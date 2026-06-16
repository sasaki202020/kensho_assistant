from __future__ import annotations

import pandas as pd

from src.data_processing.real_data_fetcher import RealDataFetcher, _course_ids_from_index_html, _result_status_from_html


def _racelist_html() -> str:
    row = lambda cells: "<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>"
    rows = []
    for lane in range(1, 3):
        rows.extend(
            [
                row(
                    [
                        str(lane),
                        "",
                        f"<a href='/owpc/pc/data/racersearch/profile?toban={1000 + lane}'>{1000 + lane} / B1<br>テスト{lane}<br>東京/東京<br>30歳/50.0kg</a>",
                        "F0<br>L0<br>0.15",
                        "5.0<br>20.0<br>40.0",
                        "4.0<br>18.0<br>38.0",
                        "10<br>30.0<br>45.0",
                        "11<br>25.0<br>35.0",
                    ]
                    + [""] * 15
                    + [f"{lane}R"]
                ),
                row(["1", "2", "3"] + [""] * 11),
                row([".17", ".18", ".19"] + [""] * 11),
                row(["1", "2", "3"] + [""] * 11),
            ]
        )
    html = f"""
    <html>
      <body>
        <h2>テスト杯</h2>
        <h3>一般戦 1800m</h3>
        <table>
          <thead><tr><th>ボートレーサー</th><th>早見</th></tr></thead>
          <tbody>
            {''.join(rows)}
          </tbody>
        </table>
      </body>
    </html>
    """
    return html


def _beforeinfo_html() -> str:
    rows = []
    for lane in range(1, 3):
        rows.extend(
            [
                f"<tr><td>{lane}</td><td></td><td>テスト{lane}</td><td>50.0</td><td>6.80</td><td>0.0</td><td></td><td></td><td>R</td><td></td></tr>",
                f"<tr><td>進入</td><td>{lane}</td></tr>",
                f"<tr><td></td><td>ST</td><td>.15</td></tr>",
                f"<tr><td>着順</td><td></td></tr>",
            ]
        )
    html = f"""
    <html>
      <body>
        <h2>テスト杯</h2>
        <h3>一般戦 1800m</h3>
        <table>
          <thead><tr><th>展示タイム</th><th>前走成績</th></tr></thead>
          <tbody>
            {''.join(rows)}
          </tbody>
        </table>
        <table>
          <thead><tr><th>スタート展示</th></tr></thead>
          <tbody>
            <tr><td>1 .15</td></tr>
            <tr><td>2 .16</td></tr>
          </tbody>
        </table>
        <div>水面気象情報 気温 25.0℃ 晴 風速 4m 水温 20.0℃ 波高 2cm</div>
      </body>
    </html>
    """
    return html


def _result_html() -> str:
    rows = []
    for lane in range(1, 7):
        rows.append(
            f"<tr><td>{lane}</td><td>{lane}</td><td><a href='/owpc/pc/data/racersearch/profile?toban={2000 + lane}'>{2000 + lane} テスト{lane}</a></td><td>1'5{lane}\"{lane}</td></tr>"
        )
    start_rows = [f"<tr><td><div class='table1_boatImage1TimeInner'>.{10 + lane}  </div></td></tr>" for lane in range(1, 7)]
    html = f"""
    <html>
      <body>
        <h2>テスト杯</h2>
        <h3>一般戦 1800m</h3>
        <table>
          <thead><tr><th>着</th><th>枠</th><th>ボートレーサー</th><th>レースタイム</th></tr></thead>
          <tbody>
            {''.join(rows)}
          </tbody>
        </table>
        <table>
          <thead><tr><th>スタート情報</th></tr></thead>
          <tbody>
            {''.join(start_rows)}
          </tbody>
        </table>
        <table>
          <thead><tr><th>勝式</th><th>組番</th><th>払戻金</th><th>人気</th></tr></thead>
          <tbody>
            <tr><td>単勝</td><td>1</td><td>¥120</td><td></td></tr>
          </tbody>
        </table>
        <div>水面気象情報 気温 22.0℃ 晴 風速 2m 水温 20.0℃ 波高 1cm</div>
      </body>
    </html>
    """
    return html


