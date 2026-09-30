"""Sentinel network monitor and residue checks against local fixtures only.

Every browser test also attaches the legacy smoke-monitor logic (copied from
scripts/run_extension_local_smoke.py before this change) to show which cases
it silently missed.  Chromium is started with host-resolver rules that make
every non-loopback hostname unresolvable except ``external.test``, which is
mapped to 127.0.0.1, so no test can reach the internet.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import secrets
import socket
import threading
import zlib
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator
from urllib.parse import quote, urlsplit

import pytest
from playwright.sync_api import sync_playwright

from kensho_assistant.app.pilot_network_monitor import (
    CLEAN,
    LEAK,
    OPAQUE,
    UNVERIFIED,
    SentinelMatcher,
    SentinelNetworkMonitor,
    classify_payload,
    evaluate_worker,
    live_extension_worker,
    service_worker_network_events,
)
from kensho_assistant.app.pilot_residue import (
    check_sentinel_residue,
    compare_sha256_snapshots,
    snapshot_sha256,
)

TESTS_ROOT = Path(__file__).resolve().parent
CHANNELS = "pilot_monitor_fixtures/channels.html"


def _nonce() -> str:
    return secrets.token_hex(16)


# --------------------------------------------------------------------------
# Pure unit tests: variant matcher and classifier (no browser)
# --------------------------------------------------------------------------

def _legacy_match(nonce: str, body: bytes) -> bool:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = ""
    return nonce in text


def test_nonce_must_be_long_ascii_alnum() -> None:
    for bad in ("short", "has space 0123456789", "ｆｕｌｌｗｉｄｔｈ0123456789", "abc-def-0123456789", ""):
        with pytest.raises(ValueError):
            SentinelMatcher(bad)
    SentinelMatcher("a1" * 8)


@pytest.mark.parametrize(
    "encode",
    [
        pytest.param(lambda n: n.encode(), id="raw"),
        pytest.param(lambda n: n.upper().encode(), id="uppercased"),
        pytest.param(lambda n: "".join(f"%{ord(c):02X}" for c in n).encode(), id="percent-upper"),
        pytest.param(lambda n: "".join(f"%{ord(c):02x}" for c in n).encode(), id="percent-lower"),
        pytest.param(lambda n: quote(quote("a b " + n)).replace("%2520", "+").encode(), id="double-percent-plus"),
        pytest.param(lambda n: ("q=hello+" + n + "+world").encode(), id="form-plus"),
        pytest.param(lambda n: base64.b64encode(n.encode()).rstrip(b"="), id="base64-offset0"),
        pytest.param(lambda n: base64.b64encode(b"x" + n.encode()).rstrip(b"="), id="base64-offset1"),
        pytest.param(lambda n: base64.b64encode(b"xy" + n.encode()).rstrip(b"="), id="base64-offset2"),
        pytest.param(lambda n: base64.urlsafe_b64encode(b"\xff\xfe" + n.encode() + b"\xfb"), id="base64-urlsafe"),
        pytest.param(lambda n: json.dumps({"v": "".join(f"\\u{ord(c):04x}" for c in n)}).replace("\\\\", "\\").encode(), id="json-escaped"),
        pytest.param(lambda n: ("{\"v\":\"" + n[:4] + "".join(f"\\u{ord(c):04X}" for c in n[4:]) + "\"}").encode(), id="json-partial-escape"),
        pytest.param(lambda n: n.encode("utf-16-le"), id="utf16le"),
        pytest.param(lambda n: n.encode("utf-16-be"), id="utf16be"),
        pytest.param(lambda n: n.encode().hex().encode(), id="hex"),
        pytest.param(lambda n: "".join(f"&#x{ord(c):x};" for c in n).encode(), id="html-entities"),
    ],
)
def test_matcher_detects_encoded_variants(encode) -> None:
    nonce = _nonce()
    payload = b"prefix&" + encode(nonce) + b"&suffix"
    assert SentinelMatcher(nonce).matches_bytes(payload)


def test_matcher_ignores_unrelated_values() -> None:
    nonce = _nonce()
    other = _nonce()
    matcher = SentinelMatcher(nonce)
    for payload in (other.encode(), base64.b64encode(other.encode()), other.encode("utf-16-le"),
                    b"page_view&ts=1", b""):
        assert not matcher.matches_bytes(payload)


def test_matcher_detects_hashed_candidate_values() -> None:
    nonce = _nonce()
    email = f"{nonce}@example.invalid"
    digest = hashlib.sha256(email.encode()).hexdigest()
    assert SentinelMatcher(nonce, hash_candidates=[email]).matches_bytes(b'{"em":"' + digest.encode() + b'"}')


@pytest.mark.parametrize(
    "build, content_type, content_encoding, expected, legacy_detects",
    [
        pytest.param(lambda n: f"email={n}".encode(), "application/x-www-form-urlencoded", None, LEAK, True, id="form-raw"),
        pytest.param(lambda n: b'{"event":"page_view"}', "application/json", None, CLEAN, False, id="clean-json"),
        pytest.param(lambda n: gzip.compress(n.encode()), "application/octet-stream", None, LEAK, False, id="gzip-magic"),
        pytest.param(lambda n: gzip.compress(b'{"event":"x"}'), "application/octet-stream", None, CLEAN, False, id="gzip-clean"),
        pytest.param(lambda n: zlib.compress(n.encode()), None, None, LEAK, False, id="zlib"),
        pytest.param(lambda n: zlib.compress(n.encode())[2:-4], "text/plain", "deflate", LEAK, False, id="raw-deflate-header"),
        pytest.param(lambda n: gzip.compress(n.encode()), "text/plain", "gzip", LEAK, False, id="content-encoding-gzip"),
        pytest.param(lambda n: n.encode(), "text/plain", "br", LEAK, True, id="br-but-raw-visible"),
        pytest.param(lambda n: secrets.token_bytes(64), "text/plain", "br", OPAQUE, False, id="br-opaque"),
        pytest.param(lambda n: b"\x28\xb5\x2f\xfd" + secrets.token_bytes(40), None, None, OPAQUE, False, id="zstd"),
        pytest.param(lambda n: secrets.token_bytes(256), None, None, OPAQUE, False, id="random-binary"),
        pytest.param(lambda n: b"plain text", "application/x-protobuf", None, OPAQUE, False, id="non-text-type"),
        pytest.param(lambda n: b"\xc3\x28 invalid", "text/plain", None, OPAQUE, False, id="invalid-utf8"),
        pytest.param(lambda n: json.dumps({"d": base64.b64encode(gzip.compress(n.encode() * 3)).decode()}).encode(),
                     "application/json", None, LEAK, False, id="base64-of-gzip"),
        pytest.param(lambda n: json.dumps({"d": base64.b64encode(gzip.compress(secrets.token_bytes(40)) + secrets.token_bytes(64)).decode()}).encode(),
                     "application/json", None, OPAQUE, False, id="base64-opaque-run"),
        pytest.param(lambda n: json.dumps({"id": hashlib.sha256(b"x").hexdigest()}).encode(),
                     "application/json", None, CLEAN, False, id="hash-like-hex"),
        pytest.param(lambda n: b"--b\r\nContent-Disposition: form-data; name=\"e\"\r\n\r\n" + n.encode() + b"\r\n--b--\r\n",
                     "multipart/form-data; boundary=b", None, LEAK, True, id="multipart"),
    ],
)
def test_classifier(build, content_type, content_encoding, expected, legacy_detects) -> None:
    nonce = _nonce()
    body = build(nonce)
    matcher = SentinelMatcher(nonce)
    assert classify_payload(matcher, body, content_type=content_type, content_encoding=content_encoding) == expected
    # Legacy smoke logic only matched the raw nonce in a UTF-8 decoded body.
    assert _legacy_match(nonce, body) is legacy_detects


def test_classifier_none_and_empty_are_clean() -> None:
    matcher = SentinelMatcher(_nonce())
    assert classify_payload(matcher, None) == CLEAN
    assert classify_payload(matcher, b"") == CLEAN


def test_sha256_snapshot_reports_counts_only(tmp_path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "one.json").write_text("1", encoding="utf-8")
    (tmp_path / "b.json").write_text("2", encoding="utf-8")
    before = snapshot_sha256([tmp_path / "a", tmp_path / "b.json"])
    assert compare_sha256_snapshots(before, snapshot_sha256([tmp_path / "a", tmp_path / "b.json"]))["identical"]
    (tmp_path / "a" / "one.json").write_text("changed", encoding="utf-8")
    (tmp_path / "a" / "two.json").write_text("new", encoding="utf-8")
    (tmp_path / "b.json").unlink()
    diff = compare_sha256_snapshots(before, snapshot_sha256([tmp_path / "a", tmp_path / "b.json"]))
    assert diff == {"added": 1, "removed": 1, "changed": 1, "unreadable": 0, "identical": False}
    assert all(not isinstance(value, (list, str)) for value in diff.values())


def test_monitor_rejects_non_alnum_nonce() -> None:
    with pytest.raises(ValueError):
        SentinelNetworkMonitor("not-alnum-nonce-123", [], "abc")


def test_result_is_unverified_until_every_phase_completes() -> None:
    monitor = SentinelNetworkMonitor(_nonce(), ["phone"], "abc")
    result = monitor.result()
    assert result["sentinel_network_leak"] == UNVERIFIED
    assert result["extension_non_loopback_requests"] == UNVERIFIED
    assert result["undetectable_fields_count"] == UNVERIFIED
    assert result["status"] == UNVERIFIED


@pytest.mark.parametrize("kind", ["opaque", "sentinel"])
def test_prefill_blocker_prevents_delivery_through_clear_and_unload(tmp_path, kind):
    nonce = _nonce()
    with _browser(tmp_path) as h:
        page = h.context.pages[0]
        monitor = SentinelNetworkMonitor(nonce, [], h.extension_id)
        monitor.start(h.context)
        page.goto(h.url("pilot_monitor_fixtures/blank.html"))
        assert monitor.prefill_blocking_reasons(page) == []
        monitor.enable_pre_send_blocking()
        monitor.mark_fill_started(["email"])
        page.evaluate("""({port, nonce, kind}) => {
          const url = `http://external.test:${port}/sink`;
          const send = () => navigator.sendBeacon(url, new Blob(
            [kind === 'opaque' ? new Uint8Array([0, 255, 3]) : nonce],
            {type: 'application/octet-stream'}));
          send(); setTimeout(send, 300);
          addEventListener('pagehide', send);
        }""", {"port": h.port, "nonce": nonce, "kind": kind})
        monitor.mark_cleared()
        monitor.wait_quiet(min_seconds=0.6, quiet_seconds=0.3)
        result = monitor.result()
        assert h.server.received_posts == 0, result
    assert result["pre_send_blocking_enabled"] is True
    assert result["unload_network_blocking_enabled"] is True
    assert result["blocked_opaque_requests" if kind == "opaque" else "blocked_sentinel_attempts"] >= 2
    assert result["sentinel_network_leak"] in (0, UNVERIFIED)
    assert result["opaque_requests"] == 0
    assert result["status"] == (UNVERIFIED if kind == "opaque" else "FAIL")


# --------------------------------------------------------------------------
# Local browser harness
# --------------------------------------------------------------------------

class _Handler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def do_POST(self) -> None:
        self.server.received_posts += 1
        length = int(self.headers.get("content-length") or 0)
        if length:
            self.rfile.read(length)
        self.send_response(204)
        self.end_headers()


@contextmanager
def _http_server() -> Iterator[ThreadingHTTPServer]:
    handler = lambda *a, **k: _Handler(*a, directory=str(TESTS_ROOT), **k)  # noqa: E731
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.received_posts = 0
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@contextmanager
def _websocket_server() -> Iterator[int]:
    """Minimal RFC 6455 handshake; frames are read and discarded."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(0.2)
    stop = threading.Event()
    clients: list[socket.socket] = []

    def serve() -> None:
        while not stop.is_set():
            try:
                client, _ = listener.accept()
            except OSError:
                continue
            clients.append(client)
            request = client.recv(4096).decode("latin-1")
            key = next(line.split(":", 1)[1].strip() for line in request.split("\r\n")
                       if line.lower().startswith("sec-websocket-key"))
            accept = base64.b64encode(hashlib.sha1(
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
            client.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                            f"Connection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n").encode())

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield listener.getsockname()[1]
    finally:
        stop.set()
        thread.join(timeout=5)
        for client in clients:
            client.close()
        listener.close()


