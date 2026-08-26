"""
LangGraph Nodes for Conductor Agent Workflow.
Implements the full 10-component orchestration pipeline:
Harvester -> Deduplication/Cooldown -> Research Agent -> AlignResume -> Human Gate -> [Overture / PDF Auto-Apply] -> MemoryStore
"""

import time
from typing import Any, Callable, Dict, Optional

from conductor.adapters.align_resume import AlignResumeAdapter
from conductor.adapters.auto_apply import PDFAutoApplyAdapter
from conductor.adapters.base import AgentAdapter
from conductor.adapters.harvester import HarvesterAdapter
from conductor.adapters.overture import OvertureAdapter
from conductor.adapters.research import ResearchAgentAdapter
from conductor.adapters.sentiment import SentimentClassifierAdapter
from conductor.config import config
from conductor.metrics import (
    conductor_human_gate_actions_total,
    conductor_node_duration_seconds,
    conductor_node_errors_total,
    conductor_runs_total,
    conductor_token_cost_total,
)
from conductor.state import (
    AutoApplyRef,
    CandidateProfile,
    CompanyBriefRef,
    ConductorState,
    OutreachRef,
    PostingRef,
    SentimentSignal,
    TailoredResumeRef,
)
from conductor.storage.base import MemoryStore
from conductor.storage.local_store import SQLiteMemoryStore


class NodeContext:
    """Dependency container for graph nodes."""

    def __init__(
        self,
        harvester_adapter: Optional[AgentAdapter] = None,
        research_adapter: Optional[ResearchAgentAdapter] = None,
        align_resume_adapter: Optional[AlignResumeAdapter] = None,
        overture_adapter: Optional[OvertureAdapter] = None,
        auto_apply_adapter: Optional[PDFAutoApplyAdapter] = None,
        sentiment_adapter: Optional[SentimentClassifierAdapter] = None,
        memory_store: Optional[MemoryStore] = None,
        human_gate_callback: Optional[Callable[[ConductorState], str]] = None,
    ):
        self.harvester_adapter = harvester_adapter or HarvesterAdapter()
        self.research_adapter = research_adapter or ResearchAgentAdapter()
        self.align_resume_adapter = align_resume_adapter or AlignResumeAdapter()
        self.overture_adapter = overture_adapter or OvertureAdapter(dry_run=config.DRY_RUN)
        self.auto_apply_adapter = auto_apply_adapter or PDFAutoApplyAdapter(dry_run=config.DRY_RUN)
        self.sentiment_adapter = sentiment_adapter or SentimentClassifierAdapter()
        self.memory_store = memory_store or SQLiteMemoryStore(config.SQLITE_DB_PATH)
        self.human_gate_callback = human_gate_callback


def discover_node(state: ConductorState, context: NodeContext) -> ConductorState:
    """
    Ingest opportunity via Harvester, validate schema, check deduplication (EC-06),
    and check company cooldown suppression (EC-07 / Task 3.3).
    """
    start = time.time()
    state.record_node("discover")
    try:
        res = context.harvester_adapter.invoke(state.model_dump())
        if not res.success:
            state.record_error(res.error or "Harvester discovery failed.")
            conductor_node_errors_total.labels(node="discover").inc()
            return state

        out = res.output or {}
        if "posting" in out:
            posting_data = out["posting"]
            if isinstance(posting_data, dict):
                state.application.posting = PostingRef.model_validate(posting_data)
            elif isinstance(posting_data, PostingRef):
                state.application.posting = posting_data

        posting = state.application.posting

        # 1. Deduplication Check (Task 2.4 & EC-06)
        if context.memory_store.is_duplicate_posting(
            link=posting.url,
            company=posting.company,
            title=posting.title,
        ):
            print(f"[Conductor Dedupe] Skipping duplicate posting: {posting.company} - {posting.title}")
            state.application.status = "skipped_duplicate"
            state.metadata["skip_reason"] = "duplicate_posting"
            return state

        # 2. Sentiment / Cooldown Suppression Check (Task 3.3 & EC-07)
        if context.memory_store.is_company_in_cooldown(
            company=posting.company,
            cooldown_days=config.COOLDOWN_DAYS,
        ):
            print(f"[Conductor Feedback] Company '{posting.company}' is in cooldown. Suppressing outreach.")
            state.application.status = "skipped_cooldown"
            state.metadata["skip_reason"] = "company_in_cooldown"
            return state

        state.application.status = "discovered"

    except Exception as e:
        state.record_error(f"discover_node unexpected exception: {str(e)}")
        conductor_node_errors_total.labels(node="discover").inc()
    finally:
        duration = time.time() - start
        conductor_node_duration_seconds.labels(node="discover").observe(duration)
    return state


