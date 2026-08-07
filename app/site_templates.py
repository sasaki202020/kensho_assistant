from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

from .paths import SITE_TEMPLATES_JSON


@dataclass(frozen=True)
class SiteTemplate:
    template_id: str
    label: str
    site_name: str = ""
    domains: tuple[str, ...] = ()
    path_contains: tuple[str, ...] = ()
    known_form_labels: tuple[str, ...] = ()
    known_required_fields: tuple[str, ...] = ()
    known_radio_groups: tuple[str, ...] = ()
    known_select_options: dict[str, tuple[str, ...]] = field(default_factory=dict)
    confirmation_button_texts: tuple[str, ...] = ()
    submit_button_texts: tuple[str, ...] = ()
    skip_rules: tuple[str, ...] = ()
    force_fill_fields: tuple[str, ...] = ()
    manual_review_terms: tuple[str, ...] = ()
    safety_notes: tuple[str, ...] = ()
    last_verified_at: str = ""
    notes: tuple[str, ...] = ()

    def matches(self, url: str) -> bool:
        parsed = urlsplit(url or "")
        domain = (parsed.netloc or "").casefold()
        path = (parsed.path or "").casefold()
        domain_match = not self.domains or any(domain == item.casefold() or domain.endswith("." + item.casefold()) for item in self.domains)
        path_match = not self.path_contains or any(token.casefold() in path for token in self.path_contains)
        return domain_match and path_match

    def signal_hits(self, text: str) -> dict[str, object]:
        normalized = _normalize_text(text)
        if not normalized:
            return {
                "known_form_labels": [],
                "known_required_fields": [],
                "known_radio_groups": [],
                "known_select_options": {},
                "confirmation_button_texts": [],
                "submit_button_texts": [],
                "skip_rules": [],
                "manual_review_terms": [],
                "safety_notes": [],
            }
        hits: dict[str, object] = {
            "known_form_labels": [term for term in self.known_form_labels if _contains(normalized, term)],
            "known_required_fields": [term for term in self.known_required_fields if _contains(normalized, term)],
            "known_radio_groups": [term for term in self.known_radio_groups if _contains(normalized, term)],
            "known_select_options": {
                group: [option for option in options if _contains(normalized, option)]
                for group, options in self.known_select_options.items()
                if any(_contains(normalized, option) for option in options)
            },
            "confirmation_button_texts": [term for term in self.confirmation_button_texts if _contains(normalized, term)],
            "submit_button_texts": [term for term in self.submit_button_texts if _contains(normalized, term)],
            "skip_rules": [term for term in self.skip_rules if _contains(normalized, term)],
            "manual_review_terms": [term for term in self.manual_review_terms if _contains(normalized, term)],
            "safety_notes": [term for term in self.safety_notes if _contains(normalized, term)],
        }
        return hits

    def signal_score(self, text: str) -> tuple[int, dict[str, object]]:
        hits = self.signal_hits(text)
        score = 0
        score += len(hits["known_form_labels"]) * 3
        score += len(hits["known_required_fields"]) * 2
        score += len(hits["known_radio_groups"]) * 2
        score += sum(len(values) for values in hits["known_select_options"].values()) * 3
        score += len(hits["confirmation_button_texts"])
        score += len(hits["submit_button_texts"])
        score += len(hits["skip_rules"])
        score += len(hits["manual_review_terms"])
        return score, hits

    def matches_text(self, text: str) -> bool:
        score, _ = self.signal_score(text)
        return score > 0

    def is_confirmation_text(self, text: str) -> bool:
        normalized = _normalize_text(text)
        return bool(normalized and any(_contains(normalized, term) for term in self.confirmation_button_texts))

    def is_submit_text(self, text: str) -> bool:
        normalized = _normalize_text(text)
        return bool(normalized and any(_contains(normalized, term) for term in self.submit_button_texts))

    def skip_rule_hits(self, text: str) -> list[str]:
        normalized = _normalize_text(text)
        return [term for term in self.skip_rules if _contains(normalized, term)]


def _coerce_tuple(values: object) -> tuple[str, ...]:
    if isinstance(values, list):
        return tuple(str(item).strip() for item in values if str(item).strip())
    if isinstance(values, str) and values.strip():
        return (values.strip(),)
    return ()


def _coerce_select_options(values: object) -> dict[str, tuple[str, ...]]:
    if isinstance(values, dict):
        result: dict[str, tuple[str, ...]] = {}
        for key, item in values.items():
            key_text = str(key).strip()
            if not key_text:
                continue
            result[key_text] = _coerce_tuple(item)
        return result
    if isinstance(values, list):
        result: dict[str, tuple[str, ...]] = {}
        for item in values:
            if not isinstance(item, dict):
                continue
            key_text = str(item.get("name", "") or item.get("field_name", "") or item.get("label", "")).strip()
            if not key_text:
                continue
            result[key_text] = _coerce_tuple(item.get("options"))
        return result
    return {}


