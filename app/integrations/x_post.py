from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import requests

from ..paths import X_POST_HISTORY_JSONL, ensure_runtime_dirs
from ..privacy_guard import redact_personal_info, sanitize_exception_message


X_POST_API_URL = "https://api.x.com/2/tweets"
DEFAULT_MAX_POST_CHARS = 280
DEFAULT_MAX_URLS = 2
DEFAULT_MAX_HASHTAGS = 5
RECENT_DUPLICATE_WINDOW_HOURS = 24
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
HASHTAG_RE = re.compile(r"(?<!\w)#([\w_]+)", re.UNICODE)
SECRET_PAIR_RE = re.compile(
    r"(?i)\b(api[-_ ]?key|access[-_ ]?token|refresh[-_ ]?token|bearer\s+token|client[-_ ]?secret|secret|token)\b\s*[:=]\s*([^\s,;\"']+)"
)


def _env_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    text = value.strip().casefold()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _env_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(str(value).strip())
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _normalized_text(text: str) -> str:
    return _clean_text(text).casefold()


def _text_hash(text: str) -> str:
    normalized = _normalized_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _count_urls(text: str) -> int:
    return len(URL_RE.findall(text or ""))


def _count_hashtags(text: str) -> int:
    return len(HASHTAG_RE.findall(text or ""))


def _safe_preview(text: str, limit: int = 120) -> str:
    redacted = redact_personal_info(_clean_text(text))
    if len(redacted) <= limit:
        return redacted
    return redacted[: max(0, limit - 1)] + "…"


def _mask_secret_like_text(text: str) -> str:
    safe = redact_personal_info(text or "")
    return SECRET_PAIR_RE.sub(r"\1=[redacted]", safe)


def _parse_bool_from_env(env: Mapping[str, str], key: str, default: bool) -> bool:
    return _env_bool(env.get(key), default)


def _parse_int_from_env(env: Mapping[str, str], key: str, default: int) -> int:
    return _env_int(env.get(key), default)


def _now_iso(now: datetime | None = None) -> str:
    current = now or datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc).astimezone()
    return current.isoformat(timespec="seconds")


