"""Sentinel residue checks after session clear (counts only, never values)."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

from .pilot_network_monitor import (
    CLEAN,
    LEAK,
    UNVERIFIED,
    SentinelMatcher,
    classify_payload,
)

RESIDUE_AREAS = (
    "dom",
    "local_storage",
    "session_storage",
    "indexeddb",
    "cache_storage",
    "document_cookie",
    "context_cookies",
    "extension_storage",
    "evidence_files",
)

# Runs inside each frame.  Only per-area match counts leave the page.
_FRAME_SCAN = r"""
async ({ci, cs}) => {
  const lowered = ci.map(item => item.toLowerCase());
  const views = text => {
    const out = [text];
    const tryPush = fn => { try { out.push(fn(text)); } catch (error) {} };
    tryPush(t => decodeURIComponent(t));
    tryPush(t => decodeURIComponent(t.replace(/\+/g, " ")));
    tryPush(t => t.replace(/\\u([0-9a-fA-F]{4})/g, (_, h) => String.fromCharCode(parseInt(h, 16))));
    return out;
  };
  const hit = value => {
    if (value === null || value === undefined) return false;
    const text = String(value);
    if (!text) return false;
    for (const view of views(text)) {
      const low = view.toLowerCase();
      if (lowered.some(n => low.includes(n))) return true;
      if (cs.some(n => view.includes(n))) return true;
    }
    return false;
  };
  const flatten = async (value, seen, depth) => {
    if (depth > 12) throw new Error("too_deep");
    if (value === null || value === undefined) return [];
    const type = typeof value;
    if (type === "string") return [value];
    if (type === "number" || type === "boolean" || type === "bigint") return [String(value)];
    if (type !== "object") return [];
    if (seen.has(value)) return [];
    seen.add(value);
    if (value instanceof Blob) return [await value.text()];
    if (value instanceof ArrayBuffer || ArrayBuffer.isView(value)) {
      const bytes = value instanceof ArrayBuffer ? new Uint8Array(value) :
        new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
      return [new TextDecoder("utf-8").decode(bytes), new TextDecoder("utf-16le").decode(bytes)];
    }
    if (value instanceof Date || value instanceof RegExp) return [String(value)];
    const out = [];
    const entries = value instanceof Map ? [...value.entries()] :
      value instanceof Set ? [...value.values()].map(v => [v, v]) : Object.entries(value);
    for (const [key, item] of entries) {
      out.push(...await flatten(key, seen, depth + 1));
      out.push(...await flatten(item, seen, depth + 1));
    }
    return out;
  };
  const anyHit = async value => (await flatten(value, new WeakSet(), 0)).some(hit);
  const result = {origin: location.origin, dom: 0, local_storage: 0, session_storage: 0,
    indexeddb: 0, cache_storage: 0, document_cookie: 0};

  // DOM: form control values, open shadow roots, full HTML, URL/state.
  const roots = [document];
  const controls = [];
  while (roots.length) {
    const root = roots.pop();
    for (const el of root.querySelectorAll("*")) {
      if (el.shadowRoot) roots.push(el.shadowRoot);
      if ("value" in el && (el.matches("input, textarea, select, output"))) controls.push(el);
    }
  }
  result.dom += controls.filter(el => hit(el.value)).length;
  const html = [document.documentElement ? document.documentElement.outerHTML : ""];
  for (const el of document.querySelectorAll("*")) if (el.shadowRoot) html.push(el.shadowRoot.innerHTML);
  if (html.some(hit)) result.dom += 1;
  if (hit(location.href)) result.dom += 1;
  if (hit(window.name)) result.dom += 1;
  try { if (await anyHit(history.state)) result.dom += 1; } catch (error) { result.dom = null; }

  const scanStorage = storage => {
    let count = 0;
    for (let i = 0; i < storage.length; i += 1) {
      const key = storage.key(i);
      if (hit(key) || hit(storage.getItem(key))) count += 1;
    }
    return count;
  };
  try { result.local_storage = scanStorage(localStorage); } catch (error) { result.local_storage = null; }
  try { result.session_storage = scanStorage(sessionStorage); } catch (error) { result.session_storage = null; }
  try { result.document_cookie = document.cookie.split(";").filter(hit).length; }
  catch (error) { result.document_cookie = null; }

  try {
    if (typeof indexedDB === "undefined" || typeof indexedDB.databases !== "function") throw new Error("no_enum");
    const request = r => new Promise((resolve, reject) => {
      r.onsuccess = () => resolve(r.result); r.onerror = () => reject(r.error);
    });
    let count = 0;
    for (const info of await indexedDB.databases()) {
      if (!info.name) throw new Error("unnamed_db");
      const db = await new Promise((resolve, reject) => {
        const open = indexedDB.open(info.name);
        open.onupgradeneeded = () => { open.transaction.abort(); };
        open.onsuccess = () => resolve(open.result);
        open.onerror = () => reject(open.error);
        open.onblocked = () => reject(new Error("blocked"));
      });
      try {
        for (const storeName of Array.from(db.objectStoreNames)) {
          const store = db.transaction(storeName, "readonly").objectStore(storeName);
          const [keys, values] = await Promise.all([request(store.getAllKeys()), request(store.getAll())]);
          for (let i = 0; i < values.length; i += 1) {
            if (await anyHit(keys[i]) || await anyHit(values[i])) count += 1;
          }
        }
      } finally { db.close(); }
    }
    result.indexeddb = count;
  } catch (error) { result.indexeddb = null; }

  try {
    if (typeof caches === "undefined") {
      result.cache_storage = window.isSecureContext ? null : 0;
    } else {
      let count = 0;
      let entries = 0;
      for (const name of await caches.keys()) {
        const cache = await caches.open(name);
        for (const req of await cache.keys()) {
          entries += 1;
          if (entries > 500) throw new Error("too_many_entries");
          const res = await cache.match(req);
          const body = res ? await res.clone().text() : "";
          if (hit(name) || hit(req.url) || hit(body)) count += 1;
        }
      }
      result.cache_storage = count;
    }
  } catch (error) { result.cache_storage = null; }
  return result;
}
"""

_EXTENSION_SCAN = r"""
async ({ci, cs}) => {
  const lowered = ci.map(item => item.toLowerCase());
  const hit = text => {
    const low = text.toLowerCase();
    return lowered.some(n => low.includes(n)) || cs.some(n => text.includes(n));
  };
  let count = 0;
  for (const area of [chrome.storage.session, chrome.storage.local]) {
    if (!area) continue;
    const items = await area.get(null);
    for (const [key, value] of Object.entries(items)) {
      if (hit(key) || hit(JSON.stringify(value) || "")) count += 1;
    }
  }
  return count;
}
"""


def _add(total: dict[str, object], area: str, value: object) -> None:
    current = total.get(area, 0)
    if current == UNVERIFIED or value is None or value == UNVERIFIED:
        total[area] = UNVERIFIED
        return
    try:
        total[area] = int(current) + int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        total[area] = UNVERIFIED


def check_sentinel_residue(
    context,
    nonce: str,
    *,
    extension_id: str,
    evidence_dirs: Iterable[Path] = (),
    hash_candidates: Iterable[str] = (),
) -> dict[str, object]:
    """Count sentinel occurrences left after session clear.

    Each area reports an int (matched entries) or ``"UNVERIFIED"`` when it
    could not be enumerated.  Values themselves never leave the browser.
    """
    matcher = SentinelMatcher(nonce, hash_candidates=hash_candidates)
    needles = matcher.js_needles()
    result: dict[str, object] = {area: 0 for area in RESIDUE_AREAS}

    pages = [page for page in list(context.pages) if not page.is_closed()]
    if not pages:
        for area in ("dom", "local_storage", "session_storage", "indexeddb",
                     "cache_storage", "document_cookie"):
            result[area] = UNVERIFIED
    origin_storage: dict[str, dict[str, object]] = {}
    for page in pages:
        for frame in list(page.frames):
            try:
                scanned = frame.evaluate(_FRAME_SCAN, needles)
            except Exception:
                scanned = None
            if not isinstance(scanned, dict):
                for area in ("dom", "local_storage", "session_storage", "indexeddb",
                             "cache_storage", "document_cookie"):
                    result[area] = UNVERIFIED
                continue
            _add(result, "dom", scanned.get("dom"))
            origin = str(scanned.get("origin") or "")
            # localStorage/IndexedDB/Cache/cookies are per origin: count once.
            per_origin = origin_storage.setdefault(origin, {})
            for area in ("local_storage", "indexeddb", "cache_storage", "document_cookie"):
                value = scanned.get(area)
                previous = per_origin.get(area)
                if value is None or previous == UNVERIFIED:
                    per_origin[area] = UNVERIFIED
                else:
                    per_origin[area] = max(int(previous or 0), int(value))
            # sessionStorage is per tab and origin; count every frame's view once per page.
            key = f"{id(page)}|{origin}|session"
            if key not in per_origin:
                per_origin[key] = True
                _add(result, "session_storage", scanned.get("session_storage"))
    for per_origin in origin_storage.values():
        for area in ("local_storage", "indexeddb", "cache_storage", "document_cookie"):
            if area in per_origin:
                _add(result, area, per_origin[area])

    try:
        cookies = context.cookies()
        result["context_cookies"] = sum(
            1 for cookie in cookies
            if matcher.matches_text(str(cookie.get("name", "")))
            or matcher.matches_text(str(cookie.get("value", "")))
        )
    except Exception:
        result["context_cookies"] = UNVERIFIED

    prefix = f"chrome-extension://{str(extension_id or '').strip()}/"
    workers = [w for w in list(context.service_workers) if str(w.url or "").startswith(prefix)]
    if not extension_id or not workers:
        result["extension_storage"] = UNVERIFIED
    else:
        try:
            result["extension_storage"] = int(workers[0].evaluate(_EXTENSION_SCAN, needles))
        except Exception:
            result["extension_storage"] = UNVERIFIED

    result["evidence_files"] = scan_evidence_files(matcher, evidence_dirs)

    values = [result[area] for area in RESIDUE_AREAS]
    if UNVERIFIED in values:
        total: object = UNVERIFIED
    else:
        total = sum(int(v) for v in values)  # type: ignore[arg-type]
    positive = any(isinstance(v, int) and v > 0 for v in values)
    result["total"] = total
    result["status"] = "FAIL" if positive else (UNVERIFIED if total == UNVERIFIED else "PASS")
    return result


def scan_evidence_files(matcher: SentinelMatcher, dirs: Iterable[Path]) -> object:
    """Count files containing the sentinel; unreadable/opaque files => UNVERIFIED."""
    count = 0
    unverified = False
    for root in dirs:
        root = Path(root)
        if not root.exists():
            continue
        paths = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())
        for path in paths:
            try:
                data = path.read_bytes()
            except OSError:
                unverified = True
                continue
            verdict = classify_payload(matcher, data)
            if verdict == LEAK:
                count += 1
            elif verdict != CLEAN:
                unverified = True
    if count:
        return count
    return UNVERIFIED if unverified else 0


def snapshot_sha256(paths: Iterable[Path]) -> dict[str, str]:
    """SHA-256 of every file under the given files/dirs (missing paths are absent)."""
    snapshot: dict[str, str] = {}
    for item in paths:
        item = Path(item)
        if item.is_file():
            files = [item]
        elif item.is_dir():
            files = sorted(p for p in item.rglob("*") if p.is_file())
        else:
            continue
        for path in files:
            try:
                snapshot[str(path.resolve())] = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                snapshot[str(path.resolve())] = "<unreadable>"
    return snapshot


def compare_sha256_snapshots(before: dict[str, str], after: dict[str, str]) -> dict[str, object]:
    """Differences as counts only."""
    added = len(set(after) - set(before))
    removed = len(set(before) - set(after))
    changed = sum(1 for key in set(before) & set(after) if before[key] != after[key])
    unreadable = sum(1 for value in after.values() if value == "<unreadable>")
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "unreadable": unreadable,
        "identical": not (added or removed or changed or unreadable),
    }
