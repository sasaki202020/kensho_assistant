from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import numpy as np
import pandas as pd
import requests
from lxml import html as lxml_html
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from ..constants import COURSE_ID_TO_NAME, COURSE_NAME_TO_ID
from ..utils import clean_text, ensure_dir, normalize_course_id, parse_float, parse_int, race_id_for, text_lines


def _first_text(doc: lxml_html.HtmlElement, xpath: str) -> str:
    values = doc.xpath(xpath)
    if not values:
        return ""
    return clean_text(values[0])


def _parse_html(html: str | bytes) -> lxml_html.HtmlElement:
    if isinstance(html, str):
        if re.search(r"^\s*<\?xml[^>]+encoding=", html[:300], flags=re.IGNORECASE):
            return lxml_html.fromstring(html.encode("utf-8"))
        return lxml_html.fromstring(html)
    return lxml_html.fromstring(html)


def _table_by_terms(doc: lxml_html.HtmlElement, *terms: str) -> lxml_html.HtmlElement | None:
    for table in doc.xpath("//table"):
        text = clean_text(table.text_content())
        if all(term in text for term in terms):
            return table
    return None


def _table_rows(table: lxml_html.HtmlElement) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in table.xpath(".//tbody/tr"):
        cells: list[str] = []
        for cell in row.xpath("./th|./td"):
            parts = [clean_text(part) for part in cell.xpath(".//text()")]
            parts = [part for part in parts if part]
            cells.append("\n".join(parts))
        rows.append(cells)
    return rows


def _extract_racer_profile(text: str) -> dict[str, object]:
    lines = text_lines(text)
    joined = clean_text(text)
    racer_id = ""
    grade = ""
    name = ""
    match = re.search(r"(?P<id>\d{4,})\s*/\s*(?P<grade>[AB]\d)", joined)
    if match:
        racer_id = match.group("id")
        grade = match.group("grade")
    for line in lines:
        clean = clean_text(line)
        if not clean or re.search(r"\d{4,}\s*/\s*[AB]\d", clean):
            continue
        if re.fullmatch(r"\d{4,}\s*/?", clean):
            continue
        if re.search(r"(?:都|道|府|県|大阪|兵庫|東京|福岡|長崎|佐賀|沖縄|北海道|愛知|静岡|京都|滋賀|奈良|和歌山|広島|岡山|山口|徳島|香川|愛媛|高知|鳥取|島根|宮城|福島|茨城|栃木|群馬|埼玉|千葉|神奈川|山梨|長野|新潟|富山|石川|福井|岐阜|三重|宮崎|鹿児島|大分|熊本)/", clean):
            continue
        if re.search(r"\d+歳|[0-9.]+kg|^F\d+|^L\d+|^[AB]\d$", clean):
            continue
        name = clean
        break
    age = None
    weight = None
    age_match = re.search(r"(\d+)歳", joined)
    weight_match = re.search(r"([0-9.]+)kg", joined)
    if age_match:
        age = parse_int(age_match.group(1), default=None)
    if weight_match:
        weight = parse_float(weight_match.group(1), default=None)
    return {"racer_id": racer_id, "grade": grade, "name": name, "age": age, "weight": weight}


def _course_ids_from_index_html(html: str, date_text: str) -> list[str]:
    doc = _parse_html(html)
    course_ids: list[str] = []
    hrefs = doc.xpath("//a[contains(@href, 'racelist?') or contains(@href, 'beforeinfo?')]/@href")
    if not hrefs:
        hrefs = doc.xpath("//a[contains(@href, 'raceindex?jcd=')]/@href")
    for href in hrefs:
        if "hd=" in href:
            hd_match = re.search(r"hd=(\d{8})", href)
            if hd_match and hd_match.group(1) != date_text:
                continue
        match = re.search(r"jcd=(\d{2})", href)
        if not match:
            continue
        course_id = match.group(1)
        if course_id not in course_ids:
            course_ids.append(course_id)
    return course_ids