def _partial_result_html() -> str:
    rows = []
    for lane in range(1, 5):
        rows.append(
            f"<tr><td>{lane}</td><td>{lane}</td><td><a href='/owpc/pc/data/racersearch/profile?toban={2000 + lane}'>{2000 + lane} テスト{lane}</a></td><td>1'5{lane}\"{lane}</td></tr>"
        )
    return f"""
    <html>
      <body>
        <h2>テスト杯</h2>
        <h3>一般戦 1800m</h3>
        <table>
          <thead><tr><th>着</th><th>枠</th><th>ボートレーサー</th><th>レースタイム</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </body>
    </html>
    """


def _odds_html() -> str:
    win_rows = []
    place_rows = []
    for lane in range(1, 3):
        win_rows.append(
            f"<tr><td>{lane}</td><td>テスト{lane}</td><td>{1.0 + lane}</td></tr>"
        )
        place_rows.append(
            f"<tr><td>{lane}</td><td>テスト{lane}</td><td>{1.1 + lane:.1f}-{1.3 + lane:.1f}</td></tr>"
        )
    html = f"""
    <html>
      <body>
        <h2>テスト杯</h2>
        <h3>一般戦 1800m</h3>
        <table>
          <thead><tr><th>単勝オッズ</th></tr></thead>
          <tbody>{''.join(win_rows)}</tbody>
        </table>
        <table>
          <thead><tr><th>複勝オッズ</th></tr></thead>
          <tbody>{''.join(place_rows)}</tbody>
        </table>
      </body>
    </html>
    """
    return html


def test_real_data_parser_handles_core_pages() -> None:
    racelist = RealDataFetcher.parse_racelist_html(_racelist_html(), "20260613", "07", 1)
    beforeinfo = RealDataFetcher.parse_beforeinfo_html(_beforeinfo_html(), "20260613", "07", 1)
    result = RealDataFetcher.parse_result_html(_result_html(), "20260612", "07", 1)
    odds = RealDataFetcher.parse_odds_html(_odds_html(), "20260613", "07", 1)

    assert len(racelist) == 2
    assert racelist.loc[0, "name"] == "テスト1"
    assert racelist.loc[0, "grade"] == "B1"
    assert beforeinfo.loc[0, "exhibition_time"] == 6.8
    assert beforeinfo.loc[0, "start_time"] == 0.15
    assert result.loc[0, "finish_position"] == 1
    assert result.loc[0, "win"] == 1
    assert result.loc[0, "win_odds"] == 1.2
    assert pd.isna(result.loc[1, "win_odds"])
    assert result.loc[0, "weather"] == "晴"
    assert odds.loc[0, "win_odds"] == 2.0
    assert odds.loc[0, "place_odds_low"] == 2.1


def test_odds_parser_treats_zero_as_missing() -> None:
    html = """
    <html>
      <body>
        <h2>テスト杯</h2>
        <h3>一般戦 1800m</h3>
        <table>
          <thead><tr><th>単勝オッズ</th></tr></thead>
          <tbody><tr><td>1</td><td>テスト1</td><td>0.0</td></tr></tbody>
        </table>
        <table>
          <thead><tr><th>複勝オッズ</th></tr></thead>
          <tbody><tr><td>1</td><td>テスト1</td><td>0.0-0.0</td></tr></tbody>
        </table>
      </body>
    </html>
    """
    odds = RealDataFetcher.parse_odds_html(html, "20260616", "07", 1)

    assert pd.isna(odds.loc[0, "win_odds"])
    assert pd.isna(odds.loc[0, "place_odds_low"])
    assert pd.isna(odds.loc[0, "place_odds_high"])


def test_resolve_course_id() -> None:
    fetcher = RealDataFetcher(raw_dir="data/raw")
    assert fetcher.resolve_course_id("桐生") == "01"