@dataclass
class Harness:
    context: object
    port: int
    extension_id: str
    server: object

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}/{path}"

    def live_worker(self):
        """The current extension worker; Chromium may have stopped/restarted it.

        Never reuse a Worker object across steps.  If the worker is stopped and
        nothing woke it, start it through CDP (test-only) instead of navigating.
        """
        prefix = f"chrome-extension://{self.extension_id}/"
        for attempt in range(5):
            worker = live_extension_worker(self.context, prefix, timeout=2)
            if worker is not None:
                try:
                    evaluate_worker(worker, "() => true", timeout=2)
                    return worker
                except Exception:
                    pass
            page = self.context.pages[0] if self.context.pages else self.context.new_page()
            cdp = self.context.new_cdp_session(page)
            try:
                cdp.send("ServiceWorker.enable")
                cdp.send("ServiceWorker.startWorker", {"scopeURL": prefix})
            finally:
                cdp.detach()
        raise AssertionError("extension_worker_not_found")


# Like the real extension, a content script messages the worker on every
# matching page load, so navigation wakes a worker that Chromium stopped.
_FIXTURE_CONTENT_JS = "chrome.runtime.sendMessage({type: 'fixture-ping'}).catch(() => 0);\n"
_FIXTURE_SW_JS = (
    "self.addEventListener('install', () => {});\n"
    "chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {\n"
    "  sendResponse({ok: true});\n"
    "});\n"
)