def research_node(state: ConductorState, context: NodeContext) -> ConductorState:
    """
    Enrich job opportunity with deep company intelligence via Research Agent (#4).
    Produces CompanyBrief with tech signals, news, and culture notes.
    """
    start = time.time()
    state.record_node("research")
    try:
        if state.application.status in ("error", "skipped_duplicate", "skipped_cooldown"):
            return state

        res = context.research_adapter.invoke(state.model_dump())
        if res.success and res.output and "company_brief" in res.output:
            brief_data = res.output["company_brief"]
            state.application.company_brief = CompanyBriefRef.model_validate(brief_data)
            state.application.status = "researched"
        else:
            state.record_error(res.error or "Research Agent failed to produce company brief.")
            conductor_node_errors_total.labels(node="research").inc()

    except Exception as e:
        state.record_error(f"research_node unexpected exception: {str(e)}")
        conductor_node_errors_total.labels(node="research").inc()
    finally:
        duration = time.time() - start
        conductor_node_duration_seconds.labels(node="research").observe(duration)
    return state


def tailor_node(state: ConductorState, context: NodeContext) -> ConductorState:
    """
    Tailor resume against discovered JD enriched with Research Agent company intelligence.
    """
    start = time.time()
    state.record_node("tailor")
    try:
        if state.application.status in ("error", "skipped_duplicate", "skipped_cooldown"):
            return state

        state_dict = state.model_dump()
        posting = state.application.posting
        brief = state.application.company_brief

        # Context enrichment: inject company intelligence into tailoring payload
        if brief:
            enriched_jd = (
                f"{posting.jd_text}\n\n"
                f"[Company Intelligence - {brief.company_name}]\n"
                f"Core Tech Signals: {', '.join(brief.tech_signals)}\n"
                f"Culture & Mission: {brief.culture_notes}\n"
            )
            state_dict["application"]["posting"]["jd_text"] = enriched_jd

        res = context.align_resume_adapter.invoke(state_dict)
        if not res.success:
            state.record_error(res.error or "AlignResume tailoring failed.")
            conductor_node_errors_total.labels(node="tailor").inc()
        else:
            out = res.output or {}
            state.application.tailored_resume = TailoredResumeRef(
                run_id=out.get("run_id"),
                tailored_content=out.get("tailored_content"),
                diff_summary=out.get("diff_summary"),
                match_score=out.get("match_score"),
                skills_matched=out.get("skills_matched", []),
                skills_gap=out.get("skills_gap", []),
            )
            state.application.status = "outreach_pending_review"
            if res.cost_estimate:
                conductor_token_cost_total.labels(component="align_resume").inc(res.cost_estimate)
    except Exception as e:
        state.record_error(f"tailor_node unexpected exception: {str(e)}")
        conductor_node_errors_total.labels(node="tailor").inc()
    finally:
        duration = time.time() - start
        conductor_node_duration_seconds.labels(node="tailor").observe(duration)
    return state