def test_result_status_classifies_unavailable_pages() -> None:
    assert _result_status_from_html("<html>※ データはありません。</html>") == ("unavailable", "result_unpublished")
    assert _result_status_from_html("<html>レース中止</html>") == ("unavailable", "cancelled")
    assert _result_status_from_html("<html><table><tr><th>別表</th></tr></table></html>") == ("parse_error", "result_table_not_found")


def test_result_parser_keeps_partial_results() -> None:
    frame = RealDataFetcher.parse_result_html(_partial_result_html(), "20260613", "07", 1)
    assert len(frame) == 4
    assert set(frame["result_status"]) == {"partial_result"}
    assert set(frame["unavailable_reason"]) == {"fewer_than_6_finishers"}


def test_discover_course_ids_prefers_active_racelist_links() -> None:
    html = """
    <html><body>
      <a href="/owpc/pc/race/racelist?rno=1&jcd=03&hd=20260613">江戸川</a>
      <a href="/owpc/pc/race/racelist?rno=1&jcd=07&hd=20260613">蒲郡</a>
      <a href="/owpc/pc/race/raceindex?jcd=01&hd=20260613">桐生</a>
      <a href="/owpc/pc/race/racelist?rno=1&jcd=08&hd=20260612">常滑</a>
    </body></html>
    """
    assert _course_ids_from_index_html(html, "20260613") == ["03", "07"]


def test_racelist_parser_handles_wrapped_profile_text() -> None:
    html = """
    <html>
      <body>
        <h2>テスト杯</h2>
        <h3>一般戦 1800m</h3>
        <table>
          <thead><tr><th>ボートレーサー</th><th>早見</th></tr></thead>
          <tbody>
            <tr>
              <td>1</td><td></td>
              <td><div><span>4321 / A1</span><span>山田 太郎</span><span>東京/東京</span><span>41歳/52.1kg</span></div></td>
              <td>F0<br>L0<br>0.15</td><td>7.0<br>55.0<br>70.0</td><td>6.0<br>44.0<br>60.0</td>
              <td>10<br>30.0<br>45.0</td><td>11<br>25.0<br>35.0</td>
            </tr>
            <tr><td>1</td><td>2</td><td>3</td></tr>
            <tr><td>.17</td><td>.18</td><td>.19</td></tr>
            <tr><td>1</td><td>2</td><td>3</td></tr>
          </tbody>
        </table>
      </body>
    </html>
    """
    frame = RealDataFetcher.parse_racelist_html(html, "20260613", "07", 1)
    assert frame.loc[0, "racer_id"] == "4321"
    assert frame.loc[0, "grade"] == "A1"
    assert frame.loc[0, "name"] == "山田 太郎"
    assert frame.loc[0, "age"] == 41
    assert frame.loc[0, "weight"] == 52.1


def test_racelist_parser_does_not_treat_id_line_as_name() -> None:
    html = """
    <html>
      <body>
        <h2>テスト杯</h2>
        <h3>一般戦 1800m</h3>
        <table>
          <thead><tr><th>ボートレーサー</th><th>早見</th></tr></thead>
          <tbody>
            <tr>
              <td>1</td><td></td>
              <td><a href="/profile?toban=4321">4321 /<br>A1<br>山田 太郎<br>東京/東京<br>41歳/52.1kg</a></td>
              <td>F0<br>L0<br>0.15</td><td>7.0<br>55.0<br>70.0</td><td>6.0<br>44.0<br>60.0</td>
              <td>10<br>30.0<br>45.0</td><td>11<br>25.0<br>35.0</td>
            </tr>
            <tr><td>1</td><td>2</td><td>3</td></tr>
            <tr><td>.17</td><td>.18</td><td>.19</td></tr>
            <tr><td>1</td><td>2</td><td>3</td></tr>
          </tbody>
        </table>
      </body>
    </html>
    """
    frame = RealDataFetcher.parse_racelist_html(html, "20260613", "07", 1)
    assert frame.loc[0, "racer_id"] == "4321"
    assert frame.loc[0, "grade"] == "A1"
    assert frame.loc[0, "name"] == "山田 太郎"