def _extract_race_meta(doc: lxml_html.HtmlElement, race_date: str, course_id: str, race_number: int) -> dict[str, object]:
    title = _first_text(doc, "//h2[1]/text()")
    subtitle = _first_text(doc, "//h3[1]/text()")
    race_class = subtitle
    distance_m = parse_int(subtitle.split()[-1].replace("m", ""), default=None) if subtitle else None
    return {
        "race_id": race_id_for(race_date, course_id, race_number),
        "race_date": pd.to_datetime(race_date),
        "course_id": normalize_course_id(course_id),
        "course_name": COURSE_ID_TO_NAME.get(normalize_course_id(course_id), ""),
        "race_number": int(race_number),
        "race_title": title,
        "race_class": race_class,
        "distance_m": distance_m,
    }


def _extract_weather(text: str) -> dict[str, object]:
    if "水面気象情報" not in text:
        return {"weather": None, "wind_speed": None, "water_temp": None, "wave_height": None}
    section = text.split("水面気象情報", 1)[1]
    normalized = clean_text(section)
    weather = None
    weather_match = re.search(r"気温\s*[0-9.]+℃\s*(?P<weather>.+?)\s*風速", normalized)
    if weather_match:
        weather = clean_text(weather_match.group("weather"))
    if not weather:
        lines = [clean_text(line) for line in section.splitlines() if clean_text(line)]
        for line in lines:
            if any(token in line for token in ["気温", "風速", "水温", "波高", "スタンド", "返還"]):
                continue
            if re.search(r"^\d+(?:\.\d+)?$", line):
                continue
            weather = line
            break
    temp_match = re.search(r"気温\s*([0-9.]+)℃", section)
    wind_match = re.search(r"風速\s*([0-9.]+)m", section)
    water_match = re.search(r"水温\s*([0-9.]+)℃", section)
    wave_match = re.search(r"波高\s*([0-9.]+)cm", section)
    temp = parse_float(temp_match.group(1) if temp_match else None)
    wind = parse_float(wind_match.group(1) if wind_match else None)
    water = parse_float(water_match.group(1) if water_match else None)
    wave = parse_float(wave_match.group(1) if wave_match else None)
    return {"weather": weather, "wind_speed": wind, "water_temp": water, "wave_height": wave}


def _result_status_from_html(html: str) -> tuple[str, str]:
    text = clean_text(html)
    if not text:
        return "parse_error", "empty_html"
    if "中止" in text:
        return "unavailable", "cancelled"
    if "順延" in text:
        return "unavailable", "postponed"
    if "不成立" in text:
        return "unavailable", "no_contest"
    if "データがありません" in text or "※ データはありません。" in text:
        return "unavailable", "result_unpublished"
    try:
        doc = _parse_html(html)
    except Exception:
        return "parse_error", "html_parse_error"
    if _table_by_terms(doc, "着", "レースタイム") is None:
        return "parse_error", "result_table_not_found"
    return "settled", ""


def _parse_number_pair(text: str) -> tuple[float | None, float | None]:
    numbers = re.findall(r"[-+]?(?:\d+\.\d+|\.\d+|\d+)", text or "")
    if len(numbers) >= 2:
        return parse_float(numbers[0]), parse_float(numbers[1])
    if len(numbers) == 1:
        return parse_float(numbers[0]), None
    return None, None


def _parse_yen_amount(text: str) -> float | None:
    normalized = clean_text(text).replace(",", "")
    match = re.search(r"\d+(?:\.\d+)?", normalized)
    if not match:
        return None
    return parse_float(match.group(0), default=None)


def _result_win_odds_by_lane(doc: lxml_html.HtmlElement) -> dict[int, float]:
    table = _table_by_terms(doc, "勝式", "払戻金")
    if table is None:
        return {}
    for row in _table_rows(table):
        if len(row) < 3 or "単勝" not in row[0]:
            continue
        lane = parse_int(row[1], default=None)
        payout_yen = _parse_yen_amount(row[2])
        if lane is None or payout_yen is None:
            continue
        return {lane: round(payout_yen / 100.0, 2)}
    return {}


def _parse_number_list(text: str, count: int = 3) -> list[float | None]:
    numbers = re.findall(r"[-+]?(?:\d+\.\d+|\.\d+|\d+)", text or "")
    values = [parse_float(value, default=None) for value in numbers[:count]]
    while len(values) < count:
        values.append(None)
    return values


