from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


_AMOUNT_RE = re.compile(
    r"(?P<number>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)"
    r"\s*(?P<unit>万|千)?\s*円(?:相当|分)?"
)
_TOTAL_MARKERS = ("総額", "合計", "総計")


@dataclass(frozen=True)
class YenAmountCandidate:
    yen: int
    raw: str
    context: str
    is_total_amount: bool


def _to_yen(number: str, unit: str | None) -> int:
    value = float(number.replace(",", ""))
    return int(round(value * {None: 1, "千": 1_000, "万": 10_000}[unit]))


def extract_yen_amounts(text: str) -> list[YenAmountCandidate]:
    results: list[YenAmountCandidate] = []
    source = text or ""
    for match in _AMOUNT_RE.finditer(source):
        prefix_start = max(0, match.start() - 12)
        suffix_end = min(len(source), match.end() + 12)
        prefix = source[prefix_start:match.start()]
        results.append(
            YenAmountCandidate(
                yen=_to_yen(match.group("number"), match.group("unit")),
                raw=match.group(0),
                context=source[prefix_start:suffix_end],
                is_total_amount=any(marker in prefix for marker in _TOTAL_MARKERS),
            )
        )
    return results


def max_individual_value(candidates: Iterable[YenAmountCandidate]) -> int | None:
    values = [candidate.yen for candidate in candidates if not candidate.is_total_amount]
    return max(values) if values else None