def _discover_extension_id(context, port: int) -> str:
    worker = live_extension_worker(context, "chrome-extension://", timeout=5)
    if worker is None:
        # Stopped before we looked: wake it through the content script, then
        # return the tab to about:blank so monitors still attach before navigation.
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(f"http://127.0.0.1:{port}/pilot_monitor_fixtures/blank.html", wait_until="load")
        worker = live_extension_worker(context, "chrome-extension://", timeout=10)
        page.goto("about:blank")
    assert worker is not None, "extension_worker_not_found"
    return urlsplit(worker.url).hostname or ""


@contextmanager
def _browser(tmp_path: Path, *, sw_events: bool = True) -> Iterator[Harness]:
    extension_dir = tmp_path / "probe-extension"
    extension_dir.mkdir()
    (extension_dir / "manifest.json").write_text(json.dumps({
        "manifest_version": 3, "name": "monitor fixture", "version": "1",
        "background": {"service_worker": "sw.js"}, "permissions": ["storage"],
        "content_scripts": [{
            "matches": ["http://127.0.0.1/*", "http://external.test/*"],
            "js": ["content.js"], "run_at": "document_start",
        }],
    }), encoding="utf-8")
    (extension_dir / "sw.js").write_text(_FIXTURE_SW_JS, encoding="utf-8")
    (extension_dir / "content.js").write_text(_FIXTURE_CONTENT_JS, encoding="utf-8")
    guard = service_worker_network_events() if sw_events else nullcontext()
    with _http_server() as server, guard, sync_playwright() as playwright:
        port = server.server_port
        context = playwright.chromium.launch_persistent_context(
            str(tmp_path / "profile"),
            channel="chromium",
            headless=True,
            args=[
                f"--disable-extensions-except={extension_dir}",
                f"--load-extension={extension_dir}",
                "--host-resolver-rules=MAP external.test 127.0.0.1, MAP * ~NOTFOUND, "
                "EXCLUDE 127.0.0.1, EXCLUDE localhost",
            ],
        )
        try:
            yield Harness(context, port, _discover_extension_id(context, port), server)
        finally:
            context.close()