def human_gate_node(state: ConductorState, context: NodeContext) -> ConductorState:
    """
    Human Approval Gate (ADR-6 & EC-13).
    Inspects candidate tailored resume and prepared application payload before send/submit.
    """
    start = time.time()
    state.record_node("human_gate")
    try:
        if state.application.status in ("error", "skipped_duplicate", "skipped_cooldown"):
            return state

        posting = state.application.posting
        brief = state.application.company_brief

        # Prepare draft info for outreach path
        contact = {
            "company": posting.company,
            "role": posting.title,
            "recipient_email": posting.contact_email or f"recruiting@{posting.company.lower().replace(' ', '')}.com",
            "recipient_name": posting.contact_name or "Hiring Team",
            "job_url": posting.url or "",
            "candidate_name": config.CANDIDATE_NAME,
            "candidate_background": "AI & Agentic Systems Engineer",
            "portfolio_url": config.CANDIDATE_PORTFOLIO,
            "personalization_note": (
                f"how {posting.company} leverages {', '.join(brief.tech_signals[:2])} for its systems"
                if brief and brief.tech_signals
                else f"how {posting.company} approaches engineering in this domain"
            ),
        }
        if hasattr(context.overture_adapter, "draft_email"):
            draft_info = context.overture_adapter.draft_email(contact, use_llm=bool(config.GROQ_API_KEY))
        else:
            draft_info = {
                "draft_subject": f"Application for {posting.title} at {posting.company}",
                "draft_body": f"Hi,\n\nI am applying for the {posting.title} role at {posting.company}.",
            }
        state.application.outreach = OutreachRef(**draft_info)

        # Determine approval action
        action = None
        if context.human_gate_callback:
            action = context.human_gate_callback(state)
        elif config.AUTO_APPROVE:
            action = "approve"
        else:
            action = _prompt_user_interactive(state)

        action = (action or "abort").lower().strip()
        state.human_approval = action  # type: ignore
        conductor_human_gate_actions_total.labels(action=action).inc()

        if action in ("approve", "edit"):
            state.application.status = "outreach_approved"
        elif action == "reject":
            state.application.status = "outreach_rejected"
        else:
            state.application.status = "closed"

    except Exception as e:
        state.record_error(f"human_gate_node unexpected exception: {str(e)}")
        conductor_node_errors_total.labels(node="human_gate").inc()
    finally:
        duration = time.time() - start
        conductor_node_duration_seconds.labels(node="human_gate").observe(duration)
    return state


def outreach_node(state: ConductorState, context: NodeContext) -> ConductorState:
    """Dispatch cold email via Overture."""
    start = time.time()
    state.record_node("outreach")
    try:
        if state.application.status in ("error", "skipped_duplicate", "skipped_cooldown"):
            return state

        if state.human_approval not in ("approve", "edit"):
            err = f"Human gate bypass attempted! Approval is '{state.human_approval}'. Halting send."
            state.record_error(err)
            conductor_node_errors_total.labels(node="outreach").inc()
            return state

        res = context.overture_adapter.invoke(state.model_dump())
        if not res.success:
            state.record_error(res.error or "Overture send failed.")
            conductor_node_errors_total.labels(node="outreach").inc()
        else:
            out = res.output or {}
            state.application.outreach = OutreachRef(
                draft_subject=out.get("draft_subject"),
                draft_body=out.get("draft_body"),
                personalization_score=out.get("personalization_score"),
                word_count=out.get("word_count"),
                mode=out.get("mode"),
                status=out.get("status"),
                message_id=out.get("message_id"),
                error=out.get("error"),
                sent_at=out.get("sent_at"),
            )
            state.application.status = "outreach_sent"

    except Exception as e:
        state.record_error(f"outreach_node unexpected exception: {str(e)}")
        conductor_node_errors_total.labels(node="outreach").inc()
    finally:
        duration = time.time() - start
        conductor_node_duration_seconds.labels(node="outreach").observe(duration)
    return state


def auto_apply_node(state: ConductorState, context: NodeContext) -> ConductorState:
    """Compile PDF resume artifact and submit portal application form via PDF Auto-Apply (#5)."""
    start = time.time()
    state.record_node("auto_apply")
    try:
        if state.application.status in ("error", "skipped_duplicate", "skipped_cooldown"):
            return state

        if state.human_approval not in ("approve", "edit"):
            err = f"Human gate bypass attempted! Approval is '{state.human_approval}'. Halting form application."
            state.record_error(err)
            conductor_node_errors_total.labels(node="auto_apply").inc()
            return state

        res = context.auto_apply_adapter.invoke(state.model_dump())
        if not res.success:
            state.record_error(res.error or "PDF Auto-Apply submission failed.")
            conductor_node_errors_total.labels(node="auto_apply").inc()
        else:
            out = res.output or {}
            auto_data = out.get("auto_apply", {})
            state.application.auto_apply = AutoApplyRef.model_validate(auto_data)
            state.application.status = "auto_applied"

    except Exception as e:
        state.record_error(f"auto_apply_node unexpected exception: {str(e)}")
        conductor_node_errors_total.labels(node="auto_apply").inc()
    finally:
        duration = time.time() - start
        conductor_node_duration_seconds.labels(node="auto_apply").observe(duration)
    return state


