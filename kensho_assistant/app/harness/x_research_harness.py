from __future__ import annotations

from pathlib import Path

from kensho_assistant.app.research.note_material_builder import build_note_material
from kensho_assistant.app.research.hermes_x_search import build_hermes_x_search_diagnostic_prompt, run_hermes_x_search
from kensho_assistant.app.research.x_claim_analyzer import analyze_x_claims
from kensho_assistant.app.privacy_guard import redact_personal_info

from .run_store import build_output_dir, timestamp, write_json, write_json_raw, write_sources_csv, write_text
from .task_models import HarnessMode, HarnessRunResult, XPost, XResearchTask


MOCK_X_POSTS = [
    XPost(
        author="sample user",
        handle="@sample",
        post_url="https://x.com/sample/status/123",
        text="Codexにサブエージェント3並列レビューをさせると開発が完全自動化できます。寝ている間に全部終わります。",
        engagement_hint="high",
    ),
    XPost(
        author="cautious user",
        handle="@cautious",
        post_url="https://x.com/cautious/status/456",
        text="AI駆動開発は便利だけど、設計レビューとテスト確認を人間がやらないと危ない。完全自動という表現は言いすぎ。",
        engagement_hint="medium",
    ),
]

VALID_MODES: set[str] = {"quick", "verify", "note", "ttp"}
VALID_PROVIDERS: set[str] = {"mock", "hermes"}


def _run_hermes_provider(query: str, mode: HarnessMode) -> dict[str, object]:
    if mode == "quick":
        return run_hermes_x_search(query, prompt=build_hermes_x_search_diagnostic_prompt(query), prefer_array=True)
    return run_hermes_x_search(query)