def _normalize_text(text: str) -> str:
    return " ".join((text or "").casefold().replace("　", " ").split())


def _contains(text: str, term: str) -> bool:
    if not text or not term:
        return False
    return _normalize_text(term) in text


def _template_score(template: SiteTemplate, url: str, page_text: str = "") -> tuple[int, int, int, int, str]:
    if template.template_id == "generic":
        return (0, 0, 0, 0, template.template_id)
    parsed = urlsplit(url or "")
    domain = (parsed.netloc or "").casefold()
    path = (parsed.path or "").casefold()
    domain_match = not template.domains or any(domain == item.casefold() or domain.endswith("." + item.casefold()) for item in template.domains)
    if not domain_match:
        return (-1, 0, 0, 0, template.template_id)
    path_hits = sum(1 for token in template.path_contains if token.casefold() in path)
    text_score = 0
    signal_hit_count = 0
    if page_text.strip():
        text_score, hits = template.signal_score(page_text)
        signal_hit_count = sum(
            len(value) if isinstance(value, list) else sum(len(item) for item in value.values())
            for value in hits.values()
        )
    return (100 + (path_hits * 20) + text_score, path_hits, signal_hit_count, len(template.domains), template.template_id)


@lru_cache(maxsize=1)
def load_site_templates(path: str | Path | None = None) -> list[SiteTemplate]:
    template_path = Path(path) if path else SITE_TEMPLATES_JSON
    if not template_path.exists():
        return [_default_template()]
    try:
        payload = json.loads(template_path.read_text(encoding="utf-8"))
    except Exception:
        return [_default_template()]
    templates: list[SiteTemplate] = []
    for item in payload.get("templates", []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict):
            continue
        template_id = str(item.get("id", "")).strip()
        if not template_id:
            continue
        templates.append(
            SiteTemplate(
                template_id=template_id,
                label=str(item.get("label", template_id)).strip() or template_id,
                site_name=str(item.get("site_name", "")).strip(),
                domains=_coerce_tuple(item.get("domains")),
                path_contains=_coerce_tuple(item.get("path_contains")),
                known_form_labels=_coerce_tuple(item.get("known_form_labels")),
                known_required_fields=_coerce_tuple(item.get("known_required_fields")),
                known_radio_groups=_coerce_tuple(item.get("known_radio_groups")),
                known_select_options=_coerce_select_options(item.get("known_select_options")),
                confirmation_button_texts=_coerce_tuple(item.get("confirmation_button_texts")),
                submit_button_texts=_coerce_tuple(item.get("submit_button_texts")),
                skip_rules=_coerce_tuple(item.get("skip_rules")),
                force_fill_fields=_coerce_tuple(item.get("force_fill_fields")),
                manual_review_terms=_coerce_tuple(item.get("manual_review_terms")),
                safety_notes=_coerce_tuple(item.get("safety_notes")),
                last_verified_at=str(item.get("last_verified_at", "")).strip(),
                notes=_coerce_tuple(item.get("notes")),
            )
        )
    return templates or [_default_template()]


def _default_template() -> SiteTemplate:
    return SiteTemplate(
        template_id="generic",
        label="Generic form template",
        site_name="generic",
        notes=("site-specific rules not yet matched",),
    )


def match_site_template(url: str, path: str | Path | None = None, page_text: str = "") -> SiteTemplate:
    templates = load_site_templates(path)
    generic = next((template for template in templates if template.template_id == "generic"), _default_template())
    candidates: list[tuple[int, int, int, int, str, SiteTemplate]] = []
    for template in templates:
        if template.template_id == "generic":
            continue
        parsed = urlsplit(url or "")
        domain = (parsed.netloc or "").casefold()
        domain_match = not template.domains or any(domain == item.casefold() or domain.endswith("." + item.casefold()) for item in template.domains)
        if not domain_match:
            continue
        score, path_hits, signal_hits, domain_count, template_id = _template_score(template, url, page_text=page_text)
        candidates.append((score, path_hits, signal_hits, domain_count, template_id, template))
    if not candidates:
        return generic
    candidates.sort(reverse=True)
    best = candidates[0][5]
    return best


def template_summary(template: SiteTemplate | None) -> dict[str, object]:
    if template is None:
        template = _default_template()
    return {
        "site_template_id": template.template_id,
        "site_template_label": template.label,
        "site_name": template.site_name,
        "site_template_notes": list(template.notes),
        "known_form_labels": list(template.known_form_labels),
        "known_required_fields": list(template.known_required_fields),
        "known_radio_groups": list(template.known_radio_groups),
        "known_select_options": {key: list(values) for key, values in template.known_select_options.items()},
        "confirmation_button_texts": list(template.confirmation_button_texts),
        "submit_button_texts": list(template.submit_button_texts),
        "skip_rules": list(template.skip_rules),
        "force_fill_fields": list(template.force_fill_fields),
        "manual_review_terms": list(template.manual_review_terms),
        "safety_notes": list(template.safety_notes),
        "last_verified_at": template.last_verified_at,
    }
