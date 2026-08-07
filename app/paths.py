from __future__ import annotations

from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PACKAGE_ROOT / "config"
DATA_DIR = PACKAGE_ROOT / "data"
LATER_QUEUE_DIR = DATA_DIR / "queue"
AGENT_STATUS_DIR = DATA_DIR / "agent_status"
AGENT_ORG_JSON = AGENT_STATUS_DIR / "agent_org.json"
AGENT_ORG_SAMPLE_JSON = AGENT_STATUS_DIR / "agent_org.sample.json"
AGENT_CONTROL_DIR = DATA_DIR / "agent_control"
AGENT_CONTROL_JOBS_JSONL = AGENT_CONTROL_DIR / "jobs.jsonl"
AGENT_CONTROL_STATUS_JSON = AGENT_CONTROL_DIR / "agent_status.json"
AGENT_CONTROL_EVENTS_JSONL = AGENT_CONTROL_DIR / "control_events.jsonl"
RESEARCH_DIR = DATA_DIR / "research"
RESEARCH_X_DIR = RESEARCH_DIR / "x"
RESEARCH_X_SEARCH_DIR = RESEARCH_DIR / "x_search"
RESEARCH_X_HARNESS_DIR = RESEARCH_DIR / "x_harness"
RESEARCH_LOOP_DIR = RESEARCH_DIR / "loop"
RESEARCH_KENSHO_HARNESS_DIR = RESEARCH_DIR / "kensho_harness"
X_POST_DIR = DATA_DIR / "x_post"
X_POST_RUNS_DIR = X_POST_DIR / "runs"
X_POST_HISTORY_JSONL = X_POST_DIR / "post_history.jsonl"
RESEARCH_X_HARNESS_DIAGNOSTICS_DIR = RESEARCH_X_HARNESS_DIR / "diagnostics"
RESEARCH_X_HARNESS_DIAGNOSTICS_JSON = RESEARCH_X_HARNESS_DIAGNOSTICS_DIR / "hermes_x_search_check.json"
RESEARCH_X_DIAGNOSTICS_DIR = RESEARCH_X_DIR / "diagnostics"
RESEARCH_X_DIAGNOSTICS_JSON = RESEARCH_X_DIAGNOSTICS_DIR / "hermes_x_search_check.json"
DOCS_DIR = PACKAGE_ROOT / "docs"
SAMPLES_DIR = PACKAGE_ROOT / "samples"
REPORTS_DIR = PACKAGE_ROOT / "reports"
LOGS_DIR = PACKAGE_ROOT / "logs"
SCREENSHOTS_DIR = PACKAGE_ROOT / "screenshots"
BEFORE_SUBMIT_DIR = SCREENSHOTS_DIR / "before_submit"
AFTER_SUBMIT_DIR = SCREENSHOTS_DIR / "after_submit"
DRY_RUN_SCREENSHOTS_DIR = SCREENSHOTS_DIR / "dry_run"
APP_DIR = PACKAGE_ROOT / "app"
MAIL_SAMPLES_DIR = SAMPLES_DIR / "mail"
BROWSER_PROFILE_DIR = PACKAGE_ROOT / "browser_profile"
CHROME_USER_DATA_DIR = BROWSER_PROFILE_DIR / "chrome_user_data"
ALLOWED_SUBMIT_DOMAINS_JSON = CONFIG_DIR / "allowed_submit_domains.json"
SITE_TEMPLATES_JSON = CONFIG_DIR / "site_templates.json"
FORM_ANALYSIS_DIR = DATA_DIR / "form_analysis"
PRE_SUBMIT_CHECKS_DIR = DATA_DIR / "pre_submit_checks"
APPLY_RUNS_DIR = DATA_DIR / "apply_runs"
DRY_RUN_SNAPSHOTS_DIR = DATA_DIR / "dry_run_snapshots"
PREPARE_ALL_DIR = DATA_DIR / "prepare_all"
PREPARE_ALL_STATUS_JSON = PREPARE_ALL_DIR / "status.json"
ASSISTED_SESSION_DIR = DATA_DIR / "assisted_session"
ASSISTED_SESSION_STATE_JSON = ASSISTED_SESSION_DIR / "session.json"
REAL_SITE_TRIALS_DIR = DATA_DIR / "real_site_trials"
REAL_SITE_TRIALS_JSONL = REAL_SITE_TRIALS_DIR / "trials.jsonl"
REAL_SITE_TRIAL_STEPS_JSONL = REAL_SITE_TRIALS_DIR / "steps.jsonl"
REAL_SITE_TRIAL_REPORTS_DIR = REPORTS_DIR / "real_site_trials"
PILOT_DIR = DATA_DIR / "pilot"
PILOT_MANIFESTS_DIR = PILOT_DIR / "manifests"
PILOT_RUNS_DIR = PILOT_DIR / "runs"
PILOT_EVIDENCE_DIR = PILOT_DIR / "evidence"
PILOT_REPORTS_DIR = PILOT_DIR / "reports"
PILOT_TRIALS_JSONL = PILOT_RUNS_DIR / "trials.jsonl"

