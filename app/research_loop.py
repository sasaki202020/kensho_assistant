from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .harness.run_store import day_key, slugify, timestamp, write_json, write_text
from .harness.x_research_harness import XPost, run_x_research_harness
from .paths import RESEARCH_LOOP_DIR, ensure_runtime_dirs
from .privacy_guard import redact_personal_info
from .research.x_claim_analyzer import analyze_x_claims


VALID_MODES: set[str] = {"quick", "verify", "note", "ttp"}
VALID_PROVIDERS: set[str] = {"mock", "hermes"}


@dataclass(frozen=True)
class ResearchLoopRound:
    round_index: int
    query: str
    mode: str
    provider: str
    status: str
    confidence: float
    source_query_count: int
    source_run_count: int
    source_count: int
    unique_source_count: int
    credibility_score: float
    supporting_points: list[str] = field(default_factory=list)
    opposing_points: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    exaggeration_flags: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    official_check_required: bool = False
    follow_up_query: str = ""
    source_queries: list[str] = field(default_factory=list)
    source_runs: list[dict[str, Any]] = field(default_factory=list)
    output_dir: str = ""
    aggregated_posts_path: str = ""
    aggregated_analysis_path: str = ""
    cross_check_path: str = ""
    round_report_path: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _build_output_dir(
    question: str,
    *,
    output_root: Path | None = None,
    run_date: date | None = None,
) -> Path:
    root = output_root or RESEARCH_LOOP_DIR
    safe_question = str(redact_personal_info(question or ""))
    return root / day_key(run_date) / slugify(safe_question)


def _normalize_question(value: str) -> str:
    return redact_personal_info((value or "").strip())


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _clean_text_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned = [str(item).strip() for item in values if str(item).strip()]
    return list(dict.fromkeys(cleaned))