def _attach_legacy(context, page, marker: str) -> dict[str, object]:
    """The pre-change smoke monitor logic, kept to prove what it missed."""
    state: dict[str, object] = {"leak": 0, "ext": 0, "stopped": False}

    def record_request(request) -> None:
        if state["stopped"]:
            return
        url = str(request.url or "")
        try:
            body = str(request.post_data or "")
        except Exception:
            body = ""
        if marker in url or marker in body:
            state["leak"] += 1
        parsed = urlsplit(url)
        if parsed.hostname not in {"127.0.0.1", "::1"} and parsed.scheme != "chrome-extension":
            try:
                has_frame = request.frame is not None
            except Exception:
                has_frame = False
            if not has_frame:
                state["ext"] += 1

    def record_websocket(websocket) -> None:
        def sent(payload) -> None:
            if not state["stopped"] and marker in str(payload or ""):
                state["leak"] += 1
        websocket.on("framesent", sent)

    context.on("request", record_request)
    page.on("websocket", record_websocket)
    return state


def _run_channel(h: Harness, script: str, *, arm: str | None = None, quiet: float = 0.5,
                 arg: object = None, page_path: str = CHANNELS):
    nonce = _nonce()
    page = h.context.pages[0] if h.context.pages else h.context.new_page()
    legacy = _attach_legacy(h.context, page, nonce)
    monitor = SentinelNetworkMonitor(nonce, ["phone"], h.extension_id)
    monitor.start(h.context)
    page.goto(h.url(page_path), wait_until="load")
    assert monitor.prefill_blocking_reasons(page) == []
    if arm:
        page.evaluate(arm)
    monitor.mark_fill_started(["email"])
    page.fill("#email", f"{nonce}@example.invalid")
    page.evaluate(script, arg)
    page.wait_for_timeout(300)
    page.fill("#email", "")  # rollback
    legacy["stopped"] = True  # the legacy smoke stopped measuring at rollback
    monitor.mark_cleared()
    monitor.wait_quiet(min_seconds=quiet, quiet_seconds=0.5)
    return monitor.result(), legacy


# --------------------------------------------------------------------------
# Browser tests
# --------------------------------------------------------------------------