def persist_node(state: ConductorState, context: NodeContext) -> ConductorState:
    """Durable checkpoint persistence and final metrics emit (ADR-2 & ADR-4)."""
    start = time.time()
    state.record_node("persist")
    try:
        context.memory_store.save_application(state.application)

        final_status = state.application.status
        metric_label = (
            "completed" if final_status in ("outreach_sent", "auto_applied")
            else "failed" if final_status == "error"
            else "rejected" if final_status == "outreach_rejected"
            else "skipped_duplicate" if final_status == "skipped_duplicate"
            else "skipped_cooldown" if final_status == "skipped_cooldown"
            else "aborted"
        )
        conductor_runs_total.labels(status=metric_label).inc()

    except Exception as e:
        print(f"[PersistNode ERROR] Failed to persist state: {e}")
        state.record_error(f"persist_node unexpected exception: {str(e)}")
    finally:
        duration = time.time() - start
        conductor_node_duration_seconds.labels(node="persist").observe(duration)
    return state


def execute_tier0_baseline(
    role: str,
    master_resume_text: str,
    context: NodeContext,
) -> Dict[str, Any]:
    """
    Tier-0 Baseline Pass (ADR-1).
    Periodically re-optimizes master resume against a general target-role profile.
    Decoupled from the per-job loop.
    """
    general_jd = (
        f"General target role profile for {role}. "
        f"Key competencies include multi-agent orchestration, LangGraph state machine development, "
        f"LLM API integration, evaluation and failure injection, distributed backend systems, and Python."
    )

    state_dict = {
        "master_resume_text": master_resume_text,
        "application": {
            "posting": {
                "company": "Industry Benchmark",
                "title": role,
                "jd_text": general_jd,
            }
        }
    }

    res = context.align_resume_adapter.invoke(state_dict)
    if res.success and res.output:
        profile = context.memory_store.get_candidate_profile(config.CANDIDATE_ID) or CandidateProfile()
        profile.baseline_optimizations[role] = {
            "optimized_content": res.output.get("tailored_content"),
            "match_score": res.output.get("match_score"),
            "skills_matched": res.output.get("skills_matched", []),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        context.memory_store.save_candidate_profile(profile)
        return {
            "success": True,
            "role": role,
            "optimization": profile.baseline_optimizations[role],
        }

    return {"success": False, "error": res.error or "Baseline optimization failed"}


def _prompt_user_interactive(state: ConductorState) -> str:
    """Terminal interactive display for the human approval gate."""
    SEP = "=" * 65
    DASH = "-" * 65
    app = state.application
    posting = app.posting
    brief = app.company_brief

    print(f"\n{SEP}")
    print("  [CONDUCTOR] HUMAN-IN-THE-LOOP APPROVAL GATE (ADR-6)")
    print(SEP)
    print(f"  Target Company: {posting.company}")
    print(f"  Target Role:    {posting.title}")
    if brief:
        print(f"  Tech Signals:   {', '.join(brief.tech_signals)}")
    if app.tailored_resume:
        print(f"  Match Score:    {app.tailored_resume.match_score}%")
        print(f"  Skills Matched: {', '.join(app.tailored_resume.skills_matched)}")

    if app.outreach:
        print(f"\n  Application Preview ({state.target_channel.upper()}):")
        print(f"  Email Subject:  {app.outreach.draft_subject}")
        print(f"  {DASH}")
        for line in (app.outreach.draft_body or "").split("\n"):
            print(f"  {line}")
        print(f"  {DASH}")

    print("\n  Actions:")
    print("  [a] Approve & Submit/Send")
    print("  [r] Reject Application")
    print("  [q] Quit / Abort Run")

    while True:
        try:
            choice = input("  Enter action (a/r/q): ").strip().lower()
            if choice in ("a", "approve"):
                return "approve"
            if choice in ("r", "reject"):
                return "reject"
            if choice in ("q", "quit", "abort"):
                return "abort"
            print("  Invalid choice. Please enter 'a', 'r', or 'q'.")
        except (EOFError, KeyboardInterrupt):
            return "abort"