@dataclass
class RealDataFetcher:
    raw_dir: str | Path
    render_wait_ms: int = 2500
    request_timeout_ms: int = 30000
    min_request_interval_sec: float = 2.0
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    use_http_fetch: bool = True

    def __post_init__(self) -> None:
        self.raw_dir = Path(self.raw_dir)
        self.html_dir = ensure_dir(self.raw_dir / "html")
        self.csv_dir = ensure_dir(self.raw_dir / "csv")
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._last_request_ts = 0.0
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": self.user_agent})
        self._robot = RobotFileParser()
        try:
            self._robot.set_url("https://www.boatrace.jp/robots.txt")
            self._robot.read()
        except Exception:
            pass

    def __enter__(self) -> "RealDataFetcher":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        self._session.close()
        if self._page is not None:
            try:
                self._page.close()
            except Exception:
                pass
            self._page = None
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def resolve_course_id(self, place: str | int) -> str:
        return normalize_course_id(place)

    def discover_course_ids(self, race_date: str | pd.Timestamp | None = None, limit: int | None = None) -> list[str]:
        date_text = pd.to_datetime(race_date or pd.Timestamp.today()).strftime("%Y%m%d")
        url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={date_text}"
        html = self._load_html(url, f"index_{date_text}")
        course_ids = _course_ids_from_index_html(html, date_text)
        if limit is not None:
            course_ids = course_ids[:limit]
        return course_ids

    def fetch_day(
        self,
        race_date: str | pd.Timestamp,
        *,
        place: str | None = None,
        course_id: str | int | None = None,
        race_numbers: Iterable[int] | None = None,
        include_beforeinfo: bool = False,
        include_results: bool = True,
        include_odds: bool = True,
        max_courses: int | None = None,
    ) -> pd.DataFrame:
        date_text = pd.to_datetime(race_date).strftime("%Y-%m-%d")
        if place:
            course_ids = [self.resolve_course_id(place)]
        elif course_id is not None:
            course_ids = [normalize_course_id(course_id)]
        else:
            course_ids = self.discover_course_ids(date_text, limit=max_courses)
        race_numbers = list(race_numbers or range(1, 13))
        frames: list[pd.DataFrame] = []
        for current_course in course_ids:
            for current_race_number in race_numbers:
                merged = self.fetch_race(
                    date_text,
                    current_course,
                    current_race_number,
                    include_beforeinfo=include_beforeinfo,
                    include_results=include_results,
                    include_odds=include_odds,
                )
                if not merged.empty:
                    frames.append(merged)
        if not frames:
            return pd.DataFrame()
        frame = pd.concat(frames, ignore_index=True)
        frame["race_date"] = pd.to_datetime(frame["race_date"], errors="coerce")
        return frame.sort_values(["race_date", "course_id", "race_number", "lane"]).reset_index(drop=True)

    def fetch_race(
        self,
        race_date: str | pd.Timestamp,
        course_id: str | int,
        race_number: int,
        *,
        include_beforeinfo: bool = False,
        include_results: bool = True,
        include_odds: bool = True,
    ) -> pd.DataFrame:
        race_date_text = pd.to_datetime(race_date).strftime("%Y%m%d")
        course = normalize_course_id(course_id)
        race_id = race_id_for(race_date_text, course, race_number)
        cache_path = (
            self.csv_dir
            / f"race_{race_date_text}_{course}_{race_number:02d}_b{int(include_beforeinfo)}_r{int(include_results)}_o{int(include_odds)}.csv"
        )
        if cache_path.exists():
            cached = pd.read_csv(cache_path)
            if "race_date" in cached.columns:
                cached["race_date"] = pd.to_datetime(cached["race_date"], errors="coerce")
            return cached

        base = self.parse_racelist_html(
            self._load_html(
                f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={race_number}&jcd={course}&hd={race_date_text}",
                f"racelist_{race_date_text}_{course}_{race_number:02d}",
            ),
            race_date_text,
            course,
            race_number,
        )
        if base.empty:
            return base

        merged = base.copy()
        if include_beforeinfo:
            beforeinfo = self.parse_beforeinfo_html(
                self._load_html(
                    f"https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={race_number}&jcd={course}&hd={race_date_text}",
                    f"beforeinfo_{race_date_text}_{course}_{race_number:02d}",
                ),
                race_date_text,
                course,
                race_number,
            )
            if not beforeinfo.empty:
                merged = merged.merge(beforeinfo, on=["race_id", "lane"], how="left", suffixes=("", "_before"))
        if include_results:
            result_frame = self.parse_result_html(
                self._load_html(
                    f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={race_number}&jcd={course}&hd={race_date_text}",
                    f"raceresult_{race_date_text}_{course}_{race_number:02d}",
                ),
                race_date_text,
                course,
                race_number,
            )
            if not result_frame.empty:
                merged = merged.merge(result_frame, on=["race_id", "lane"], how="left", suffixes=("", "_result"))
        if include_odds:
            odds_frame = self.parse_odds_html(
                self._load_html(
                    f"https://www.boatrace.jp/owpc/pc/race/oddstf?rno={race_number}&jcd={course}&hd={race_date_text}",
                    f"oddstf_{race_date_text}_{course}_{race_number:02d}",
                ),
                race_date_text,
                course,
                race_number,
            )
            if not odds_frame.empty:
                merged = merged.merge(odds_frame, on=["race_id", "lane"], how="left", suffixes=("", "_odds"))

        for column in ["weather", "wind_speed", "water_temp", "wave_height"]:
            if column not in merged.columns:
                merged[column] = np.nan
        output = merged.sort_values("lane").reset_index(drop=True)
        output.to_csv(cache_path, index=False, encoding="utf-8-sig")
        return output

    def fetch_results_day(
        self,
        race_date: str | pd.Timestamp,
        *,
        course_ids: Iterable[str | int] | None = None,
        race_numbers: Iterable[int] | None = None,
        max_courses: int | None = None,
    ) -> pd.DataFrame:
        date_text = pd.to_datetime(race_date).strftime("%Y-%m-%d")
        if course_ids is None:
            courses = self.discover_course_ids(date_text, limit=max_courses)
        else:
            courses = [normalize_course_id(course_id) for course_id in course_ids]
        frames: list[pd.DataFrame] = []
        for current_course in courses:
            for current_race_number in list(race_numbers or range(1, 13)):
                frame = self.fetch_result_race(date_text, current_course, current_race_number)
                if not frame.empty:
                    frames.append(frame)
        if not frames:
            return pd.DataFrame()
        frame = pd.concat(frames, ignore_index=True)
        frame["race_date"] = pd.to_datetime(frame["race_date"], errors="coerce")
        return frame.sort_values(["race_date", "course_id", "race_number", "lane"]).reset_index(drop=True)

    def fetch_result_race(
        self,
        race_date: str | pd.Timestamp,
        course_id: str | int,
        race_number: int,
    ) -> pd.DataFrame:
        frame, _status = self.fetch_result_race_with_status(race_date, course_id, race_number)
        return frame

    def fetch_result_race_with_status(
        self,
        race_date: str | pd.Timestamp,
        course_id: str | int,
        race_number: int,
    ) -> tuple[pd.DataFrame, dict[str, object]]:
        race_date_text = pd.to_datetime(race_date).strftime("%Y%m%d")
        course = normalize_course_id(course_id)
        race_id = race_id_for(race_date_text, course, race_number)
        status = {
            "stage": "night_fetch",
            "course_id": course,
            "race_number": int(race_number),
            "race_id": race_id,
            "status": "unavailable",
            "unavailable_reason": "unknown",
            "message": "",
        }
        cache_path = self.csv_dir / f"result_{race_date_text}_{course}_{race_number:02d}.csv"
        if cache_path.exists():
            cached = pd.read_csv(cache_path)
            if "win_odds" not in cached.columns or pd.to_numeric(cached.get("win_odds"), errors="coerce").isna().all():
                html_path = self.html_dir / f"raceresult_{race_date_text}_{course}_{race_number:02d}.html"
                if html_path.exists():
                    reparsed = self.parse_result_html(
                        html_path.read_text(encoding="utf-8"),
                        race_date_text,
                        course,
                        race_number,
                    )
                    if not reparsed.empty and "win_odds" in reparsed.columns:
                        reparsed.to_csv(cache_path, index=False, encoding="utf-8-sig")
                        cached = reparsed
            if "race_date" in cached.columns:
                cached["race_date"] = pd.to_datetime(cached["race_date"], errors="coerce")
            status.update({"status": "settled", "unavailable_reason": "", "message": "cached result"})
            return cached, status
        html = self._load_html(
            f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={race_number}&jcd={course}&hd={race_date_text}",
            f"raceresult_{race_date_text}_{course}_{race_number:02d}",
        )
        html_status, reason = _result_status_from_html(html)
        frame = self.parse_result_html(
            html,
            race_date_text,
            course,
            race_number,
        )
        if not frame.empty:
            if "result_status" not in frame.columns:
                frame["result_status"] = "settled"
            if "unavailable_reason" not in frame.columns:
                frame["unavailable_reason"] = ""
            frame.to_csv(cache_path, index=False, encoding="utf-8-sig")
            status.update({"status": "settled", "unavailable_reason": "", "message": "result parsed"})
        else:
            status.update({"status": html_status, "unavailable_reason": reason, "message": reason})
        return frame, status

    def fetch_odds_race(
        self,
        race_date: str | pd.Timestamp,
        course_id: str | int,
        race_number: int,
        *,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        race_date_text = pd.to_datetime(race_date).strftime("%Y%m%d")
        course = normalize_course_id(course_id)
        html = self._load_html(
            f"https://www.boatrace.jp/owpc/pc/race/oddstf?rno={race_number}&jcd={course}&hd={race_date_text}",
            f"oddstf_{race_date_text}_{course}_{race_number:02d}",
            force_refresh=force_refresh,
        )
        return self.parse_odds_html(html, race_date_text, course, race_number)

    def _ensure_browser(self) -> None:
        if self._page is not None:
            return
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context(
            user_agent=self.user_agent,
            locale="ja-JP",
            viewport={"width": 1440, "height": 1800},
        )
        self._page = self._context.new_page()
        self._page.route("**/*", self._route_request)

    def _route_request(self, route) -> None:
        request = route.request
        parsed = urlparse(request.url)
        if request.resource_type in {"image", "font", "media"}:
            route.abort()
            return
        if parsed.scheme in {"data", "about", "javascript"}:
            route.continue_()
            return
        if parsed.netloc and not parsed.netloc.endswith("boatrace.jp"):
            route.abort()
            return
        route.continue_()

    def _respect_interval(self) -> None:
        elapsed = time.time() - self._last_request_ts
        if elapsed < self.min_request_interval_sec:
            time.sleep(self.min_request_interval_sec - elapsed)

    def _load_html(self, url: str, cache_key: str, *, force_refresh: bool = False) -> str:
        html_path = self.html_dir / f"{cache_key}.html"
        if html_path.exists() and not force_refresh:
            return html_path.read_text(encoding="utf-8")
        if self._robot and not self._robot.can_fetch(self.user_agent, url):
            raise RuntimeError(f"Robots.txt disallows access to {url}")
        if self.use_http_fetch:
            for request_attempt in range(1, 4):
                try:
                    self._respect_interval()
                    response = self._session.get(url, timeout=self.request_timeout_ms / 1000)
                    response.raise_for_status()
                    response.encoding = response.apparent_encoding or "utf-8"
                    html = response.text
                    html_path.write_text(html, encoding="utf-8")
                    self._last_request_ts = time.time()
                    return html
                except requests.RequestException:
                    if request_attempt >= 3:
                        break
                    time.sleep(2**request_attempt)
        attempt = 0
        self._ensure_browser()
        while True:
            attempt += 1
            try:
                self._respect_interval()
                assert self._page is not None
                self._page.goto(url, wait_until="domcontentloaded", timeout=self.request_timeout_ms)
                self._page.wait_for_timeout(self.render_wait_ms)
                html = self._page.content()
                html_path.write_text(html, encoding="utf-8")
                self._last_request_ts = time.time()
                return html
            except PlaywrightTimeoutError:
                if attempt >= 3:
                    raise
                time.sleep(2**attempt)
                self._page = self._context.new_page() if self._context is not None else None
                if self._page is not None:
                    self._page.route("**/*", self._route_request)
            except Exception:
                if attempt >= 3:
                    raise
                time.sleep(2**attempt)

    @staticmethod
    def parse_racelist_html(html: str, race_date: str, course_id: str, race_number: int) -> pd.DataFrame:
        if "データがありません" in html:
            return pd.DataFrame()
        doc = _parse_html(html)
        table = _table_by_terms(doc, "ボートレーサー", "早見")
        if table is None:
            return pd.DataFrame()
        meta = _extract_race_meta(doc, race_date, course_id, race_number)
        weather = _extract_weather(clean_text(doc.text_content()))
        rows = _table_rows(table)
        if len(rows) < 4:
            return pd.DataFrame()
        records: list[dict[str, object]] = []
        for idx in range(0, len(rows), 4):
            block = rows[idx : idx + 4]
            if len(block) < 4:
                continue
            row0, row1, row2, row3 = block
            lane = parse_int(row0[0], default=None)
            if lane is None:
                continue
            profile_text = row0[2] if len(row0) > 2 else ""
            if not text_lines(profile_text):
                continue
            profile = _extract_racer_profile(profile_text)
            f_count, l_count, avg_st = _parse_number_list(row0[3] if len(row0) > 3 else "", count=3)
            national_win_rate, national_2rate, national_3rate = _parse_number_list(row0[4] if len(row0) > 4 else "", count=3)
            local_win_rate, local_2rate, local_3rate = _parse_number_list(row0[5] if len(row0) > 5 else "", count=3)
            motor_no, motor_2rate, motor_3rate = _parse_number_list(row0[6] if len(row0) > 6 else "", count=3)
            boat_no, boat_2rate, boat_3rate = _parse_number_list(row0[7] if len(row0) > 7 else "", count=3)
            recent_form_text = " | ".join(filter(None, row0[9:23])) if len(row0) > 9 else ""
            records.append(
                {
                    **meta,
                    **weather,
                    "lane": lane,
                    "racer_id": profile["racer_id"],
                    "name": profile["name"],
                    "grade": profile["grade"],
                    "age": profile["age"],
                    "weight": profile["weight"],
                    "f_count": f_count,
                    "l_count": l_count,
                    "avg_st": avg_st,
                    "national_win_rate": national_win_rate,
                    "national_2rate": national_2rate,
                    "national_3rate": national_3rate,
                    "local_win_rate": local_win_rate,
                    "local_2rate": local_2rate,
                    "local_3rate": local_3rate,
                    "motor_no": motor_no,
                    "motor_2rate": motor_2rate,
                    "motor_3rate": motor_3rate,
                    "boat_no": boat_no,
                    "boat_2rate": boat_2rate,
                    "boat_3rate": boat_3rate,
                    "recent_form_text": recent_form_text,
                }
            )
        return pd.DataFrame(records)

    @staticmethod
    def parse_beforeinfo_html(html: str, race_date: str, course_id: str, race_number: int) -> pd.DataFrame:
        if "データがありません" in html:
            return pd.DataFrame()
        doc = _parse_html(html)
        table = _table_by_terms(doc, "展示タイム", "前走成績")
        if table is None:
            return pd.DataFrame()
        meta = _extract_race_meta(doc, race_date, course_id, race_number)
        weather = _extract_weather(clean_text(doc.text_content()))
        rows = _table_rows(table)
        if len(rows) < 4:
            return pd.DataFrame()
        records: list[dict[str, object]] = []
        for idx in range(0, len(rows), 4):
            block = rows[idx : idx + 4]
            if len(block) < 4:
                continue
            row0, row1, row2, row3 = block
            lane = parse_int(row0[0], default=None)
            if lane is None:
                continue
            racer_id_match = re.search(r"toban=(\d+)", "".join(doc.xpath(f"//tbody//tr[{idx + 1}]//a/@href")))
            racer_id = racer_id_match.group(1) if racer_id_match else ""
            name = row0[2] if len(row0) > 2 else ""
            exhibition_time = parse_float(row0[4] if len(row0) > 4 else None, default=None)
            tilt = parse_float(row0[5] if len(row0) > 5 else None, default=None)
            propeller = row0[6] if len(row0) > 6 else ""
            parts_exchange = row0[7] if len(row0) > 7 else ""
            start_course = parse_int(row1[1] if len(row1) > 1 else None, default=None)
            start_time = parse_float(row2[2] if len(row2) > 2 else None, default=None)
            finish_order = row3[1] if len(row3) > 1 else ""
            records.append(
                {
                    **meta,
                    **weather,
                    "lane": lane,
                    "racer_id": racer_id,
                    "name": name,
                    "exhibition_time": exhibition_time,
                    "start_time": start_time,
                    "tilt": tilt,
                    "propeller": propeller,
                    "parts_exchange": parts_exchange,
                    "start_exhibition_course": start_course,
                    "start_exhibition_lane": lane,
                    "start_exhibition_st": start_time,
                    "pre_race_result": finish_order,
                }
            )
        return pd.DataFrame(records)

    @staticmethod
    def parse_result_html(html: str, race_date: str, course_id: str, race_number: int) -> pd.DataFrame:
        if "データがありません" in html or "※ データはありません。" in html:
            return pd.DataFrame()
        doc = _parse_html(html)
        table = _table_by_terms(doc, "着", "レースタイム")
        if table is None:
            return pd.DataFrame()
        meta = _extract_race_meta(doc, race_date, course_id, race_number)
        weather = _extract_weather(clean_text(doc.text_content()))
        rows = _table_rows(table)
        if not rows:
            return pd.DataFrame()
        records: list[dict[str, object]] = []
        for row in rows:
            if len(row) < 4:
                continue
            finish_position = parse_int(row[0], default=None)
            lane = parse_int(row[1], default=None)
            if finish_position is None or lane is None:
                continue
            anchor_match = re.search(r"toban=(\d+)", " ".join(doc.xpath(f"//tbody//tr[td[text()='{row[0]}'] and td[text()='{row[1]}']]//a/@href")))
            racer_id = anchor_match.group(1) if anchor_match else ""
            name = row[2].split()[-1] if row[2] else ""
            race_time = row[3] if len(row) > 3 else ""
            records.append(
                {
                    **meta,
                    **weather,
                    "lane": lane,
                    "racer_id": racer_id,
                    "name": name,
                    "finish_position": finish_position,
                    "race_time": race_time,
                    "decision": "",
                    "win": int(finish_position == 1),
                    "place": int(finish_position <= 2),
                    "show": int(finish_position <= 3),
                    "result_status": "settled" if len(rows) >= 6 else "partial_result",
                    "unavailable_reason": "" if len(rows) >= 6 else "fewer_than_6_finishers",
                }
            )
        result_win_odds = _result_win_odds_by_lane(doc)
        for record in records:
            lane = int(record["lane"])
            if lane in result_win_odds:
                record["win_odds"] = result_win_odds[lane]
        start_table = _table_by_terms(doc, "スタート情報")
        if start_table is not None:
            start_rows = _table_rows(start_table)
            start_map: dict[int, dict[str, object]] = {}
            for row in start_rows:
                text = " ".join(row)
                lane = parse_int(text, default=None)
                if lane is None:
                    continue
                numbers = re.findall(r"[-+]?(?:\d+\.\d+|\.\d+|\d+)", text)
                actual_st = parse_float(numbers[1] if len(numbers) > 1 else None, default=None)
                start_map[lane] = {"actual_start_time": actual_st}
            for record in records:
                lane = int(record["lane"])
                record.update(start_map.get(lane, {}))
        return pd.DataFrame(records)

    @staticmethod
    def parse_odds_html(html: str, race_date: str, course_id: str, race_number: int) -> pd.DataFrame:
        if "データがありません" in html:
            return pd.DataFrame()
        doc = _parse_html(html)
        meta = _extract_race_meta(doc, race_date, course_id, race_number)
        win_table = _table_by_terms(doc, "単勝オッズ")
        place_table = _table_by_terms(doc, "複勝オッズ")
        if win_table is None and place_table is None:
            return pd.DataFrame()
        win_rows = _table_rows(win_table) if win_table is not None else []
        place_rows = _table_rows(place_table) if place_table is not None else []
        odds_map: dict[int, dict[str, object]] = {}
        for row in win_rows:
            if len(row) < 3:
                continue
            lane = parse_int(row[0], default=None)
            if lane is None:
                continue
            odds_map.setdefault(lane, {}).update(
                {
                    "win_odds": parse_float(row[2], default=None),
                }
            )
        for row in place_rows:
            if len(row) < 3:
                continue
            lane = parse_int(row[0], default=None)
            if lane is None:
                continue
            low, high = _parse_number_pair(row[2])
            odds_map.setdefault(lane, {}).update(
                {
                    "place_odds_low": low,
                    "place_odds_high": high,
                }
            )
        records = [{**meta, "lane": lane, **values} for lane, values in odds_map.items()]
        return pd.DataFrame(records)