def test_normal_page_load_traffic_is_clean_and_counted_separately(tmp_path) -> None:
    with _browser(tmp_path) as h:
        script = """port => { const img = new Image();
          img.src = 'http://external.test:' + port + '/pilot_monitor_fixtures/pixel.gif';
          return window.channels.clean(); }"""
        result, legacy = _run_channel(h, script, arg=h.port)
    assert result["sentinel_network_leak"] == 0
    assert result["extension_non_loopback_requests"] == 0
    assert result["page_external_requests"] >= 1
    assert result["page_requests_total"] >= 4
    assert result["opaque_requests"] == 0
    assert result["undetectable_fields_count"] == 0
    assert result["status"] == "PASS", result["unverified_reasons"]


def test_fetch_post_raw_is_leak(tmp_path) -> None:
    with _browser(tmp_path) as h:
        result, legacy = _run_channel(h, "() => window.channels.fetchRaw()")
    assert result["sentinel_network_leak"] == 1
    assert result["status"] == "FAIL"
    assert legacy["leak"] == 1  # raw body: legacy logic also caught this one


def test_fetch_url_query_is_leak(tmp_path) -> None:
    with _browser(tmp_path) as h:
        result, _ = _run_channel(h, "() => window.channels.fetchUrl()")
    assert result["sentinel_network_leak"] == 1


def test_xhr_fully_percent_encoded_form_is_leak(tmp_path) -> None:
    with _browser(tmp_path) as h:
        result, legacy = _run_channel(h, "() => window.channels.xhrForm()")
    assert result["sentinel_network_leak"] == 1
    assert legacy["leak"] == 0


def test_send_beacon_string_is_leak(tmp_path) -> None:
    with _browser(tmp_path) as h:
        result, legacy = _run_channel(h, "() => window.channels.beacon()")
    assert result["sentinel_network_leak"] == 1
    assert legacy["leak"] == 1  # string beacon bodies were visible to legacy logic


def test_send_beacon_blob_body_is_unverified_not_clean(tmp_path) -> None:
    with _browser(tmp_path) as h:
        result, legacy = _run_channel(h, "() => window.channels.blobBeacon()")
    # Playwright exposes no bytes for Blob bodies: must not be reported as 0.
    assert result["sentinel_network_leak"] == UNVERIFIED
    assert result["opaque_requests"] == 1
    assert legacy["leak"] == 0  # legacy reported this as clean


@pytest.mark.parametrize("offset", [0, 1, 2])
def test_base64_encoded_body_is_leak(tmp_path, offset) -> None:
    with _browser(tmp_path) as h:
        result, legacy = _run_channel(h, "offset => window.channels.base64(offset)", arg=offset)
    assert result["sentinel_network_leak"] == 1
    assert legacy["leak"] == 0


def test_json_unicode_escaped_body_is_leak(tmp_path) -> None:
    with _browser(tmp_path) as h:
        result, legacy = _run_channel(h, "() => window.channels.jsonEscaped()")
    assert result["sentinel_network_leak"] == 1
    assert legacy["leak"] == 0


def test_gzip_body_is_decompressed_and_detected(tmp_path) -> None:
    with _browser(tmp_path) as h:
        result, legacy = _run_channel(h, "() => window.channels.gzip()")
    assert result["sentinel_network_leak"] == 1
    assert legacy["leak"] == 0


def test_clean_gzip_body_is_clean(tmp_path) -> None:
    with _browser(tmp_path) as h:
        result, _ = _run_channel(h, "() => window.channels.gzip('{\"event\":\"page_view\"}')")
    assert result["sentinel_network_leak"] == 0
    assert result["opaque_requests"] == 0
    assert result["status"] == "PASS", result["unverified_reasons"]


def test_binary_opaque_body_is_unverified(tmp_path) -> None:
    with _browser(tmp_path) as h:
        result, legacy = _run_channel(h, "() => window.channels.binary()")
    assert result["sentinel_network_leak"] == UNVERIFIED
    assert result["status"] == UNVERIFIED
    assert "opaque_requests_after_fill" in result["unverified_reasons"]
    assert legacy["leak"] == 0


def test_websocket_text_frame_on_main_page_is_leak(tmp_path) -> None:
    with _websocket_server() as ws_port, _browser(tmp_path) as h:
        result, legacy = _run_channel(h, "port => window.channels.websocket(port)", arg=ws_port)
    assert result["sentinel_network_leak"] == 1
    assert result["websocket_frames_sent"] == 1
    assert legacy["leak"] == 1


