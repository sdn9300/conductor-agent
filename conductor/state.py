"""
State and Schema definitions for Conductor Agent.
Implements Candidate Profile JSON schema (CND-ARCH §3.1), ConductorState (CND-ARCH §3.2),
CompanyBriefRef (Research Agent #4), AutoApplyRef (PDF Auto-Apply #5), and SentimentSignal (Phase 3).
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Literal
from uuid import uuid4
from pydantic import BaseModel, Field


def get_utc_now_iso() -> str:
    """Return ISO format UTC timestamp string."""
    return datetime.now(timezone.utc).isoformat()


class PostingRef(BaseModel):
    """Reference metadata and content of a discovered or seed job posting."""
    company: str
    title: str
    jd_text: str = Field(..., min_length=20)
    url: Optional[str] = None
    location: Optional[str] = None
    contact_email: Optional[str] = None
    contact_name: Optional[str] = None
    source: str = "manual"  # "remoteok" | "indeed" | "wellfound" | "naukri" | "manual"
    application_channel: Literal["auto", "email", "form"] = "auto"
    posted_at: Optional[str] = None
    requirements: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompanyBriefRef(BaseModel):
    """Company research intelligence produced by Research Agent (#4)."""
    company_name: str
    summary: str
    tech_signals: List[str] = Field(default_factory=list)
    recent_news: List[Dict[str, str]] = Field(default_factory=list)
    culture_notes: str = ""
    confidence_flags: List[str] = Field(default_factory=list)
    source_count: int = 0
    created_at: str = Field(default_factory=get_utc_now_iso)


class SentimentSignal(BaseModel):
    """Outcome classification signal ingested from Sentiment Classifier (#9)."""
    response_id: Optional[str] = None
    macro_sentiment: Optional[Literal["positive", "neutral", "negative"]] = "neutral"
    intent_label: Optional[str] = "under_review"  # e.g., "interview_invite", "soft_rejection", "hard_rejection", etc.
    urgency_score: Optional[int] = 3  # 1 to 5
    confidence: Optional[float] = 1.0
    recommended_action: Optional[str] = None
    key_phrases: List[str] = Field(default_factory=list)
    requires_manual_review: bool = False
    flagged_for_conductor: bool = False
    raw_response: Optional[str] = None
    classified_at: str = Field(default_factory=get_utc_now_iso)


class TailoredResumeRef(BaseModel):
    """Tailored resume artifact and gap analysis produced by AlignResume (#2)."""
    run_id: Optional[str] = None
    tailored_content: Optional[str] = None
    diff_summary: Optional[str] = None
    match_score: Optional[float] = None
    skills_matched: List[str] = Field(default_factory=list)
    skills_gap: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=get_utc_now_iso)


class OutreachRef(BaseModel):
    """Outreach draft and send execution details produced by Overture (#3)."""
    draft_subject: Optional[str] = None
    draft_body: Optional[str] = None
    personalization_score: Optional[int] = None
    word_count: Optional[int] = None
    mode: Optional[str] = None  # "send" | "draft" | "dry_run"
    status: Optional[str] = None  # "sent" | "drafted" | "dry_run" | "skipped" | "failed"
    message_id: Optional[str] = None
    error: Optional[str] = None
    sent_at: Optional[str] = None


class AutoApplyRef(BaseModel):
    """Portal / web-form application submission details produced by PDF Auto-Apply (#5)."""
    submission_id: str = Field(default_factory=lambda: f"apply_{uuid4().hex[:8]}")
    portal_url: Optional[str] = None
    pdf_resume_path: Optional[str] = None
    cover_note: Optional[str] = None
    fields_submitted: Dict[str, Any] = Field(default_factory=dict)
    mode: str = "dry_run"  # "dry_run" | "live_submit"
    status: str = "submitted"  # "submitted" | "dry_run" | "failed"
    submitted_at: Optional[str] = Field(default_factory=get_utc_now_iso)
    error: Optional[str] = None


ApplicationStatus = Literal[
    "discovered",
    "researched",
    "skipped_duplicate",
    "skipped_cooldown",
    "tailored",
    "outreach_pending_review",
    "outreach_approved",
    "outreach_rejected",
    "outreach_sent",
    "auto_apply_pending_review",
    "auto_applied",
    "responded",
    "interview_scheduled",
    "closed",
    "error"
]


class ApplicationRecord(BaseModel):
    """Lifecycle record for a single job opportunity in the Candidate Profile."""
    job_id: str = Field(default_factory=lambda: str(uuid4()))
    source: str = "manual"  # "harvester" | "manual" | "remoteok" | ...
    posting: PostingRef
    status: ApplicationStatus = "discovered"
    company_brief: Optional[CompanyBriefRef] = None
    tailored_resume: Optional[TailoredResumeRef] = None
    outreach: Optional[OutreachRef] = None
    auto_apply: Optional[AutoApplyRef] = None
    sentiment_signal: Optional[SentimentSignal] = None
    timestamps: Dict[str, str] = Field(default_factory=lambda: {"discovered": get_utc_now_iso()})
    error: Optional[str] = None
    checkpoint: Optional[str] = None

    def update_timestamp(self, stage: str) -> None:
        """Record timestamp for a lifecycle milestone."""
        self.timestamps[stage] = get_utc_now_iso()
        self.timestamps["last_updated"] = get_utc_now_iso()


class CandidateProfile(BaseModel):
    """Canonical shared-state object representing the candidate's active search."""
    candidate_id: str = "sdn9300"
    candidate_name: str = "Soumyadeep Nath"
    candidate_email: str = "soumyadeepnath@example.com"
    candidate_phone: str = "+1 (555) 019-2834"
    portfolio_url: str = "https://github.com/sdn9300"
    resume_master_ref: str = "align-resume/base-v12"
    master_resume_content: Optional[str] = None
    target_roles: List[str] = Field(
        default_factory=lambda: ["AI Engineer", "Data Scientist", "GenAI Engineer"]
    )
    baseline_optimizations: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    applications: List[ApplicationRecord] = Field(default_factory=list)
    created_at: str = Field(default_factory=get_utc_now_iso)
    updated_at: str = Field(default_factory=get_utc_now_iso)


class ConductorState(BaseModel):
    """
    State object passed between LangGraph nodes during a single job execution run.
    Encapsulates one ApplicationRecord plus run-scoped execution trace and error logs.
    """
    candidate_id: str = "sdn9300"
    job_id: str
    application: ApplicationRecord
    master_resume_text: str = ""
    target_channel: Literal["auto", "email", "form"] = "auto"
    current_node: str = "entry"
    node_trace: List[str] = Field(default_factory=list)
    human_approval: Optional[Literal["approve", "edit", "reject", "abort"]] = None
    human_review_notes: Optional[str] = None
    errors: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    run_id: str = Field(default_factory=lambda: str(uuid4()))

    def record_node(self, node_name: str) -> None:
        """Append node execution to trace."""
        self.current_node = node_name
        self.node_trace.append(node_name)
        self.application.checkpoint = node_name
        self.application.update_timestamp(node_name)

    def record_error(self, err_msg: str) -> None:
        """Append error to trace and update application status without crashing."""
        self.errors.append(err_msg)
        self.application.error = err_msg
        self.application.status = "error"
        self.application.update_timestamp("error")