def _parse_iso_datetime(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _percent_encode(value: str) -> str:
    return urllib.parse.quote(value, safe="~")


def _normalize_base_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower() or "https"
    host = parsed.hostname.lower() if parsed.hostname else ""
    port = parsed.port
    default_port = 443 if scheme == "https" else 80
    netloc = host
    if port and port != default_port:
        netloc = f"{host}:{port}"
    path = parsed.path or "/"
    return urllib.parse.urlunparse((scheme, netloc, path, "", "", ""))


def _build_oauth1_header(
    method: str,
    url: str,
    *,
    consumer_key: str,
    consumer_secret: str,
    token: str,
    token_secret: str,
    extra_params: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> str:
    oauth_params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": secrets.token_urlsafe(24).replace("=", ""),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int((now or datetime.now().astimezone()).timestamp())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    signature_params = {**(extra_params or {}), **oauth_params}
    normalized_pairs = sorted((_percent_encode(str(key)), _percent_encode(str(value))) for key, value in signature_params.items())
    normalized_param_string = "&".join(f"{key}={value}" for key, value in normalized_pairs)
    base_string = "&".join(
        [
            method.upper(),
            _percent_encode(_normalize_base_url(url)),
            _percent_encode(normalized_param_string),
        ]
    )
    signing_key = f"{_percent_encode(consumer_secret)}&{_percent_encode(token_secret)}"
    digest = hmac.new(signing_key.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha1).digest()
    oauth_params["oauth_signature"] = base64.b64encode(digest).decode("ascii")
    header_parts = []
    for key in (
        "oauth_consumer_key",
        "oauth_nonce",
        "oauth_signature",
        "oauth_signature_method",
        "oauth_timestamp",
        "oauth_token",
        "oauth_version",
    ):
        header_parts.append(f'{_percent_encode(key)}="{_percent_encode(oauth_params[key])}"')
    return "OAuth " + ", ".join(header_parts)


@dataclass(slots=True)
class XPostConfig:
    enabled: bool = False
    dry_run: bool = True
    auth_mode: str = "oauth2"
    client_id: str = ""
    client_secret: str = ""
    callback_url: str = ""
    access_token: str = ""
    refresh_token: str = ""
    api_key: str = ""
    api_secret: str = ""
    access_token_secret: str = ""
    max_chars: int = DEFAULT_MAX_POST_CHARS
    max_urls: int = DEFAULT_MAX_URLS
    max_hashtags: int = DEFAULT_MAX_HASHTAGS
    history_path: Path = X_POST_HISTORY_JSONL

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "XPostConfig":
        source = env or os.environ
        auth_mode = str(source.get("X_AUTH_MODE", "oauth2")).strip().casefold() or "oauth2"
        return cls(
            enabled=_parse_bool_from_env(source, "X_AUTO_POST_ENABLED", False),
            dry_run=_parse_bool_from_env(source, "X_DRY_RUN", True),
            auth_mode=auth_mode,
            client_id=str(source.get("X_CLIENT_ID", "")).strip(),
            client_secret=str(source.get("X_CLIENT_SECRET", "")).strip(),
            callback_url=str(source.get("X_CALLBACK_URL", "")).strip(),
            access_token=str(source.get("X_ACCESS_TOKEN", "")).strip(),
            refresh_token=str(source.get("X_REFRESH_TOKEN", "")).strip(),
            api_key=str(source.get("X_API_KEY", "")).strip(),
            api_secret=str(source.get("X_API_SECRET", "")).strip(),
            access_token_secret=str(source.get("X_ACCESS_TOKEN_SECRET", "")).strip(),
            max_chars=_parse_int_from_env(source, "X_MAX_POST_CHARS", DEFAULT_MAX_POST_CHARS),
            max_urls=_parse_int_from_env(source, "X_MAX_URLS", DEFAULT_MAX_URLS),
            max_hashtags=_parse_int_from_env(source, "X_MAX_HASHTAGS", DEFAULT_MAX_HASHTAGS),
            history_path=Path(source.get("X_POST_HISTORY_PATH", str(X_POST_HISTORY_JSONL))),
        )


def load_x_post_config(env: Mapping[str, str] | None = None) -> XPostConfig:
    return XPostConfig.from_env(env)


def load_post_history(path: Path | str | None = None) -> list[dict[str, Any]]:
    history_path = Path(path) if path else X_POST_HISTORY_JSONL
    if not history_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw_line in history_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            rows.append(record)
    return rows


def _append_history_record(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(record), ensure_ascii=False) + "\n")


def _recent_duplicate(
    text_hash: str,
    history: Iterable[Mapping[str, Any]],
    *,
    now: datetime,
    window_hours: int = RECENT_DUPLICATE_WINDOW_HOURS,
) -> Mapping[str, Any] | None:
    cutoff = now - timedelta(hours=window_hours)
    for row in history:
        if str(row.get("status", "")).casefold() not in {"posted", "success"}:
            continue
        if str(row.get("text_hash", "")) != text_hash:
            continue
        row_dt = _parse_iso_datetime(str(row.get("posted_at", "") or row.get("ts", "")))
        if row_dt is None or row_dt < cutoff:
            continue
        return row
    return None


def _safe_error_summary(status_code: int, response_text: str = "", response_json: Mapping[str, Any] | None = None) -> str:
    if status_code == 429:
        reason = "rate_limited"
    elif status_code in {401, 403}:
        reason = "auth_error"
    elif status_code >= 500:
        reason = "server_error"
    else:
        reason = "http_error"
    detail = ""
    if response_json:
        for key in ("title", "detail", "message", "error", "type"):
            value = response_json.get(key)
            if isinstance(value, str) and value.strip():
                detail = _mask_secret_like_text(value.strip())
                break
            if isinstance(value, list) and value:
                candidate = value[0]
                if isinstance(candidate, str) and candidate.strip():
                    detail = _mask_secret_like_text(candidate.strip())
                    break
    if not detail and response_text:
        detail = _mask_secret_like_text(response_text.strip())
    detail = detail[:220]
    summary = f"HTTP {status_code}: {reason}"
    if detail:
        summary = f"{summary} - {detail}"
    return summary


def _parse_response_json(response: requests.Response) -> Mapping[str, Any] | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _build_request_headers(config: XPostConfig, *, method: str, url: str, now: datetime | None = None) -> dict[str, str]:
    if config.auth_mode == "oauth2":
        if not config.access_token:
            raise ValueError("missing_access_token")
        return {
            "Authorization": f"Bearer {config.access_token}",
            "Content-Type": "application/json",
        }
    if config.auth_mode == "oauth1a":
        missing = [
            name
            for name, value in (
                ("X_API_KEY", config.api_key),
                ("X_API_SECRET", config.api_secret),
                ("X_ACCESS_TOKEN", config.access_token),
                ("X_ACCESS_TOKEN_SECRET", config.access_token_secret),
            )
            if not value
        ]
        if missing:
            raise ValueError("missing_oauth1_credentials")
        return {
            "Authorization": _build_oauth1_header(
                method,
                url,
                consumer_key=config.api_key,
                consumer_secret=config.api_secret,
                token=config.access_token,
                token_secret=config.access_token_secret,
                now=now,
            ),
            "Content-Type": "application/json",
        }
    raise ValueError("unsupported_auth_mode")


def _build_preview(text: str, config: XPostConfig, *, live_requested: bool, confirm_live: bool) -> dict[str, Any]:
    normalized = _clean_text(text)
    return {
        "text_preview": _safe_preview(normalized),
        "length": len(normalized),
        "url_count": _count_urls(normalized),
        "hashtag_count": _count_hashtags(normalized),
        "enabled": bool(config.enabled),
        "dry_run": bool(config.dry_run),
        "auth_mode": config.auth_mode,
        "live_requested": live_requested,
        "confirm_live": bool(confirm_live),
    }


def create_post(
    text: str,
    *,
    confirm_live: bool = False,
    dry_run: bool | None = None,
    config: XPostConfig | None = None,
    session: requests.Session | None = None,
    now: datetime | None = None,
    timeout_sec: int = 30,
) -> dict[str, Any]:
    ensure_runtime_dirs()
    cfg = config or load_x_post_config()
    effective_dry_run = cfg.dry_run if dry_run is None else bool(dry_run)
    live_requested = not effective_dry_run
    normalized = _clean_text(text)
    current_time = now or datetime.now().astimezone()
    preview = _build_preview(normalized, cfg, live_requested=live_requested, confirm_live=confirm_live)
    warnings: list[str] = []
    if not normalized:
        return {
            "status": "failed",
            "reason": "empty_text",
            "sent": False,
            "dry_run": effective_dry_run,
            "confirm_live": bool(confirm_live),
            "enabled": bool(cfg.enabled),
            "auth_mode": cfg.auth_mode,
            "preview": preview,
            "warnings": warnings,
            "http_status": 0,
            "tweet_id": "",
            "request_url": X_POST_API_URL,
            "history_path": str(cfg.history_path),
            "error_summary": "投稿文が空です。",
        }
    if len(normalized) > cfg.max_chars:
        return {
            "status": "failed",
            "reason": "post_too_long",
            "sent": False,
            "dry_run": effective_dry_run,
            "confirm_live": bool(confirm_live),
            "enabled": bool(cfg.enabled),
            "auth_mode": cfg.auth_mode,
            "preview": preview,
            "warnings": warnings,
            "http_status": 0,
            "tweet_id": "",
            "request_url": X_POST_API_URL,
            "history_path": str(cfg.history_path),
            "error_summary": f"投稿文が長すぎます: {len(normalized)} > {cfg.max_chars}",
        }
    if preview["url_count"] > cfg.max_urls:
        warnings.append(f"URL が多めです: {preview['url_count']} 件")
    if preview["hashtag_count"] > cfg.max_hashtags:
        warnings.append(f"ハッシュタグが多めです: {preview['hashtag_count']} 件")

    text_hash = _text_hash(normalized)
    history = load_post_history(cfg.history_path)
    recent = _recent_duplicate(text_hash, history, now=current_time)
    if recent:
        warnings.append("24時間以内の同文投稿履歴があります")
        if live_requested:
            return {
                "status": "failed",
                "reason": "duplicate_post",
                "sent": False,
                "dry_run": effective_dry_run,
                "confirm_live": bool(confirm_live),
                "enabled": bool(cfg.enabled),
                "auth_mode": cfg.auth_mode,
                "preview": preview,
                "warnings": warnings,
                "http_status": 0,
                "tweet_id": "",
                "request_url": X_POST_API_URL,
                "history_path": str(cfg.history_path),
                "error_summary": "直近24時間以内に同じ文章が投稿済みです。",
            }

    if effective_dry_run:
        return {
            "status": "success",
            "reason": "dry_run",
            "sent": False,
            "dry_run": True,
            "confirm_live": bool(confirm_live),
            "enabled": bool(cfg.enabled),
            "auth_mode": cfg.auth_mode,
            "preview": preview,
            "warnings": warnings,
            "http_status": 0,
            "tweet_id": "",
            "request_url": X_POST_API_URL,
            "history_path": str(cfg.history_path),
        }

    if not cfg.enabled:
        return {
            "status": "failed",
            "reason": "auto_post_disabled",
            "sent": False,
            "dry_run": False,
            "confirm_live": bool(confirm_live),
            "enabled": bool(cfg.enabled),
            "auth_mode": cfg.auth_mode,
            "preview": preview,
            "warnings": warnings,
            "http_status": 0,
            "tweet_id": "",
            "request_url": X_POST_API_URL,
            "history_path": str(cfg.history_path),
            "error_summary": "X_AUTO_POST_ENABLED が true ではありません。",
        }
    if not confirm_live:
        return {
            "status": "failed",
            "reason": "confirm_live_required",
            "sent": False,
            "dry_run": False,
            "confirm_live": False,
            "enabled": bool(cfg.enabled),
            "auth_mode": cfg.auth_mode,
            "preview": preview,
            "warnings": warnings,
            "http_status": 0,
            "tweet_id": "",
            "request_url": X_POST_API_URL,
            "history_path": str(cfg.history_path),
            "error_summary": "本番投稿には --confirm-live が必要です。",
        }

    body = {"text": normalized}
    try:
        headers = _build_request_headers(cfg, method="POST", url=X_POST_API_URL, now=current_time)
    except ValueError as exc:
        reason = str(exc)
        if reason == "missing_access_token":
            error_summary = "OAuth 2.0 の X_ACCESS_TOKEN が必要です。"
        elif reason == "missing_oauth1_credentials":
            error_summary = "OAuth 1.0a の認証情報が不足しています。"
        elif reason == "unsupported_auth_mode":
            error_summary = "X_AUTH_MODE は oauth2 か oauth1a を指定してください。"
        else:
            error_summary = "認証設定を確認してください。"
        return {
            "status": "failed",
            "reason": reason,
            "sent": False,
            "dry_run": False,
            "confirm_live": True,
            "enabled": bool(cfg.enabled),
            "auth_mode": cfg.auth_mode,
            "preview": preview,
            "warnings": warnings,
            "http_status": 0,
            "tweet_id": "",
            "request_url": X_POST_API_URL,
            "history_path": str(cfg.history_path),
            "error_summary": error_summary,
        }

    http = session or requests.Session()
    try:
        response = http.post(X_POST_API_URL, headers=headers, json=body, timeout=timeout_sec)
    except requests.Timeout as exc:
        return {
            "status": "failed",
            "reason": "timeout",
            "sent": False,
            "dry_run": False,
            "confirm_live": True,
            "enabled": bool(cfg.enabled),
            "auth_mode": cfg.auth_mode,
            "preview": preview,
            "warnings": warnings,
            "http_status": 0,
            "tweet_id": "",
            "request_url": X_POST_API_URL,
            "history_path": str(cfg.history_path),
            "error_summary": sanitize_exception_message(exc),
        }
    except requests.RequestException as exc:
        return {
            "status": "failed",
            "reason": "network_error",
            "sent": False,
            "dry_run": False,
            "confirm_live": True,
            "enabled": bool(cfg.enabled),
            "auth_mode": cfg.auth_mode,
            "preview": preview,
            "warnings": warnings,
            "http_status": 0,
            "tweet_id": "",
            "request_url": X_POST_API_URL,
            "history_path": str(cfg.history_path),
            "error_summary": sanitize_exception_message(exc),
        }

    status_code = int(getattr(response, "status_code", 0) or 0)
    response_json = _parse_response_json(response)
    if status_code == 429:
        return {
            "status": "failed",
            "reason": "rate_limited",
            "sent": False,
            "dry_run": False,
            "confirm_live": True,
            "enabled": bool(cfg.enabled),
            "auth_mode": cfg.auth_mode,
            "preview": preview,
            "warnings": warnings,
            "http_status": status_code,
            "tweet_id": "",
            "request_url": X_POST_API_URL,
            "history_path": str(cfg.history_path),
            "error_summary": _safe_error_summary(status_code, getattr(response, "text", ""), response_json),
        }
    if status_code >= 400:
        return {
            "status": "failed",
            "reason": "api_error",
            "sent": False,
            "dry_run": False,
            "confirm_live": True,
            "enabled": bool(cfg.enabled),
            "auth_mode": cfg.auth_mode,
            "preview": preview,
            "warnings": warnings,
            "http_status": status_code,
            "tweet_id": "",
            "request_url": X_POST_API_URL,
            "history_path": str(cfg.history_path),
            "error_summary": _safe_error_summary(status_code, getattr(response, "text", ""), response_json),
        }

    tweet_id = ""
    if response_json:
        data = response_json.get("data")
        if isinstance(data, Mapping):
            tweet_id = str(data.get("id", "") or "")
    record = {
        "posted_at": _now_iso(current_time),
        "status": "posted",
        "auth_mode": cfg.auth_mode,
        "text_hash": text_hash,
        "text_preview": preview["text_preview"],
        "text_length": len(normalized),
        "tweet_id": tweet_id,
        "warnings": warnings,
        "request_url": X_POST_API_URL,
    }
    _append_history_record(cfg.history_path, record)
    return {
        "status": "success",
        "reason": "ok",
        "sent": True,
        "dry_run": False,
        "confirm_live": True,
        "enabled": bool(cfg.enabled),
        "auth_mode": cfg.auth_mode,
        "preview": preview,
        "warnings": warnings,
        "http_status": status_code,
        "tweet_id": tweet_id,
        "request_url": X_POST_API_URL,
        "history_path": str(cfg.history_path),
    }