def test_websocket_from_second_page_is_leak(tmp_path) -> None:
    with _websocket_server() as ws_port, _browser(tmp_path) as h:
        script = """async ([port, url]) => {
          const value = document.getElementById('email').value;
          const popup = window.open(url);
          await new Promise(r => popup.addEventListener('load', r));
          const ws = new popup.WebSocket('ws://127.0.0.1:' + port + '/');
          await new Promise(r => { ws.onopen = r; });
          ws.send(value);
          await new Promise(r => setTimeout(r, 200));
        }"""
        result, legacy = _run_channel(h, script, arg=[ws_port, h.url("pilot_monitor_fixtures/blank.html")])
    assert result["sentinel_network_leak"] == 1
    assert legacy["leak"] == 0  # legacy watched only the first page


def test_dedicated_worker_fetch_is_leak_and_attributed_to_page(tmp_path) -> None:
    with _browser(tmp_path) as h:
        result, _ = _run_channel(h, "() => window.channels.workerFetch()")
    assert result["sentinel_network_leak"] == 1
    assert result["unattributed_requests"] == 0


def test_delayed_autosave_after_clear_is_leak(tmp_path) -> None:
    with _browser(tmp_path) as h:
        result, legacy = _run_channel(
            h, "() => undefined", arm="() => window.channels.armAutosave(5000)", quiet=6)
    assert result["sentinel_network_leak"] == 1
    assert result["requests_after_clear"] >= 1
    assert legacy["leak"] == 0


def test_unload_beacon_at_tab_close_is_leak(tmp_path) -> None:
    with _browser(tmp_path) as h:
        result, legacy = _run_channel(
            h, "() => undefined", arm="() => window.channels.armUnloadBeacon()")
    assert result["sentinel_network_leak"] == 1
    assert legacy["leak"] == 0


def test_extension_worker_non_loopback_request_is_counted(tmp_path) -> None:
    with _browser(tmp_path) as h:
        script = "() => undefined"
        nonce = _nonce()
        page = h.context.pages[0]
        monitor = SentinelNetworkMonitor(nonce, [], h.extension_id)
        monitor.start(h.context)
        page.goto(h.url(CHANNELS), wait_until="load")
        assert monitor.prefill_blocking_reasons(page) == []
        monitor.mark_fill_started(["email"])
        h.live_worker().evaluate(
            "url => fetch(url, {method: 'POST', body: 'x'}).catch(() => 0)",
            f"http://external.test:{h.port}/sink",
        )
        page.evaluate(script)
        monitor.mark_cleared()
        monitor.wait_quiet(min_seconds=0.5, quiet_seconds=0.5)
        result = monitor.result()
    assert result["extension_non_loopback_requests"] == 1
    assert result["extension_requests_total"] >= 1
    assert result["status"] == "FAIL"


def _stop_extension_worker(h: Harness, page) -> None:
    """Deterministically stop the extension worker the way Chromium may (CDP).

    Playwright keeps a CDP-stopped worker listed (its evaluate does not answer
    until the worker restarts), so wait for the CDP running status instead of
    the worker list.  The worker is deliberately not evaluated before the stop:
    Playwright 1.52 cannot evaluate again in a restarted worker whose previous
    execution context was used (the monitor then fails closed, UNVERIFIED).
    """
    prefix = f"chrome-extension://{h.extension_id}/"
    assert live_extension_worker(h.context, prefix, timeout=5) is not None
    status: dict[str, str] = {}

    def on_versions(event) -> None:
        for version in event.get("versions", []):
            if str(version.get("scriptURL", "")).startswith(prefix):
                status["running"] = str(version.get("runningStatus"))
                status["state"] = str(version.get("status"))

    cdp = h.context.new_cdp_session(page)
    try:
        cdp.on("ServiceWorker.workerVersionUpdated", on_versions)
        cdp.send("ServiceWorker.enable")
        for _ in range(100):  # stop only an installed, activated worker
            if status.get("state") == "activated" and status.get("running") == "running":
                break
            page.wait_for_timeout(50)
        cdp.send("ServiceWorker.stopAllWorkers")
        for _ in range(100):
            if status.get("running") == "stopped":
                break
            page.wait_for_timeout(50)
    finally:
        cdp.detach()
    assert status.get("running") == "stopped", status


def test_probe_recovers_when_worker_is_restarted_by_navigation(tmp_path) -> None:
    with _browser(tmp_path) as h:
        page = h.context.pages[0]
        _stop_extension_worker(h, page)
        nonce = _nonce()
        monitor = SentinelNetworkMonitor(nonce, [], h.extension_id)
        monitor.start(h.context)  # no live worker: the start probe cannot be observed
        assert "service_worker_network_unobservable" in monitor.result()["unverified_reasons"]
        # The fixture content script messages the worker, which restarts it.
        page.goto(h.url(CHANNELS), wait_until="load")
        assert monitor.prefill_blocking_reasons(page) == []
        monitor.mark_fill_started(["email"])
        page.fill("#email", f"{nonce}@example.invalid")
        page.fill("#email", "")
        monitor.mark_cleared()
        monitor.wait_quiet(min_seconds=0.3, quiet_seconds=0.3)
        result = monitor.result()
    assert result["status"] == "PASS", result["unverified_reasons"]
    assert result["extension_non_loopback_requests"] == 0