def run_x_research_harness(
    *,
    query: str,
    mode: HarnessMode = "quick",
    mock: bool = True,
    provider: str = "mock",
    output_root: Path | None = None,
) -> HarnessRunResult:
    query = (query or "").strip()
    if not query:
        raise ValueError("query is required")
    if mode not in VALID_MODES:
        raise ValueError(f"unsupported mode: {mode}")

    provider_name = (provider or "mock").strip().casefold()
    if provider_name not in VALID_PROVIDERS:
        raise ValueError(f"unsupported provider: {provider_name}")
    if mock:
        provider_name = "mock"

    started_at = timestamp()
    task = XResearchTask(query=query, mode=mode, mock=provider_name == "mock")
    task_payload = task.to_dict()
    task_payload["query"] = redact_personal_info(str(task_payload.get("query", "")))
    output_dir = build_output_dir(query, output_root=output_root)

    files: dict[str, str]
    if provider_name == "mock":
        posts = [post.to_dict() for post in MOCK_X_POSTS]
        analysis = analyze_x_claims(query, posts)
        note_material = build_note_material(analysis)
        run_plan = {
            "query": query,
            "mode": mode,
            "mock": True,
            "provider": "mock",
            "steps": ["load_mock_x_posts", "analyze_claims", "build_note_material", "save_outputs"],
            "prohibited_actions": ["post", "like", "repost", "follow", "dm", "auto_publish"],
        }
        report = {
            "status": "success",
            "provider": "mock",
            "fallback_used": False,
            "started_at": started_at,
            "finished_at": timestamp(),
            "task": task_payload | {"provider": "mock", "mock": True},
            "query": redact_personal_info(query),
            "mode": mode,
            "mock": True,
            "post_count": len(posts),
            "raw_result_count": len(posts),
            "parsed_result_count": len(posts),
            "analysis_summary": {
                "credibility_score": analysis.get("credibility_score", 0),
                "official_check_required": analysis.get("official_check_required", False),
                "exaggeration_flags": analysis.get("exaggeration_flags", []),
            },
            "output_dir": str(output_dir),
            "files": [
                "run_plan.json",
                "raw_x_results.json",
                "claim_analysis.json",
                "note_material.md",
                "sources.csv",
                "run_report.json",
            ],
            "safety": {
                "mock_only": True,
                "hermes_connected": False,
                "no_credentials_saved": True,
                "no_x_write_actions": True,
            },
        }
        files = {
            "run_plan": str(write_json(output_dir / "run_plan.json", run_plan)),
            "raw_x_results": str(write_json(output_dir / "raw_x_results.json", posts)),
            "claim_analysis": str(write_json(output_dir / "claim_analysis.json", analysis)),
            "note_material": str(write_text(output_dir / "note_material.md", note_material)),
            "sources": str(write_sources_csv(output_dir / "sources.csv", posts)),
            "run_report": str(write_json_raw(output_dir / "run_report.json", report)),
        }
        return HarnessRunResult(output_dir=str(output_dir), files=files, status="success")

    hermes_result = _run_hermes_provider(query, mode)
    hermes_response = hermes_result.get("response", {})
    provider_posts_raw = hermes_response.get("related_posts", []) if isinstance(hermes_response, dict) else []
    posts = [
        {
            "author": str(post.get("author", "")),
            "handle": str(post.get("handle", "")),
            "post_url": str(post.get("post_url", "")),
            "text": str(post.get("text") or post.get("summary") or post.get("claim") or ""),
            "engagement_hint": str(post.get("engagement_hint", "unknown")),
        }
        for post in provider_posts_raw
        if isinstance(post, dict)
    ]
    hermes_ok = hermes_result.get("status") == "success"
    hermes_error_type = "" if hermes_ok and posts else (
        "empty_result" if hermes_ok else (hermes_result.get("error_type", "unknown_error") or "unknown_error")
    )

    run_plan = {
        "query": query,
        "mode": mode,
        "mock": False,
        "provider": "hermes",
        "steps": ["run_hermes_x_search", "analyze_claims", "build_note_material", "save_outputs"],
        "prohibited_actions": ["post", "like", "repost", "follow", "dm", "auto_publish"],
        "hermes_status": hermes_result.get("status", "failed"),
        "hermes_error_type": hermes_result.get("error_type", ""),
    }

    report_base = {
        "provider": "hermes",
        "fallback_used": False,
        "hermes_status": hermes_result.get("status", "failed"),
        "hermes_error_type": hermes_error_type,
        "hermes_duration_sec": hermes_result.get("duration_sec", 0),
        "raw_result_count": len(posts),
        "parsed_result_count": len(posts),
        "started_at": started_at,
        "finished_at": timestamp(),
        "task": task_payload | {"provider": "hermes", "mock": False},
        "query": redact_personal_info(query),
        "mode": mode,
        "mock": False,
        "post_count": len(posts),
        "output_dir": str(output_dir),
        "files": [
            "run_plan.json",
            "raw_x_results.json",
            "claim_analysis.json",
            "sources.csv",
            "run_report.json",
        ],
        "safety": {
            "mock_only": False,
            "hermes_connected": hermes_ok,
            "no_credentials_saved": True,
            "no_x_write_actions": True,
        },
    }

    if hermes_ok and posts:
        analysis = analyze_x_claims(query, posts)
        note_material = build_note_material(analysis)
        report = {
            "status": "success",
            **report_base,
            "analysis_summary": {
                "credibility_score": analysis.get("credibility_score", 0),
                "official_check_required": analysis.get("official_check_required", False),
                "exaggeration_flags": analysis.get("exaggeration_flags", []),
            },
            "files": [
                "run_plan.json",
                "raw_x_results.json",
                "claim_analysis.json",
                "note_material.md",
                "sources.csv",
                "run_report.json",
            ],
        }
        files = {
            "run_plan": str(write_json(output_dir / "run_plan.json", run_plan)),
            "raw_x_results": str(write_json(output_dir / "raw_x_results.json", posts)),
            "claim_analysis": str(write_json(output_dir / "claim_analysis.json", analysis)),
            "note_material": str(write_text(output_dir / "note_material.md", note_material)),
            "sources": str(write_sources_csv(output_dir / "sources.csv", posts)),
            "run_report": str(write_json_raw(output_dir / "run_report.json", report)),
        }
        return HarnessRunResult(output_dir=str(output_dir), files=files, status="success")

    error_type = str(hermes_error_type or hermes_result.get("reason", "unknown_error") or "unknown_error")
    error_reason = "empty_result" if hermes_ok and not posts else str(hermes_result.get("reason", error_type) or error_type)
    note_material_path = output_dir / "note_material.md"
    if note_material_path.exists():
        note_material_path.unlink()
    report = {
        "status": "failed",
        **report_base,
        "reason": error_reason,
        "files": [
            "run_plan.json",
            "raw_x_results.json",
            "claim_analysis.json",
            "sources.csv",
            "run_report.json",
        ],
    }
    error_analysis = {
        "topic": query,
        "related_posts": posts,
        "source_urls": [str(post.get("post_url", "")) for post in posts if post.get("post_url")],
        "error": {
            "type": error_type,
            "reason": error_reason,
        },
        "note_article_angles": [],
    }
    files = {
        "run_plan": str(write_json(output_dir / "run_plan.json", run_plan)),
        "raw_x_results": str(write_json(output_dir / "raw_x_results.json", posts)),
        "claim_analysis": str(write_json(output_dir / "claim_analysis.json", error_analysis)),
        "sources": str(write_sources_csv(output_dir / "sources.csv", posts)),
        "run_report": str(write_json_raw(output_dir / "run_report.json", report)),
    }
    return HarnessRunResult(output_dir=str(output_dir), files=files, status="failed")
