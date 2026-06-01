from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .form_detector import detect_fields
from .models import DetectedField
from .paths import FORM_ANALYSIS_DIR


SUBMIT_SELECTOR = 'button, input[type="submit"], input[type="button"], input[type="image"]'


class FormAnalyzer:
    def analyze(self, page, campaign_id: str) -> dict[str, object]:
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
        result = {
            "campaign_id": campaign_id,
            "url": page.url,
            "fields": [self._field_payload(field) for field in fields],
            "submit_button_candidates": submit_candidates,
        }
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