def test_probe_without_worker_restart_is_unverified(tmp_path) -> None:
    with _browser(tmp_path) as h:
        page = h.context.pages[0]
        _stop_extension_worker(h, page)
        monitor = SentinelNetworkMonitor(_nonce(), [], h.extension_id, probe_timeout_seconds=2)
        monitor.start(h.context)
        # localhost is not matched by the content script: nothing wakes the worker.
        page.goto(f"http://localhost:{h.port}/{CHANNELS}", wait_until="load")
        reasons = monitor.prefill_blocking_reasons(page)
        monitor.mark_fill_started(["email"])
        monitor.mark_cleared()
        monitor.wait_quiet(min_seconds=0.3, quiet_seconds=0.3)
        result = monitor.result()
    assert "extension_worker_not_found" in reasons
    assert "service_worker_network_unobservable" in reasons
    assert result["status"] == UNVERIFIED
    assert result["status"] != "PASS"
    assert "service_worker_network_unobservable" in result["unverified_reasons"]
    assert result["extension_non_loopback_requests"] == UNVERIFIED


def test_without_service_worker_network_events_extension_metric_is_unverified(tmp_path) -> None:
    with _browser(tmp_path, sw_events=False) as h:
        nonce = _nonce()
        page = h.context.pages[0]
        legacy = _attach_legacy(h.context, page, nonce)
        monitor = SentinelNetworkMonitor(nonce, [], h.extension_id)
        monitor.start(h.context)
        page.goto(h.url(CHANNELS), wait_until="load")
        assert "service_worker_network_unobservable" in monitor.prefill_blocking_reasons(page)
        monitor.mark_fill_started(["email"])
        h.live_worker().evaluate(
            "url => fetch(url, {method: 'POST', body: 'x'}).catch(() => 0)",
            f"http://external.test:{h.port}/sink",
        )
        monitor.mark_cleared()
        monitor.wait_quiet(min_seconds=0.5, quiet_seconds=0.5)
        result = monitor.result()
    assert result["extension_non_loopback_requests"] == UNVERIFIED
    assert result["sentinel_network_leak"] == UNVERIFIED
    assert legacy["ext"] == 0  # legacy saw nothing and would have reported 0


def test_page_service_worker_blocks_fill_and_is_not_extension_traffic(tmp_path) -> None:
    with _browser(tmp_path) as h:
        nonce = _nonce()
        page = h.context.pages[0]
        legacy = _attach_legacy(h.context, page, nonce)
        monitor = SentinelNetworkMonitor(nonce, [], h.extension_id)
        monitor.start(h.context)
        page.goto(h.url("pilot_monitor_fixtures/service_worker_page.html"), wait_until="load")
        page.evaluate("() => window.swReady")
        reasons = monitor.prefill_blocking_reasons(page)
        page_sw = next(w for w in h.context.service_workers if w.url.startswith("http"))
        page_sw.evaluate(
            "url => fetch(url, {method: 'POST', body: 'x'}).catch(() => 0)",
            f"http://external.test:{h.port}/sink",
        )
        page.wait_for_timeout(500)
        counts = dict(monitor.counts)
    assert "page_service_worker_registered" in reasons
    assert counts["page_service_worker_requests"] >= 1
    assert counts["extension_non_loopback_requests"] == 0
    assert counts["unattributed_requests"] == 0
    assert legacy["ext"] >= 1  # legacy misclassified page SW traffic as extension traffic


@pytest.mark.parametrize(
    "path, reason",
    [
        ("pilot_monitor_fixtures/cross_origin_iframe.html", "cross_origin_iframe_present"),
        ("pilot_monitor_fixtures/rtc.html", "rtc_peer_connection_constructed"),
        ("pilot_monitor_fixtures/rtc_iframe_bypass.html", "rtc_peer_connection_constructed"),
    ],
)
def test_prefill_blocks(tmp_path, path, reason) -> None:
    with _browser(tmp_path) as h:
        page = h.context.pages[0]
        monitor = SentinelNetworkMonitor(_nonce(), [], h.extension_id)
        monitor.start(h.context)
        page.goto(h.url(path), wait_until="load")
        page.wait_for_timeout(300)
        reasons = monitor.prefill_blocking_reasons(page)
    assert reason in reasons


