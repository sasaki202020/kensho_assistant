from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .form_detector import detect_fields
from .models import DetectedField
from .paths import FORM_ANALYSIS_DIR
from .site_templates import match_site_template, template_summary


SUBMIT_SELECTOR = 'button, input[type="submit"], input[type="button"], input[type="image"]'


class FormAnalyzer:
    def analyze(self, page, campaign_id: str, *, persist: bool = True) -> dict[str, object]:
        try:
            body_text = page.locator("body").inner_text(timeout=5000) if page.locator("body").count() else ""
        except Exception:
            body_text = ""
        site_template = match_site_template(page.url, page_text=body_text)
        fields = detect_fields(page)
        submit_candidates = page.locator(SUBMIT_SELECTOR).evaluate_all(
            """nodes => nodes.map((node, index) => {
                const text = (node.innerText || node.value || node.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim();
                const type = (node.type || '').toLowerCase();
                const id = node.id || '';
                const name = node.getAttribute('name') || '';
                const selector = id ? `#${CSS.escape(id)}` : (name ? `${node.tagName.toLowerCase()}[name="${CSS.escape(name)}"]` : `${node.tagName.toLowerCase()}:nth-of-type(${index + 1})`);
                return {selector, text, type, id, name, tag_name: node.tagName.toLowerCase(), disabled: Boolean(node.disabled)};
            })"""
        )
        template_signal_score = 0
        template_signal_hits: dict[str, object] = {}
        template_skip_hits: list[str] = []
        if site_template is not None:
            template_signal_score, template_signal_hits = site_template.signal_score(body_text)
            template_skip_hits = site_template.skip_rule_hits(body_text)
        submit_candidates = [
            {
                **candidate,
                "template_confirmation_match": bool(site_template and site_template.is_confirmation_text(str(candidate.get("text", "")))),
                "template_submit_match": bool(site_template and site_template.is_submit_text(str(candidate.get("text", "")))),
            }
            for candidate in submit_candidates
        ]
        result = {
            "campaign_id": campaign_id,
            "url": page.url,
            **template_summary(site_template),
            "site_template_signal_score": template_signal_score,
            "site_template_signal_hits": template_signal_hits,
            "site_template_skip_hits": template_skip_hits,
            "fields": [self._field_payload(field) for field in fields],
            "submit_button_candidates": submit_candidates,
        }
        if persist:
            self.save(campaign_id, result)
        return result

    def save(self, campaign_id: str, result: dict[str, object]) -> Path:
        FORM_ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
        path = FORM_ANALYSIS_DIR / f"{campaign_id}.json"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def _field_payload(field: DetectedField) -> dict[str, object]:
        payload = asdict(field)
        payload["surrounding_text"] = field.nearby_text
        return payload
