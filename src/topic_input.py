from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TopicRequest:
    topic: str
    official_url: str | None = None
    output_suffix: str | None = None


def load_topic_request(path: Path) -> TopicRequest:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("input/topic.json must be a JSON object")
    topic = str(data.get("topic", "")).strip()
    if not topic:
        raise ValueError("input/topic.json requires a topic")
    official_url = str(data.get("official_url", "")).strip() or None
    output_suffix = str(data.get("output_suffix", "")).strip() or None
    return TopicRequest(topic=topic, official_url=official_url, output_suffix=output_suffix)
