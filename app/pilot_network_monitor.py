"""Sentinel network leak monitor for the fake-sentinel, non-submit pilot.

Principles:
- Anything that cannot be observed is reported as ``"UNVERIFIED"``, never 0.
- URLs, bodies, frames, header values and sentinel values are never stored or
  logged.  Only counts and fixed category names leave this module.
- Service Worker network traffic (including the extension worker) is only
  visible to Playwright when the driver was started with
  ``PW_EXPERIMENTAL_SERVICE_WORKER_NETWORK_EVENTS`` set.  Use
  :func:`service_worker_network_events` around ``sync_playwright()``.  The
  monitor proves observability with a loopback probe from the extension worker
  and fails closed when the probe is not seen.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import html
import os
import re
import secrets
import threading
import time
import zlib
from contextlib import contextmanager
from typing import Iterable, Iterator
from urllib.parse import unquote_to_bytes, urlsplit

CLEAN = "CLEAN"
LEAK = "LEAK"
OPAQUE = "OPAQUE"
UNVERIFIED = "UNVERIFIED"

SW_NETWORK_EVENTS_ENV = "PW_EXPERIMENTAL_SERVICE_WORKER_NETWORK_EVENTS"

_MIN_NONCE_LENGTH = 16
_MAX_DECOMPRESSED = 16 * 1024 * 1024
_MAX_DEPTH = 3
_MAX_ENCODED_RUNS = 64
_ENCODED_RUN = re.compile(rb"[A-Za-z0-9+/_-]{64,}={0,2}")
_HEX_RUN = re.compile(rb"^[0-9A-Fa-f]+$")
_JSON_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})")
_HASH_HEX_LENGTHS = {32, 40, 64, 128}
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "[::1]", "localhost"}
_NETWORK_SCHEMES = {"http", "https", "ws", "wss"}
_BODYLESS_METHODS = {"GET", "HEAD", "OPTIONS"}
_TEXT_TYPES = {
    "application/json", "application/x-www-form-urlencoded", "multipart/form-data",
    "application/javascript", "application/xml", "application/csp-report",
    "application/reports+json", "application/x-ndjson", "application/ld+json",
}


@contextmanager
def service_worker_network_events() -> Iterator[None]:
    """Enable Playwright SW network events for drivers started inside the block.

    The Playwright driver reads the variable when it starts, so wrap
    ``sync_playwright()`` (not only the monitor) with this context manager.
    """
    previous = os.environ.get(SW_NETWORK_EVENTS_ENV)
    os.environ[SW_NETWORK_EVENTS_ENV] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(SW_NETWORK_EVENTS_ENV, None)
        else:
            os.environ[SW_NETWORK_EVENTS_ENV] = previous


def _validate_nonce(nonce: str) -> str:
    if not isinstance(nonce, str) or len(nonce) < _MIN_NONCE_LENGTH:
        raise ValueError("sentinel_nonce_too_short")
    if not (nonce.isascii() and nonce.isalnum()):
        raise ValueError("sentinel_nonce_must_be_ascii_alnum")
    return nonce


def _base64_needles(raw: bytes) -> set[bytes]:
    """Base64 substrings that encode ``raw`` at every byte alignment."""
    needles: set[bytes] = set()
    for offset in range(3):
        encoded = base64.b64encode(b"\0" * offset + raw + b"\0\0")
        start = -(-8 * offset // 6)
        end = (8 * (offset + len(raw))) // 6
        piece = encoded[start:end]
        needles.add(piece)
        needles.add(piece.translate(bytes.maketrans(b"+/", b"-_")))
    return {needle for needle in needles if len(needle) >= 8}


class SentinelMatcher:
    """Detects a sentinel nonce in common encodings without storing payloads."""

    def __init__(self, nonce: str, *, hash_candidates: Iterable[str] = ()) -> None:
        self._nonce = _validate_nonce(nonce)
        lowered = nonce.lower()
        self._ci_ascii = lowered.encode("ascii")
        self._ci_hex = lowered.encode("ascii").hex().encode("ascii")
        self._ci_utf16 = {lowered.encode("utf-16-le"), lowered.encode("utf-16-be")}
        cs: set[bytes] = set()
        for variant in {nonce, nonce.lower(), nonce.upper()}:
            cs |= _base64_needles(variant.encode("ascii"))
            cs |= _base64_needles(variant.encode("utf-16-le"))
        self._cs_needles = cs
        digests: set[bytes] = set()
        for value in hash_candidates:
            text = str(value or "")
            for form in {text, text.strip(), text.strip().lower()}:
                if not form:
                    continue
                data = form.encode("utf-8")
                for name in ("md5", "sha1", "sha256"):
                    digests.add(hashlib.new(name, data).hexdigest().encode("ascii"))
        self._hash_needles = digests

    # --- needles for in-page (JS) scanning; never logged -------------------
    def js_needles(self) -> dict[str, list[str]]:
        lowered = self._nonce.lower()
        ci = {
            lowered,
            "".join(f"%{ord(c):02x}" for c in lowered),
            "".join(f"\\u{ord(c):04x}" for c in lowered),
            "".join(f"&#x{ord(c):x};" for c in lowered),
            "".join(f"&#{ord(c)};" for c in lowered),
            self._ci_hex.decode("ascii"),
        }
        cs = {needle.decode("ascii") for needle in self._cs_needles}
        cs |= {needle.decode("ascii") for needle in self._hash_needles}
        return {"ci": sorted(ci), "cs": sorted(cs)}

    # --- matching ----------------------------------------------------------
    def _match_flat(self, data: bytes) -> bool:
        lowered = data.lower()
        if self._ci_ascii in lowered or self._ci_hex in lowered:
            return True
        if any(needle in lowered for needle in self._ci_utf16):
            return True
        if any(needle in data for needle in self._cs_needles):
            return True
        return any(needle in lowered for needle in self._hash_needles)

    def matches_bytes(self, data: bytes) -> bool:
        if not data:
            return False
        if self._match_flat(data):
            return True
        for view in _byte_views(data):
            if self._match_flat(view):
                return True
        return False

    def matches_text(self, text: str) -> bool:
        if not text:
            return False
        return self.matches_bytes(text.encode("utf-8", "surrogatepass"))


def _json_unescape(text: str) -> str:
    return _JSON_ESCAPE.sub(lambda match: chr(int(match.group(1), 16)), text)


def _byte_views(data: bytes) -> list[bytes]:
    """Decoded views: percent, form '+', JSON \\u, HTML entities, UTF-16."""
    views: list[bytes] = []
    seen = {data}
    frontier = [data]
    for _ in range(2):
        next_frontier: list[bytes] = []
        for item in frontier:
            candidates = [
                unquote_to_bytes(item),
                unquote_to_bytes(item.replace(b"+", b" ")),
            ]
            text = item.decode("utf-8", "replace")
            candidates.append(_json_unescape(text).encode("utf-8", "replace"))
            candidates.append(html.unescape(text).encode("utf-8", "replace"))
            for candidate in candidates:
                if candidate not in seen:
                    seen.add(candidate)
                    views.append(candidate)
                    next_frontier.append(candidate)
        frontier = next_frontier
    if b"\0" in data:
        for start in (0, 1):
            for codec in ("utf-16-le", "utf-16-be"):
                decoded = data[start:].decode(codec, "replace").encode("utf-8", "replace")
                if decoded not in seen:
                    seen.add(decoded)
                    views.append(decoded)
    return views


def _media_type(content_type: str | None) -> str:
    return str(content_type or "").split(";", 1)[0].strip().lower()


def _is_text_media(media: str) -> bool:
    return (
        media.startswith("text/")
        or media in _TEXT_TYPES
        or media.endswith("+json")
        or media.endswith("+xml")
    )


def _decompress(data: bytes, kind: str) -> bytes | None:
    wbits = {"gzip": 16 + zlib.MAX_WBITS, "zlib": zlib.MAX_WBITS, "deflate": -zlib.MAX_WBITS}[kind]
    try:
        decompressor = zlib.decompressobj(wbits)
        out = decompressor.decompress(data, _MAX_DECOMPRESSED)
        if decompressor.unconsumed_tail or not decompressor.eof:
            return None
        return out
    except zlib.error:
        return None


def _looks_compressed(data: bytes) -> str | None:
    if data[:2] == b"\x1f\x8b":
        return "gzip"
    if len(data) >= 2 and data[0] == 0x78 and (data[0] * 256 + data[1]) % 31 == 0:
        return "zlib"
    if data[:4] == b"\x28\xb5\x2f\xfd":
        return "zstd"
    return None


def _decode_text(data: bytes) -> str | None:
    """Return text when ``data`` is reliably printable text, else ``None``."""
    candidates: list[str] = []
    try:
        candidates.append(data.decode("utf-8"))
    except UnicodeDecodeError:
        pass
    if not candidates and data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            candidates.append(data.decode("utf-16"))
        except UnicodeDecodeError:
            pass
    for text in candidates:
        if not text:
            return text
        control = sum(1 for ch in text if ord(ch) < 32 and ch not in "\t\n\r")
        if "\0" not in text and control <= len(text) * 0.01:
            return text
    return None


def _merge(verdicts: Iterable[str]) -> str:
    result = CLEAN
    for verdict in verdicts:
        if verdict == LEAK:
            return LEAK
        if verdict == OPAQUE:
            result = OPAQUE
    return result


def classify_payload(
    matcher: SentinelMatcher,
    data: bytes | str | None,
    *,
    content_type: str | None = None,
    content_encoding: str | None = None,
    _depth: int = 0,
) -> str:
    """Classify a payload as CLEAN, LEAK or OPAQUE (not reliably scannable)."""
    if data is None:
        return CLEAN
    if isinstance(data, str):
        data = data.encode("utf-8", "surrogatepass")
    if not data:
        return CLEAN
    if matcher.matches_bytes(data):
        return LEAK
    if _depth > _MAX_DEPTH:
        return OPAQUE
    encoding = str(content_encoding or "").strip().lower()
    if encoding and encoding != "identity":
        kind = {"gzip": "gzip", "x-gzip": "gzip", "deflate": "zlib"}.get(encoding)
        if kind is None:
            return OPAQUE
        inflated = _decompress(data, kind)
        if inflated is None and kind == "zlib":
            inflated = _decompress(data, "deflate")
        if inflated is None:
            return OPAQUE
        return classify_payload(matcher, inflated, content_type=content_type, _depth=_depth + 1)
    magic = _looks_compressed(data)
    if magic in ("gzip", "zlib"):
        inflated = _decompress(data, magic)
        if inflated is not None:
            return classify_payload(matcher, inflated, _depth=_depth + 1)
        if magic == "gzip":
            return OPAQUE
    elif magic == "zstd":
        return OPAQUE
    media = _media_type(content_type)
    if media and not _is_text_media(media):
        return OPAQUE
    text = _decode_text(data)
    if text is None:
        inflated = _decompress(data, "deflate")
        if inflated is not None and inflated:
            return classify_payload(matcher, inflated, _depth=_depth + 1)
        return OPAQUE
    return _classify_encoded_runs(matcher, data, _depth)


_WORDLIKE_STRETCH = re.compile(rb"[a-z_/-]{16,}")


def _plausibly_encoded(run: bytes) -> bool:
    """True when a long run looks like base64/hex data rather than words."""
    if _HEX_RUN.match(run):
        return True
    has_upper = any(65 <= c <= 90 for c in run)
    has_lower = any(97 <= c <= 122 for c in run)
    has_digit = any(48 <= c <= 57 for c in run)
    if not (has_upper and has_lower and has_digit):
        return False
    return _WORDLIKE_STRETCH.search(run) is None


def _classify_encoded_runs(matcher: SentinelMatcher, data: bytes, depth: int) -> str:
    """Decode long base64/hex runs (e.g. compressed replay payloads) and rescan."""
    runs: list[bytes] = []
    for view in [data, *_byte_views(data)[:2]]:
        runs.extend(match.group(0) for match in _ENCODED_RUN.finditer(view))
    if len(runs) > _MAX_ENCODED_RUNS:
        return OPAQUE
    verdicts: list[str] = []
    for run in dict.fromkeys(runs):
        body = run.rstrip(b"=")
        if not _plausibly_encoded(body):
            continue  # word-like path/identifier; already scanned as plain text
        if _HEX_RUN.match(body):
            if len(body) in _HASH_HEX_LENGTHS:
                continue  # hash-like identifier; hash candidates are matched directly
            try:
                decoded = binascii.unhexlify(body[: len(body) // 2 * 2])
            except (binascii.Error, ValueError):
                verdicts.append(OPAQUE)
                continue
        else:
            has_std = b"+" in body or b"/" in body
            has_url = b"-" in body or b"_" in body
            if has_std and has_url:
                verdicts.append(OPAQUE)
                continue
            usable = body[: len(body) // 4 * 4] if len(body) % 4 == 1 else body
            padded = usable + b"=" * (-len(usable) % 4)
            try:
                decoded = (
                    base64.urlsafe_b64decode(padded) if has_url else base64.b64decode(padded)
                )
            except (binascii.Error, ValueError):
                verdicts.append(OPAQUE)
                continue
        verdicts.append(classify_payload(matcher, decoded, _depth=depth + 1))
        if verdicts[-1] == LEAK:
            return LEAK
    return _merge(verdicts)


def live_extension_worker(context, prefix: str, *, timeout: float = 0.0):
    """Return a currently live Service Worker whose URL starts with ``prefix``.

    Chromium may stop an MV3 extension worker at any time (right after launch
    or when idle) and start a new instance later, so callers must re-acquire
    the worker per use instead of holding the first one.  Waits up to
    ``timeout`` seconds for a ``serviceworker`` event; never opens pages.
    Returns None when no worker appeared in time.  A listed worker may still
    be stopped (Playwright keeps it listed when the DevTools host survives a
    stop), so evaluate it only through :func:`evaluate_worker`.
    """
    if not prefix or context is None:
        return None
    deadline = time.monotonic() + max(float(timeout), 0.0)
    while True:
        try:
            workers = list(context.service_workers)
        except Exception:
            return None
        for worker in workers:
            try:
                if str(worker.url or "").startswith(prefix):
                    return worker
            except Exception:
                continue
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            context.wait_for_event("serviceworker", timeout=max(1, int(min(remaining, 0.5) * 1000)))
        except Exception:
            time.sleep(min(0.05, max(deadline - time.monotonic(), 0)))


def evaluate_worker(worker, expression: str, arg=None, *, timeout: float = 2.0):
    """``worker.evaluate`` bounded by ``timeout`` seconds.

    Playwright's ``Worker.evaluate`` has no timeout, and on a worker that
    Chromium stopped while it stays listed the call never returns.  Raises
    ``TimeoutError`` (or the evaluation error) instead of blocking forever.
    """
    impl = getattr(worker, "_impl_obj", None)
    run = getattr(worker, "_sync", None)
    if impl is None or run is None:  # not a sync-API wrapper (unexpected)
        return worker.evaluate(expression, arg)
    return run(asyncio.wait_for(impl.evaluate(expression, arg), max(float(timeout), 0.001)))


def _is_network_url(url: str) -> bool:
    try:
        return urlsplit(url).scheme.lower() in _NETWORK_SCHEMES
    except ValueError:
        return False


def _is_loopback(url: str) -> bool:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    return host in _LOOPBACK_HOSTS or host.endswith(".localhost")


def _origin(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    if parts.scheme in ("http", "https"):
        return f"{parts.scheme}://{parts.netloc}".lower()
    return ""


def _service_worker_url(request) -> str | None:
    """URL of the Service Worker that issued ``request`` (None if not a worker).

    Playwright 1.52's Python API does not expose ``Request.service_worker``,
    but the protocol initializer carries it.  Prefer the public property when a
    newer version provides it.
    """
    worker = None
    try:
        worker = getattr(request, "service_worker", None)
    except Exception:
        worker = None
    if worker is None:
        try:
            from playwright._impl._connection import from_nullable_channel

            impl = getattr(request, "_impl_obj", request)
            channel = impl._initializer.get("serviceWorker")
            worker = from_nullable_channel(channel) if channel is not None else None
        except Exception:
            worker = None
    if worker is None:
        return None
    try:
        return str(worker.url or "")
    except Exception:
        return ""


_INIT_SCRIPT = r"""
((key) => {
  if (Object.prototype.hasOwnProperty.call(window, key)) return;
  let api = null;
  try {
    if (window !== window.parent && window.parent[key]) api = window.parent[key];
  } catch (error) { api = null; }
  if (!api) {
    const counts = {rtc: 0, webtransport: 0, shared_worker: 0};
    const root = String(Math.random()).slice(2) + ":" + String(Date.now());
    api = Object.freeze({
      bump: field => { counts[field] = (counts[field] || 0) + 1; },
      read: () => Object.assign({root}, counts),
    });
  }
  Object.defineProperty(window, key, {value: api, enumerable: false, configurable: false, writable: false});
  const wrap = (name, field) => {
    const Original = window[name];
    if (typeof Original !== "function") return;
    const wrapped = new Proxy(Original, {
      construct(target, args, newTarget) {
        api.bump(field);
        return Reflect.construct(target, args, newTarget === wrapped ? target : newTarget);
      },
    });
    try {
      Object.defineProperty(Original.prototype, "constructor",
        {value: wrapped, writable: true, configurable: true, enumerable: false});
    } catch (error) {}
    try {
      Object.defineProperty(window, name, {value: wrapped, writable: true, configurable: true, enumerable: false});
    } catch (error) {}
  };
  wrap("RTCPeerConnection", "rtc");
  wrap("webkitRTCPeerConnection", "rtc");
  wrap("WebTransport", "webtransport");
  wrap("SharedWorker", "shared_worker");
})(%s);
"""


class SentinelNetworkMonitor:
    """Counts sentinel-bearing traffic on a Playwright BrowserContext.

    Lifecycle: ``start()`` (before any navigation) -> ``prefill_blocking_reasons()``
    (must be empty to fill) -> ``mark_fill_started(filled_keys)`` ->
    ``mark_cleared()`` -> ``wait_quiet(min_seconds)`` -> ``result()``.
    """

    def __init__(
        self,
        nonce: str,
        undetectable_keys: Iterable[str] = (),
        extension_id: str = "",
        *,
        hash_candidates: Iterable[str] = (),
        probe_timeout_seconds: float = 5.0,
    ) -> None:
        self._matcher = SentinelMatcher(nonce, hash_candidates=hash_candidates)
        self._undetectable = {str(key) for key in undetectable_keys}
        self._extension_id = str(extension_id or "").strip()
        self._extension_prefix = (
            f"chrome-extension://{self._extension_id}/" if self._extension_id else None
        )
        self._probe_timeout = float(probe_timeout_seconds)
        self._probe_token = secrets.token_hex(16)
        self._init_key = "__kensho_monitor_" + secrets.token_hex(8)
        self._lock = threading.Lock()
        self._context = None
        self._pages: list = []
        self._ws_pages: set[int] = set()
        self._started = False
        self._attached_late = False
        self._fill_started = False
        self._cleared = False
        self._quiet_completed = False
        self._pages_closed = False
        self._probe_seen = False
        self._worker_found = False
        self._filled_keys: list[str] | None = None
        self._pending = 0
        self._last_activity = time.monotonic()
        self._final_channels: dict[str, object] | None = None
        self.counts = {
            "page_requests_total": 0,
            "page_external_requests": 0,
            "page_service_worker_requests": 0,
            "extension_requests_total": 0,
            "extension_non_loopback_requests": 0,
            "unattributed_requests": 0,
            "unattributed_non_loopback_requests": 0,
            "non_loopback_requests_total": 0,
            "sentinel_network_leak": 0,
            "opaque_requests": 0,
            "opaque_requests_before_fill": 0,
            "websocket_frames_sent": 0,
            "requests_after_clear": 0,
        }

    @property
    def matcher(self) -> SentinelMatcher:
        return self._matcher

    # --- attachment -----------------------------------------------------------
    def start(self, context) -> None:
        if self._started:
            raise RuntimeError("monitor_already_started")
        self._context = context
        self._started = True
        for page in list(context.pages):
            if str(page.url or "about:blank") != "about:blank":
                self._attached_late = True
        context.add_init_script(_INIT_SCRIPT % _js_string(self._init_key))
        context.on("request", self._on_request)
        context.on("page", self._on_page)
        for page in list(context.pages):
            self._on_page(page)
        # Best effort before navigation; prefill_blocking_reasons() re-probes
        # (waiting for a restarted worker) when this one was not observed.
        self._probe_service_worker_network(wait_for_worker=False)

    def _on_page(self, page) -> None:
        if id(page) in self._ws_pages:
            return
        self._ws_pages.add(id(page))
        self._pages.append(page)
        page.on("websocket", self._on_websocket)

    def _extension_worker(self, timeout: float = 0.0):
        if not self._extension_prefix or self._context is None:
            return None
        return live_extension_worker(self._context, self._extension_prefix, timeout=timeout)

    def _probe_service_worker_network(self, *, wait_for_worker: bool = True) -> None:
        """Make the extension worker fetch a loopback probe URL until it is seen.

        The worker is re-acquired on every attempt because Chromium may stop and
        restart it; a closed target is retried until ``probe_timeout_seconds``.
        ``wait_for_worker=False`` makes a single attempt without waiting for a
        worker (used before navigation, when nothing can restart it yet).
        Observability is only ever set by :meth:`_on_request` seeing the probe.
        """
        if self._probe_seen or not self._extension_prefix or self._context is None:
            return
        probe_url = f"http://127.0.0.1:9/__kensho_monitor_probe_{self._probe_token}"
        # Only fetch from an activated worker.  Right after a fresh launch
        # Playwright can evaluate while the worker script is still "parsed"
        # (before install); a fetch() then terminates the worker and its
        # registration never starts again for the rest of the session.
        probe_js = (
            "url => { const sw = self.serviceWorker;"
            " const ready = sw ? sw.state === 'activated' : Boolean(self.registration && self.registration.active);"
            " if (!ready) return false;"
            " fetch(url, {cache: 'no-store'}).catch(() => 0); return true; }"
        )
        single = not wait_for_worker
        deadline = time.monotonic() + self._probe_timeout
        while not self._probe_seen and time.monotonic() < deadline:
            worker = self._extension_worker(
                timeout=0.0 if single else deadline - time.monotonic())
            if worker is None:
                return
            try:
                fetched = evaluate_worker(
                    worker, probe_js, probe_url,
                    timeout=min(max(deadline - time.monotonic(), 0.1), 1.0 if single else 2.0),
                )
            except Exception:
                # Target closed, worker stopped (evaluation never answers) or
                # evaluation failed: re-acquire and retry until the deadline.
                if single:
                    return
                time.sleep(0.05)
                continue
            self._worker_found = True
            if fetched:
                attempt_end = deadline if single else min(deadline, time.monotonic() + 1.0)
                while not self._probe_seen and time.monotonic() < attempt_end:
                    try:
                        self._context.cookies()  # pumps Playwright events
                    except Exception:
                        return
                    time.sleep(0.05)
            if single:
                return
            if not fetched:  # not activated yet: poll again, never fetch early
                time.sleep(0.1)

    # --- request handling ------------------------------------------------------
    def _attribute(self, request) -> str:
        sw_url = _service_worker_url(request)
        if sw_url is not None:
            if self._extension_prefix and sw_url.startswith(self._extension_prefix):
                return "extension"
            if sw_url.startswith("chrome-extension://"):
                return "unattributed"
            return "page_sw"
        try:
            frame = request.frame
        except Exception:
            frame = None
        if frame is not None:
            try:
                frame_url = str(frame.url or "")
            except Exception:
                frame_url = ""
            if self._extension_prefix and frame_url.startswith(self._extension_prefix):
                return "extension"
            return "page"
        try:
            if request.is_navigation_request():
                return "page"
        except Exception:
            pass
        return "unattributed"

    def _record_verdict(self, verdict: str, after_fill: bool) -> None:
        with self._lock:
            if verdict == LEAK:
                self.counts["sentinel_network_leak"] += 1
            elif verdict == OPAQUE:
                key = "opaque_requests" if after_fill else "opaque_requests_before_fill"
                self.counts[key] += 1

    def _on_request(self, request) -> None:
        try:
            url = str(request.url or "")
        except Exception:
            url = ""
        if self._probe_token in url:
            if self._attribute(request) == "extension":
                self._probe_seen = True
            return
        after_fill = self._fill_started
        with self._lock:
            self._pending += 1
            self._last_activity = time.monotonic()
        try:
            self._handle_request(request, url, after_fill)
        finally:
            with self._lock:
                self._pending -= 1

    def _handle_request(self, request, url: str, after_fill: bool) -> None:
        attribution = self._attribute(request)
        network = _is_network_url(url)
        non_loopback = network and not _is_loopback(url)
        with self._lock:
            if self._cleared:
                self.counts["requests_after_clear"] += 1
            if non_loopback:
                self.counts["non_loopback_requests_total"] += 1
            if attribution == "extension":
                self.counts["extension_requests_total"] += 1
                if non_loopback:
                    self.counts["extension_non_loopback_requests"] += 1
            elif attribution == "unattributed":
                self.counts["unattributed_requests"] += 1
                if non_loopback:
                    self.counts["unattributed_non_loopback_requests"] += 1
            else:
                self.counts["page_requests_total"] += 1
                if attribution == "page_sw":
                    self.counts["page_service_worker_requests"] += 1
                if non_loopback:
                    self.counts["page_external_requests"] += 1

        try:
            method = str(request.method or "GET").upper()
        except Exception:
            method = "GET"
        try:
            headers = dict(request.headers or {})
        except Exception:
            headers = {}
        try:
            body = request.post_data_buffer
        except Exception:
            body = None
            if method not in _BODYLESS_METHODS:
                self._record_verdict(OPAQUE, after_fill)
                return
        verdicts = [
            classify_payload(self._matcher, url, content_type="text/plain"),
            classify_payload(
                self._matcher,
                body,
                content_type=headers.get("content-type"),
                content_encoding=headers.get("content-encoding"),
            ),
        ]
        header_text = "\n".join(f"{k}: {v}" for k, v in headers.items())
        if self._matcher.matches_text(header_text):
            verdicts.append(LEAK)
        verdict = _merge(verdicts)
        if verdict == LEAK:
            self._record_verdict(LEAK, after_fill)
            return
        # Bodies Playwright could not read (Blob, FormData with files, streams)
        # arrive as None; compare against the declared length.  Blocking call.
        if method not in _BODYLESS_METHODS:
            try:
                declared = request.header_value("content-length")
            except Exception:
                declared = None
            observed = len(body or b"")
            if declared is None:
                if observed == 0:
                    verdict = _merge([verdict, OPAQUE])
            else:
                try:
                    if int(declared) != observed:
                        verdict = _merge([verdict, OPAQUE])
                except ValueError:
                    verdict = _merge([verdict, OPAQUE])
        if after_fill:
            # Raw headers include Cookie, which page scripts can populate.
            try:
                raw = request.all_headers()
                raw_text = "\n".join(f"{k}: {v}" for k, v in raw.items())
                if self._matcher.matches_text(raw_text):
                    verdict = LEAK
            except Exception:
                verdict = _merge([verdict, OPAQUE])
        self._record_verdict(verdict, after_fill)

    def _on_websocket(self, websocket) -> None:
        after_fill = self._fill_started
        try:
            url = str(websocket.url or "")
        except Exception:
            url = ""
        verdict = classify_payload(self._matcher, url, content_type="text/plain")
        with self._lock:
            self.counts["page_requests_total"] += 1
            self._last_activity = time.monotonic()
            if not _is_loopback(url):
                self.counts["page_external_requests"] += 1
                self.counts["non_loopback_requests_total"] += 1
        self._record_verdict(verdict, after_fill)
        websocket.on("framesent", self._on_frame_sent)

    def _on_frame_sent(self, payload) -> None:
        after_fill = self._fill_started
        with self._lock:
            self.counts["websocket_frames_sent"] += 1
            self._last_activity = time.monotonic()
        if isinstance(payload, (bytes, bytearray)):
            verdict = LEAK if self._matcher.matches_bytes(bytes(payload)) else OPAQUE
        else:
            verdict = classify_payload(self._matcher, str(payload or ""), content_type="text/plain")
        self._record_verdict(verdict, after_fill)

    # --- pre-fill checks --------------------------------------------------------
    def _read_channel_counters(self) -> dict[str, object]:
        totals = {"rtc": 0, "webtransport": 0, "shared_worker": 0}
        missing = 0
        for page in list(self._pages):
            try:
                if page.is_closed():
                    continue
                frames = list(page.frames)
            except Exception:
                missing += 1
                continue
            roots: set[str] = set()
            for frame in frames:
                try:
                    value = frame.evaluate(
                        "key => { const api = window[key]; return api ? api.read() : null; }",
                        self._init_key,
                    )
                except Exception:
                    value = None
                if not isinstance(value, dict):
                    missing += 1
                    continue
                # Same-origin child frames share their parent's counter object.
                root = str(value.get("root") or "")
                if not root:
                    missing += 1
                    continue
                if root in roots:
                    continue
                roots.add(root)
                for field in totals:
                    try:
                        totals[field] += int(value.get(field, 0))
                    except (TypeError, ValueError):
                        missing += 1
        return {**totals, "frames_without_monitor": missing}

    def prefill_blocking_reasons(self, page) -> list[str]:
        """Reasons the runner must not fill.  An empty list is required to fill."""
        reasons: list[str] = []
        if not self._started:
            return ["monitor_not_started"]
        if self._attached_late:
            reasons.append("monitor_attached_after_navigation")
        self._probe_service_worker_network(wait_for_worker=True)
        # "Found" means a worker actually answered; a stopped worker that is
        # still listed does not count.
        if not self._probe_seen and not self._worker_found:
            reasons.append("extension_worker_not_found")
        if not self._probe_seen:
            reasons.append("service_worker_network_unobservable")
        target_origin = _origin(str(page.url or ""))
        if not target_origin:
            reasons.append("target_origin_unknown")
        try:
            sw_state = page.evaluate(
                """async () => {
                  if (!('serviceWorker' in navigator)) return {controller: false, registrations: 0};
                  const regs = await navigator.serviceWorker.getRegistrations();
                  return {controller: Boolean(navigator.serviceWorker.controller), registrations: regs.length};
                }"""
            )
            if sw_state.get("controller") or int(sw_state.get("registrations", 0)):
                reasons.append("page_service_worker_registered")
        except Exception:
            reasons.append("page_service_worker_state_unknown")
        for worker in list(self._context.service_workers):
            worker_url = str(worker.url or "")
            if self._extension_prefix and worker_url.startswith(self._extension_prefix):
                continue
            if _origin(worker_url) == target_origin:
                if "page_service_worker_registered" not in reasons:
                    reasons.append("page_service_worker_registered")
            elif "foreign_service_worker_present" not in reasons:
                reasons.append("foreign_service_worker_present")
        try:
            frames = list(page.frames)[1:]
        except Exception:
            frames = []
            reasons.append("frames_unreadable")
        for frame in frames:
            frame_url = str(frame.url or "")
            if frame_url in ("about:blank", "about:srcdoc"):
                continue
            if _origin(frame_url) != target_origin:
                if "cross_origin_iframe_present" not in reasons:
                    reasons.append("cross_origin_iframe_present")
        channels = self._read_channel_counters()
        if channels["rtc"]:
            reasons.append("rtc_peer_connection_constructed")
        if channels["webtransport"]:
            reasons.append("webtransport_constructed")
        if channels["shared_worker"]:
            reasons.append("shared_worker_constructed")
        if channels["frames_without_monitor"]:
            reasons.append("frame_without_monitor_hook")
        return reasons

    # --- phases -------------------------------------------------------------------
    def mark_fill_started(self, filled_keys: Iterable[str] | None = None) -> None:
        if not self._started:
            raise RuntimeError("monitor_not_started")
        self._filled_keys = None if filled_keys is None else [str(k) for k in filled_keys]
        self._fill_started = True

    def mark_cleared(self) -> None:
        if not self._fill_started:
            raise RuntimeError("fill_not_started")
        self._cleared = True

    def _pump(self, seconds: float) -> None:
        page = next((p for p in self._pages if not p.is_closed()), None)
        if page is not None:
            page.wait_for_timeout(max(1, int(seconds * 1000)))
            return
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                self._context.cookies()
            except Exception:
                return
            time.sleep(0.05)

    def wait_quiet(
        self,
        min_seconds: float = 30,
        *,
        quiet_seconds: float = 2.0,
        max_extra_seconds: float = 30.0,
        close_pages: bool = True,
    ) -> None:
        """Keep observing after clear; then (optionally) close the tabs.

        Waits ``min_seconds``, then until ``quiet_seconds`` pass without new
        traffic (bounded by ``max_extra_seconds``).  Closing navigates each tab
        to about:blank first so pagehide/unload beacons are observed.
        """
        if not self._cleared:
            raise RuntimeError("session_not_cleared")
        self._pump(min_seconds)
        deadline = time.monotonic() + max_extra_seconds
        quiet = False
        while time.monotonic() < deadline:
            if time.monotonic() - self._last_activity >= quiet_seconds and self._pending == 0:
                quiet = True
                break
            self._pump(0.25)
        self._final_channels = self._read_channel_counters()
        # A page that never goes quiet leaves quiet_period_completed False.
        self._quiet_completed = quiet
        if close_pages:
            self.close_pages()

    def close_pages(self, grace_seconds: float = 2.0) -> None:
        if self._final_channels is None:
            self._final_channels = self._read_channel_counters()
        for page in list(self._pages):
            try:
                if not page.is_closed():
                    page.goto("about:blank")
            except Exception:
                pass
        self._pump(grace_seconds)
        for page in list(self._pages):
            try:
                if not page.is_closed():
                    page.close(run_before_unload=False)
            except Exception:
                pass
        deadline = time.monotonic() + 5
        while self._pending and time.monotonic() < deadline:
            self._pump(0.1)
        self._pages_closed = True

    # --- result ---------------------------------------------------------------------
    def result(self) -> dict[str, object]:
        counts = dict(self.counts)
        reasons: list[str] = []
        if not self._started:
            reasons.append("monitor_not_started")
        if self._attached_late:
            reasons.append("monitor_attached_after_navigation")
        if not self._probe_seen:
            reasons.append("service_worker_network_unobservable")
        if not self._fill_started:
            reasons.append("fill_not_started")
        if not self._cleared:
            reasons.append("session_not_cleared")
        if not self._quiet_completed:
            reasons.append("quiet_period_not_completed")
        if not self._pages_closed:
            reasons.append("tabs_not_closed")
        if self._pending:
            reasons.append("requests_still_pending")
        if counts["opaque_requests"]:
            reasons.append("opaque_requests_after_fill")
        channels = self._final_channels or {}
        if not channels:
            reasons.append("channel_counters_not_read")
        else:
            for field in ("rtc", "webtransport", "shared_worker"):
                if channels.get(field):
                    reasons.append(f"{field}_channel_unobservable")
            if channels.get("frames_without_monitor"):
                reasons.append("frame_without_monitor_hook")

        leak_count = counts["sentinel_network_leak"]
        leak_value: object = leak_count if (leak_count or not reasons) else UNVERIFIED

        ext_reasons = [
            reason for reason in reasons
            if reason not in ("opaque_requests_after_fill", "rtc_channel_unobservable",
                              "webtransport_channel_unobservable")
        ]
        if counts["unattributed_non_loopback_requests"]:
            ext_reasons.append("unattributed_non_loopback_requests")
        ext_count = counts["extension_non_loopback_requests"]
        ext_value: object = ext_count if (ext_count or not ext_reasons) else UNVERIFIED

        if self._filled_keys is None:
            undetectable: object = UNVERIFIED
        else:
            undetectable = len(set(self._filled_keys) & self._undetectable)

        if leak_value not in (0, UNVERIFIED) or ext_value not in (0, UNVERIFIED):
            status = "FAIL"
        elif UNVERIFIED in (leak_value, ext_value, undetectable) or undetectable:
            status = UNVERIFIED
        else:
            status = "PASS"
        counts["sentinel_network_leak"] = leak_value
        counts["extension_non_loopback_requests"] = ext_value
        return {
            **counts,
            "undetectable_fields_count": undetectable,
            "sw_network_events_observable": self._probe_seen,
            "quiet_period_completed": self._quiet_completed,
            "unverified_reasons": sorted(set(reasons + ext_reasons)),
            "status": status,
        }


def _js_string(value: str) -> str:
    import json

    return json.dumps(value)