CAMPAIGNS_CSV = DATA_DIR / "campaigns.csv"
SELECTED_CAMPAIGNS_CSV = DATA_DIR / "selected_campaigns.csv"
ENTRIES_CSV = DATA_DIR / "entries.csv"
ENTRY_HISTORY_DIR = DATA_DIR / "entries"
ENTRY_HISTORY_JSONL = ENTRY_HISTORY_DIR / "entry_history.jsonl"
ENTRY_HISTORY_CSV = ENTRY_HISTORY_DIR / "entry_history.csv"
WIN_MAIL_CANDIDATES_JSONL = ENTRY_HISTORY_DIR / "win_mail_candidates.jsonl"
LATER_QUEUE_JSONL = LATER_QUEUE_DIR / "later_apply_queue.jsonl"
AGENT_STATUS_JSON = AGENT_STATUS_DIR / "agent_status.json"
AGENT_STATUS_SAMPLE_JSON = AGENT_STATUS_DIR / "agent_status.sample.json"
AGENT_RUN_LOG_JSONL = AGENT_STATUS_DIR / "agent_run_log.jsonl"
BLOCKED_CSV = DATA_DIR / "blocked.csv"
HOLDS_CSV = DATA_DIR / "holds.csv"
FORM_INSPECTIONS_JSONL = DATA_DIR / "form_inspections.jsonl"
APPLY_QUEUE_CSV = DATA_DIR / "apply_queue.csv"
MAIL_SWEEPSTAKES_JSON = DATA_DIR / "mail_sweepstakes.json"
RELEASE_REPORT_MD = REPORTS_DIR / "release_report_v0.1.md"
RELEASE_REPORT_JSON = REPORTS_DIR / "release_report_v0.1.json"
RELEASE_REPORT_V02_MD = REPORTS_DIR / "release_report_v0.2.md"
RELEASE_REPORT_V02_JSON = REPORTS_DIR / "release_report_v0.2.json"
RELEASE_REPORT_V03_MD = REPORTS_DIR / "release_report_v0.3.md"
RELEASE_REPORT_V03_JSON = REPORTS_DIR / "release_report_v0.3.json"
RELEASE_REPORT_V04_MD = REPORTS_DIR / "release_report_v0.4.md"
RELEASE_REPORT_V04_JSON = REPORTS_DIR / "release_report_v0.4.json"
APPLY_QUEUE_MD = REPORTS_DIR / "apply_queue_latest.md"
APPLY_QUEUE_JSON = REPORTS_DIR / "apply_queue_latest.json"
AUTO_SCAN_MD = REPORTS_DIR / "auto_scan_latest.md"
AUTO_SCAN_JSON = REPORTS_DIR / "auto_scan_latest.json"
RESEARCH_REPORT_MD = REPORTS_DIR / "research_report_latest.md"
RESEARCH_REPORT_JSON = REPORTS_DIR / "research_report_latest.json"
SELF_TEST_LOG_MD = DOCS_DIR / "SELF_TEST_LOG.md"
RUN_LOG = LOGS_DIR / "run.jsonl"
PROFILE_JSON = CONFIG_DIR / "profile.json"
PROFILE_EXAMPLE_JSON = CONFIG_DIR / "profile.example.json"
RULES_YAML = CONFIG_DIR / "rules.yaml"
PRODUCT_YAML = CONFIG_DIR / "product.yaml"


def ensure_runtime_dirs() -> None:
    for path in (
        CONFIG_DIR,
        DATA_DIR,
        LATER_QUEUE_DIR,
        AGENT_STATUS_DIR,
        AGENT_CONTROL_DIR,
        ENTRY_HISTORY_DIR,
        RESEARCH_DIR,
        RESEARCH_X_DIR,
        RESEARCH_X_SEARCH_DIR,
        RESEARCH_X_HARNESS_DIR,
        RESEARCH_LOOP_DIR,
        RESEARCH_KENSHO_HARNESS_DIR,
        X_POST_DIR,
        X_POST_RUNS_DIR,
        RESEARCH_X_HARNESS_DIAGNOSTICS_DIR,
        RESEARCH_X_DIAGNOSTICS_DIR,
        DOCS_DIR,
        REPORTS_DIR,
        LOGS_DIR,
        SCREENSHOTS_DIR,
        BEFORE_SUBMIT_DIR,
        AFTER_SUBMIT_DIR,
        DRY_RUN_SCREENSHOTS_DIR,
        CHROME_USER_DATA_DIR,
        FORM_ANALYSIS_DIR,
        PRE_SUBMIT_CHECKS_DIR,
        APPLY_RUNS_DIR,
        DRY_RUN_SNAPSHOTS_DIR,
        PREPARE_ALL_DIR,
        ASSISTED_SESSION_DIR,
        REAL_SITE_TRIALS_DIR,
        REAL_SITE_TRIAL_REPORTS_DIR,
        PILOT_MANIFESTS_DIR,
        PILOT_DIR,
        PILOT_RUNS_DIR,
        PILOT_EVIDENCE_DIR,
        PILOT_REPORTS_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
