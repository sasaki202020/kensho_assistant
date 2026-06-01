from __future__ import annotations

from .base import BaseSubmitAdapter, SubmitResult


class RealSubmitAdapter(BaseSubmitAdapter):
    def submit(self, page, context: dict[str, object]) -> SubmitResult:
        raise RuntimeError("RealSubmitAdapter is intentionally not implemented")