def test_monitor_attached_after_navigation_blocks(tmp_path) -> None:
    with _browser(tmp_path) as h:
        page = h.context.pages[0]
        page.goto(h.url(CHANNELS), wait_until="load")
        monitor = SentinelNetworkMonitor(_nonce(), [], h.extension_id)
        monitor.start(h.context)
        reasons = monitor.prefill_blocking_reasons(page)
    assert "monitor_attached_after_navigation" in reasons
    assert "frame_without_monitor_hook" in reasons


def test_undetectable_field_marks_result_unverified(tmp_path) -> None:
    with _browser(tmp_path) as h:
        nonce = _nonce()
        page = h.context.pages[0]
        monitor = SentinelNetworkMonitor(nonce, ["phone", "postal_code"], h.extension_id)
        monitor.start(h.context)
        page.goto(h.url(CHANNELS), wait_until="load")
        assert monitor.prefill_blocking_reasons(page) == []
        monitor.mark_fill_started(["email", "phone"])
        monitor.mark_cleared()
        monitor.wait_quiet(min_seconds=0.2, quiet_seconds=0.3)
        result = monitor.result()
    assert result["sentinel_network_leak"] == 0
    assert result["undetectable_fields_count"] == 1
    assert result["status"] == UNVERIFIED


# --------------------------------------------------------------------------
# Residue checks
# --------------------------------------------------------------------------

_SEED = r"""
async nonce => {
  document.getElementById('email').value = nonce + '@example.invalid';
  localStorage.setItem('draft', JSON.stringify({email: nonce}));
  sessionStorage.setItem('s', encodeURIComponent('x ' + nonce));
  document.cookie = 'c=' + btoa('zz' + nonce).replace(/=+$/, '') + '; path=/';
  await new Promise((resolve, reject) => {
    const open = indexedDB.open('drafts', 1);
    open.onupgradeneeded = () => open.result.createObjectStore('forms');
    open.onsuccess = () => {
      const tx = open.result.transaction('forms', 'readwrite');
      tx.objectStore('forms').put({nested: {list: [1, new Blob([nonce])]}}, 'k1');
      tx.oncomplete = () => { open.result.close(); resolve(); };
      tx.onerror = () => reject(tx.error);
    };
    open.onerror = () => reject(open.error);
  });
  const cache = await caches.open('c1');
  await cache.put('/pilot_monitor_fixtures/cached', new Response('body ' + nonce));
}
"""


def test_residue_counts_every_area(tmp_path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    with _browser(tmp_path) as h:
        nonce = _nonce()
        page = h.context.pages[0]
        page.goto(h.url(CHANNELS), wait_until="load")
        page.evaluate(_SEED, nonce)
        h.live_worker().evaluate("v => chrome.storage.session.set({kenshoSessionProfile: {email: v}})", nonce)
        (evidence / "run.json").write_text(json.dumps({"x": nonce.upper()}), encoding="utf-8")
        (evidence / "clean.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
        result = check_sentinel_residue(h.context, nonce, extension_id=h.extension_id,
                                        evidence_dirs=[evidence])
    assert result["dom"] >= 1
    assert result["local_storage"] == 1
    assert result["session_storage"] == 1
    assert result["indexeddb"] == 1
    assert result["cache_storage"] == 1
    assert result["document_cookie"] == 1
    assert result["context_cookies"] == 1
    assert result["extension_storage"] == 1
    assert result["evidence_files"] == 1
    assert result["status"] == "FAIL"
    assert nonce not in json.dumps(result)


def test_residue_clean_page_passes(tmp_path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "clean.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    with _browser(tmp_path) as h:
        page = h.context.pages[0]
        page.goto(h.url(CHANNELS), wait_until="load")
        result = check_sentinel_residue(h.context, _nonce(), extension_id=h.extension_id,
                                        evidence_dirs=[evidence])
    assert result["total"] == 0
    assert result["status"] == "PASS"


def test_residue_indexeddb_without_enumeration_is_unverified(tmp_path) -> None:
    with _browser(tmp_path) as h:
        page = h.context.pages[0]
        page.goto(h.url(CHANNELS), wait_until="load")
        page.evaluate("() => { delete IDBFactory.prototype.databases; }")
        result = check_sentinel_residue(h.context, _nonce(), extension_id=h.extension_id)
    assert result["indexeddb"] == UNVERIFIED
    assert result["status"] == UNVERIFIED


def test_residue_without_extension_worker_is_unverified(tmp_path) -> None:
    with _browser(tmp_path) as h:
        page = h.context.pages[0]
        page.goto(h.url(CHANNELS), wait_until="load")
        result = check_sentinel_residue(h.context, _nonce(), extension_id="nonexistent")
    assert result["extension_storage"] == UNVERIFIED
    assert result["status"] == UNVERIFIED