def _dedupe_posts(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for post in posts:
        if not isinstance(post, dict):
            continue
        key = str(
            post.get("post_url")
            or post.get("handle")
            or ""
        ).strip().casefold()
        if not key:
            text = str(post.get("text", "")).strip().casefold()
            key = f"{post.get('author', '')}|{text}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(post)
    return deduped


def _mock_posts_for_question(question: str, round_index: int) -> list[XPost]:
    base = question or "調査テーマ"
    posts = [
        XPost(
            author="support user",
            handle="@support",
            post_url=f"https://x.com/support/status/{round_index}01",
            text=f"{base} は便利です。小さく試せば有効に使えます。",
            engagement_hint="high",
        ),
        XPost(
            author="cautious user",
            handle="@caution",
            post_url=f"https://x.com/caution/status/{round_index}02",
            text=f"{base} は言いすぎになりやすいので、慎重な確認が必要です。",
            engagement_hint="medium",
        ),
    ]
    if round_index >= 2:
        posts.append(
            XPost(
                author="official-check",
                handle="@official",
                post_url=f"https://x.com/official/status/{round_index}03",
                text="公式情報や一次ソースと照合すると有効です。",
                engagement_hint="medium",
            )
        )
    if round_index >= 3:
        posts.append(
            XPost(
                author="skeptic user",
                handle="@skeptic",
                post_url=f"https://x.com/skeptic/status/{round_index}04",
                text=f"{base} は危ない言い方を避けるべきです。確認不足は避けたいです。",
                engagement_hint="low",
            )
        )
    return posts


def _source_queries(base_query: str, analysis: dict[str, Any], round_index: int) -> list[str]:
    queries: list[str] = [base_query]
    if round_index == 1:
        queries.append(f"{base_query} 公式 一次ソース")
    else:
        queries.extend(
            [
                f"{base_query} 反対意見 失敗例",
                f"{base_query} 比較 具体例",
            ]
        )
    if analysis.get("official_check_required"):
        queries.append(f"{base_query} 公式")
    if analysis.get("missing_evidence"):
        queries.append(f"{base_query} 検証条件 再現条件")
    if analysis.get("exaggeration_flags"):
        queries.append(f"{base_query} 誇張 注意点")
    cleaned: list[str] = []
    seen: set[str] = set()
    for query in queries:
        normalized = query.strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(normalized)
    return cleaned[:3]


def _follow_up_query(question: str, analysis: dict[str, Any], round_index: int) -> str:
    hints: list[str] = []
    if analysis.get("official_check_required"):
        hints.extend(["公式情報", "一次ソース"])
    if analysis.get("opposing_points"):
        hints.extend(["反対意見", "失敗例"])
    if analysis.get("missing_evidence"):
        hints.extend(["検証条件", "再現条件"])
    if analysis.get("exaggeration_flags"):
        hints.extend(["誇張", "注意点"])
    if round_index >= 2:
        hints.extend(["比較", "具体例"])
    deduped = list(dict.fromkeys(hint for hint in hints if hint.strip()))
    if not deduped:
        return question
    return f"{question} {' '.join(deduped[:4])}".strip()


def _confidence_score(
    analysis: dict[str, Any],
    *,
    source_run_count: int,
    unique_source_count: int,
    failed_source_count: int,
    round_index: int,
) -> float:
    score = float(analysis.get("credibility_score", 0.0) or 0.0)
    supporting = _clean_text_list(analysis.get("supporting_points", []))
    opposing = _clean_text_list(analysis.get("opposing_points", []))
    missing = _clean_text_list(analysis.get("missing_evidence", []))
    exaggeration = _clean_text_list(analysis.get("exaggeration_flags", []))

    score += min(0.06, 0.012 * source_run_count)
    score += min(0.05, 0.010 * unique_source_count)
    score += 0.03 if source_run_count >= 2 else 0.0
    score += 0.03 if not analysis.get("official_check_required") else 0.0
    score += min(0.05, 0.015 * max(0, round_index - 1))
    score += min(0.04, 0.010 * len(supporting))
    score -= min(0.10, 0.040 * len(opposing))
    score -= min(0.12, 0.040 * len(missing))
    score -= min(0.08, 0.040 * len(exaggeration))
    score -= min(0.10, 0.040 * failed_source_count)
    return max(0.0, min(1.0, round(score, 2)))


def _contradiction_notes(analysis: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    supporting = _clean_text_list(analysis.get("supporting_points", []))
    opposing = _clean_text_list(analysis.get("opposing_points", []))
    missing = _clean_text_list(analysis.get("missing_evidence", []))
    exaggeration = _clean_text_list(analysis.get("exaggeration_flags", []))
    if supporting and opposing:
        notes.append("賛否が混在")
    if missing:
        notes.append(f"要確認: {missing[0]}")
    if exaggeration:
        notes.append(f"誇張フラグ: {exaggeration[0]}")
    if analysis.get("official_check_required"):
        notes.append("公式情報での確認が必要")
    return notes


def _round_summary_md(round_data: dict[str, Any]) -> str:
    lines = [
        f"# Round {round_data.get('round_index', 0)}",
        "",
        f"- query: {round_data.get('query', '')}",
        f"- status: {round_data.get('status', '')}",
        f"- confidence: {round_data.get('confidence', 0):.2f}",
        f"- source_query_count: {round_data.get('source_query_count', 0)}",
        f"- source_run_count: {round_data.get('source_run_count', 0)}",
        f"- source_count: {round_data.get('source_count', 0)}",
        f"- unique_source_count: {round_data.get('unique_source_count', 0)}",
        f"- credibility_score: {round_data.get('credibility_score', 0):.2f}",
        "",
        "## Source Queries",
    ]
    for query in round_data.get("source_queries", []):
        lines.append(f"- {query}")
    lines.extend(["", "## 要約"])
    supporting = _clean_text_list(round_data.get("supporting_points", []))
    opposing = _clean_text_list(round_data.get("opposing_points", []))
    missing = _clean_text_list(round_data.get("missing_evidence", []))
    if supporting:
        lines.extend([f"- 支持: {item}" for item in supporting[:5]])
    if opposing:
        lines.extend([f"- 反対: {item}" for item in opposing[:5]])
    if missing:
        lines.extend([f"- 要確認: {item}" for item in missing[:5]])
    if not supporting and not opposing and not missing:
        lines.append("- ソース要約はまだありません")
    lines.extend(["", "## 矛盾メモ"])
    contradictions = _clean_text_list(round_data.get("contradictions", []))
    if contradictions:
        lines.extend([f"- {item}" for item in contradictions[:5]])
    else:
        lines.append("- 矛盾は目立ちません")
    return "\n".join(lines) + "\n"


def _synthesized_answer(question: str, rounds: list[dict[str, Any]], threshold: float, final_status: str) -> str:
    final_round = rounds[-1] if rounds else {}
    final_confidence = float(final_round.get("confidence", 0.0) or 0.0)
    lines = [
        "# Research loop result",
        "",
        "## リサーチクエスチョン",
        question or "-",
        "",
        "## 判定",
        "完了" if final_confidence >= threshold else "追加調査推奨",
        "",
        "## 信頼スコア",
        f"{final_confidence:.2f} / {threshold:.2f}",
        "",
        "## ステータス",
        final_status,
        "",
        "## 主要な発見",
    ]
    for round_data in rounds:
        lines.append(
            f"- Round {round_data.get('round_index', 0)}: {round_data.get('query', '')} / "
            f"confidence={round_data.get('confidence', 0):.2f} / "
            f"sources={round_data.get('source_count', 0)}"
        )
    lines.extend(["", "## 矛盾と要確認"])
    notes: list[str] = []
    for round_data in rounds:
        notes.extend(_clean_text_list(round_data.get("contradictions", [])))
    if notes:
        for note in list(dict.fromkeys(notes))[:10]:
            lines.append(f"- {note}")
    else:
        lines.append("- 目立つ矛盾はありません")
    lines.extend(["", "## 次の一手"])
    if final_confidence >= threshold:
        lines.append("- 閾値を超えたので、このテーマはここで完了")
    else:
        lines.append("- 追加の一次ソース確認か、別観点の再検索が必要")
    return "\n".join(lines) + "\n"


def run_research_loop(
    *,
    question: str,
    mode: str = "verify",
    provider: str = "mock",
    confidence_threshold: float = 0.75,
    max_rounds: int = 3,
    limit: int = 20,
    output_root: Path | None = None,
) -> dict[str, object]:
    ensure_runtime_dirs()
    question = _normalize_question(question)
    if not question:
        raise ValueError("question is required")
    if mode not in VALID_MODES:
        raise ValueError(f"unsupported mode: {mode}")

    provider_name = (provider or "mock").strip().casefold()
    if provider_name not in VALID_PROVIDERS:
        raise ValueError(f"unsupported provider: {provider_name}")

    rounds: list[dict[str, Any]] = []
    output_dir = _build_output_dir(question, output_root=output_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    plan = {
        "question": question,
        "mode": mode,
        "provider": provider_name,
        "confidence_threshold": confidence_threshold,
        "max_rounds": max_rounds,
        "limit": limit,
        "output_dir": str(output_dir),
        "steps": [
            "define_research_question",
            "search_sources",
            "summarize_findings",
            "cross_check_sources",
            "compare_contradictions",
            "synthesize_final_answer",
            "stop_on_threshold",
        ],
        "prohibited_actions": [
            "post",
            "like",
            "repost",
            "follow",
            "dm",
            "auto_publish",
        ],
        "safety_notes": [
            "個人情報はログに出さない",
            "誇張表現は一次ソースで確認する",
            "自動送信や外部投稿はしない",
        ],
    }
    write_json(output_dir / "run_plan.json", plan)

    current_query = question
    previous_analysis: dict[str, Any] = {}
    final_status = "partial"
    stop_reason = "no_rounds"
    best_confidence = 0.0

    for round_index in range(1, max(1, max_rounds) + 1):
        round_dir = output_dir / "rounds" / f"round_{round_index:02d}"
        source_queries = _source_queries(current_query, previous_analysis, round_index)
        source_runs: list[dict[str, Any]] = []
        aggregated_posts: list[dict[str, Any]] = []

        for source_index, source_query in enumerate(source_queries, start=1):
            source_root = round_dir / f"source_{source_index:02d}"
            mock_posts = _mock_posts_for_question(source_query, round_index) if provider_name == "mock" else None
            source_result = run_x_research_harness(
                query=source_query,
                mode=mode,
                mock=provider_name == "mock",
                provider=provider_name,
                mock_posts=mock_posts,
                output_root=source_root,
            )
            source_output_dir = Path(source_result.output_dir)
            source_report = _load_json(source_output_dir / "run_report.json", {})
            source_analysis = _load_json(source_output_dir / "claim_analysis.json", {})
            raw_posts = _load_json(source_output_dir / "raw_x_results.json", [])
            if not isinstance(raw_posts, list):
                raw_posts = []
            aggregated_posts.extend([post for post in raw_posts if isinstance(post, dict)])
            source_runs.append(
                {
                    "query": source_query,
                    "status": str(source_result.status),
                    "output_dir": str(source_output_dir),
                    "post_count": int(source_report.get("post_count", 0) or 0),
                    "raw_result_count": int(source_report.get("raw_result_count", 0) or 0),
                    "parsed_result_count": int(source_report.get("parsed_result_count", 0) or 0),
                    "credibility_score": float(source_analysis.get("credibility_score", 0.0) or 0.0),
                    "official_check_required": bool(source_analysis.get("official_check_required", False)),
                    "exaggeration_flags": _clean_text_list(source_analysis.get("exaggeration_flags", [])),
                    "source_urls": _clean_text_list(source_analysis.get("source_urls", [])),
                }
            )

        deduped_posts = _dedupe_posts(aggregated_posts)
        aggregated_analysis = analyze_x_claims(current_query, deduped_posts)
        source_urls = _clean_text_list(aggregated_analysis.get("source_urls", []))
        if not source_urls:
            source_urls = _clean_text_list([post.get("post_url", "") for post in deduped_posts])
        failed_source_count = sum(1 for item in source_runs if item.get("status") != "success")
        confidence = _confidence_score(
            aggregated_analysis,
            source_run_count=len(source_runs),
            unique_source_count=len(source_urls),
            failed_source_count=failed_source_count,
            round_index=round_index,
        )
        best_confidence = max(best_confidence, confidence)
        follow_up_query = _follow_up_query(question, aggregated_analysis, round_index + 1)
        contradictions = _contradiction_notes(aggregated_analysis)
        if source_runs and failed_source_count == len(source_runs):
            final_status = "failed"
            stop_reason = f"round_{round_index}_all_sources_failed"
        else:
            final_status = "success" if confidence >= confidence_threshold else "partial"
            stop_reason = "threshold_reached" if confidence >= confidence_threshold else (
                "max_rounds_reached" if round_index >= max_rounds else "continue"
            )

        round_report = {
            "round_index": round_index,
            "query": current_query,
            "mode": mode,
            "provider": provider_name,
            "status": final_status,
            "confidence": confidence,
            "source_query_count": len(source_queries),
            "source_run_count": len(source_runs),
            "source_count": len(deduped_posts),
            "unique_source_count": len(source_urls),
            "credibility_score": float(aggregated_analysis.get("credibility_score", 0.0) or 0.0),
            "supporting_points": _clean_text_list(aggregated_analysis.get("supporting_points", [])),
            "opposing_points": _clean_text_list(aggregated_analysis.get("opposing_points", [])),
            "missing_evidence": _clean_text_list(aggregated_analysis.get("missing_evidence", [])),
            "exaggeration_flags": _clean_text_list(aggregated_analysis.get("exaggeration_flags", [])),
            "contradictions": contradictions,
            "official_check_required": bool(aggregated_analysis.get("official_check_required", False)),
            "follow_up_query": follow_up_query,
            "source_queries": source_queries,
            "source_runs": source_runs,
            "source_urls": source_urls,
            "source_runs_path": str(round_dir / "source_runs.json"),
            "aggregated_posts_path": str(round_dir / "aggregated_posts.json"),
            "aggregated_analysis_path": str(round_dir / "aggregated_analysis.json"),
            "cross_check_path": str(round_dir / "cross_check.json"),
            "round_report_path": str(round_dir / "research_loop_round.json"),
        }
        round_report["round_report_path"] = str(round_dir / "research_loop_round.json")

        write_json(round_dir / "source_runs.json", source_runs)
        write_json(round_dir / "aggregated_posts.json", deduped_posts)
        write_json(round_dir / "aggregated_analysis.json", aggregated_analysis)
        write_json(
            round_dir / "cross_check.json",
            {
                "round_index": round_index,
                "query": current_query,
                "source_queries": source_queries,
                "source_run_count": len(source_runs),
                "unique_source_count": len(source_urls),
                "failed_source_count": failed_source_count,
                "supporting_points": round_report["supporting_points"],
                "opposing_points": round_report["opposing_points"],
                "missing_evidence": round_report["missing_evidence"],
                "exaggeration_flags": round_report["exaggeration_flags"],
                "contradictions": contradictions,
                "official_check_required": round_report["official_check_required"],
                "confidence": confidence,
            },
        )
        write_json(round_dir / "research_loop_round.json", round_report)
        write_text(round_dir / "research_loop_round.md", _round_summary_md(round_report))
        rounds.append(round_report)
        previous_analysis = aggregated_analysis

        if stop_reason == "round_{}_all_sources_failed".format(round_index):
            break
        if confidence >= confidence_threshold:
            break
        if round_index >= max_rounds:
            break
        current_query = follow_up_query

    final_round = rounds[-1] if rounds else {}
    final_confidence = float(final_round.get("confidence", 0.0) or 0.0)
    if final_round.get("status") == "failed":
        final_status = "failed"
        decision = "needs_more_research"
    elif final_confidence >= confidence_threshold:
        final_status = "success"
        decision = "complete"
        stop_reason = "threshold_reached"
    else:
        final_status = "partial"
        decision = "needs_more_research"
        if stop_reason == "continue":
            stop_reason = "max_rounds_reached"

    final_answer = _synthesized_answer(question, rounds, confidence_threshold, final_status)
    final_answer_path = write_text(output_dir / "final_answer.md", final_answer)
    rounds_path = write_json(output_dir / "rounds.json", rounds)
    run_report = {
        "status": final_status,
        "decision": decision,
        "question": question,
        "mode": mode,
        "provider": provider_name,
        "confidence_threshold": confidence_threshold,
        "max_rounds": max_rounds,
        "limit": limit,
        "round_count": len(rounds),
        "final_confidence": final_confidence,
        "best_confidence": best_confidence,
        "stop_reason": stop_reason,
        "rounds": rounds,
        "source_query_total": sum(int(round_data.get("source_query_count", 0) or 0) for round_data in rounds),
        "source_run_total": sum(int(round_data.get("source_run_count", 0) or 0) for round_data in rounds),
        "source_failure_total": sum(
            1
            for round_data in rounds
            for source_run in round_data.get("source_runs", [])
            if isinstance(source_run, dict) and source_run.get("status") != "success"
        ),
        "final_answer_path": str(final_answer_path),
        "rounds_path": str(rounds_path),
        "created_at": timestamp(),
        "safety": {
            "no_auto_publish": True,
            "no_personal_info_logged": True,
            "no_submit_actions": True,
        },
    }
    run_report_path = write_json(output_dir / "run_report.json", run_report)
    files = {
        "run_plan": str(output_dir / "run_plan.json"),
        "rounds": str(rounds_path),
        "final_answer": str(final_answer_path),
        "run_report": str(run_report_path),
    }
    return {
        "output_dir": str(output_dir),
        "status": final_status,
        "decision": decision,
        "final_confidence": final_confidence,
        "best_confidence": best_confidence,
        "stop_reason": stop_reason,
        "round_count": len(rounds),
        "source_query_total": run_report["source_query_total"],
        "source_run_total": run_report["source_run_total"],
        "source_failure_total": run_report["source_failure_total"],
        "final_answer_path": str(final_answer_path),
        "run_report_path": str(run_report_path),
        "rounds_path": str(rounds_path),
        "files": files,
        "rounds": rounds,
    }
