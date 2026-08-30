"""
Event-Sourced MemoryStore implementation for Conductor Agent (#6).
Bridges Conductor's abstract MemoryStore interface to the standalone
Memory Module (#8) event-sourced ledger (ADR-2 & ADR-8).
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import json

from conductor.config import config
from conductor.state import (
    ApplicationRecord as ConductorAppRecord,
    CandidateProfile as ConductorCandidateProfile,
    PostingRef,
    SentimentSignal as ConductorSentimentSignal,
    TailoredResumeRef,
    OutreachRef,
    AutoApplyRef,
)
from conductor.storage.base import MemoryStore as ConductorMemoryStoreInterface

# Import standalone Memory Module (#8) components
from src.store import MemoryStore as StandaloneEventLedger
from src.models import (
    ApplicationStatus as StandaloneAppStatus,
    MemoryEvent,
    EventType,
)
from src.adapters import (
    from_harvester_event,
    from_align_resume_event,
    from_overture_event,
    from_auto_apply_receipt,
    from_classified_signal,
)

logger = logging.getLogger("conductor.storage.event_sourced")


class EventSourcedMemoryStore(ConductorMemoryStoreInterface):
    """
    Event-Sourced MemoryStore delegating to CareerOS Memory Module (#8).
    Maintains business-domain audit ledger in memory_events while presenting
    the canonical Conductor MemoryStore interface to LangGraph nodes.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or config.MEMORY_MODULE_DB_PATH)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._ledger = StandaloneEventLedger(db_path=self.db_path)
        self._cached_profiles: Dict[str, ConductorCandidateProfile] = {}

    # -------------------------------------------------------------------
    # Helper / Conversion Methods
    # -------------------------------------------------------------------

    def _to_conductor_record(self, raw_app) -> ConductorAppRecord:
        """Converts a standalone ApplicationRecord or dict into a Conductor ApplicationRecord."""
        # Find events to reconstruct posting and artifacts if available
        events = self._ledger.get_history(raw_app.application_id)
        
        company = raw_app.company
        title = raw_app.role_title
        domain = raw_app.domain
        url = None
        jd_text = ""
        contact_email = None
        contact_name = None
        channel = "auto"
        tailored_resume = None
        outreach = None
        auto_apply = None
        sentiment_signal = None
        timestamps: Dict[str, str] = {
            "created_at": raw_app.created_at.isoformat(),
            "last_updated": raw_app.last_updated.isoformat(),
        }

        for ev in events:
            p = ev.payload or {}
            timestamps[ev.event_type.value] = ev.occurred_at.isoformat()

            if ev.event_type == EventType.JOB_DISCOVERED:
                url = p.get("url") or p.get("apply_url") or url
                jd_text = p.get("jd_text") or p.get("description") or jd_text
                contact_email = p.get("contact_email") or contact_email
                contact_name = p.get("contact_name") or contact_name
                channel = p.get("application_channel") or p.get("channel") or channel

            elif ev.event_type == EventType.RESUME_TAILORED:
                tailored_resume = TailoredResumeRef(
                    run_id=p.get("run_id") or p.get("tailoring_run_id") or "align-run",
                    tailored_content=p.get("tailored_content") or "",
                    diff_summary=p.get("diff_summary") or p.get("resume_diff_summary") or "",
                    match_score=float(p.get("match_score", 85.0)),
                    skills_matched=p.get("skills_matched") or [],
                    skills_gap=p.get("skills_gap") or [],
                )

            elif ev.event_type == EventType.OUTREACH_SENT:
                outreach = OutreachRef(
                    draft_subject=p.get("draft_subject") or p.get("subject") or "",
                    draft_body=p.get("draft_body") or p.get("body") or "",
                    personalization_score=int(p.get("personalization_score", 3)),
                    word_count=int(p.get("word_count", 80)),
                    mode=p.get("mode"),
                    status=p.get("status", "sent"),
                    message_id=p.get("message_id") or p.get("send_id"),
                )

            elif ev.event_type == EventType.APPLICATION_SUBMITTED:
                auto_apply = AutoApplyRef(
                    submission_id=p.get("submission_id") or p.get("attempt_id") or "sub_1",
                    portal_url=p.get("portal_url") or url or "",
                    pdf_resume_path=p.get("pdf_resume_path") or p.get("pdf_artifact_path") or "",
                    cover_note=p.get("cover_note"),
                    fields_submitted=p.get("fields_submitted") or p.get("form_fields_filled") or {},
                    mode=p.get("mode", "dry_run"),
                    status=p.get("status", "submitted"),
                )

            elif ev.event_type == EventType.RESPONSE_CLASSIFIED:
                sentiment_signal = ConductorSentimentSignal(
                    macro_sentiment=p.get("macro_sentiment", "neutral"),
                    intent_label=p.get("intent_label", "inquiry"),
                    urgency_score=int(p.get("urgency_score", 1)),
                    confidence=float(p.get("confidence", 1.0)),
                    key_phrases=p.get("key_phrases") or [],
                    recommended_action=p.get("recommended_action", "review"),
                    raw_text=p.get("raw_text") or "",
                )

        if not jd_text or len(jd_text) < 20:
            jd_text = f"Job listing for {title} at {company} with requirements and technical stack details."

        posting = PostingRef(
            company=company,
            title=title,
            jd_text=jd_text,
            url=url,
            contact_email=contact_email,
            contact_name=contact_name,
            application_channel=channel,
        )

        # Normalize status to valid Conductor ApplicationStatus
        raw_status = raw_app.status.value if hasattr(raw_app.status, "value") else str(raw_app.status).lower()
        status_map = {
            "discovered": "discovered",
            "researched": "researched",
            "skipped_duplicate": "skipped_duplicate",
            "skipped_cooldown": "skipped_cooldown",
            "tailored": "tailored",
            "outreach_pending_review": "outreach_pending_review",
            "outreach_approved": "outreach_approved",
            "outreach_rejected": "outreach_rejected",
            "outreach_sent": "outreach_sent",
            "auto_apply_pending_review": "auto_apply_pending_review",
            "auto_applied": "auto_applied",
            "applied": "auto_applied",
            "drafted": "discovered",
            "responded": "responded",
            "interview": "interview_scheduled",
            "interview_scheduled": "interview_scheduled",
            "rejected": "closed",
            "closed": "closed",
            "offer": "closed",
            "withdrawn": "closed",
            "error": "error",
        }
        conductor_status = status_map.get(raw_status, "closed")

        return ConductorAppRecord(
            job_id=raw_app.application_id,
            source="memory_module",
            posting=posting,
            status=conductor_status,
            tailored_resume=tailored_resume,
            outreach=outreach,
            auto_apply=auto_apply,
            sentiment_signal=sentiment_signal,
            timestamps=timestamps,
        )

    # -------------------------------------------------------------------
    # Conductor MemoryStore Interface Implementation
    # -------------------------------------------------------------------

    def save_application(self, record: ConductorAppRecord) -> bool:
        """
        Persist or update an application record by emitting the appropriate canonical MemoryEvent.
        Guarantees zero silent drops (ADR-4 & ADR-8).
        """
        try:
            occurred_at = datetime.now(timezone.utc)
            app_id = record.job_id
            company = record.posting.company
            title = record.posting.title
            status = record.status.lower()

            # Always ensure base JOB_DISCOVERED event exists for this application_id
            existing_events = self._ledger.get_history(app_id)
            has_discovered = any(e.event_type == EventType.JOB_DISCOVERED for e in existing_events)

            if not has_discovered or status in ("discovered", "skipped_duplicate", "skipped_cooldown"):
                event_data = {
                    "application_id": app_id,
                    "job_id": app_id,
                    "company": company,
                    "role_title": title,
                    "role": title,
                    "domain": company.lower().replace(" ", "") + ".com",
                    "url": record.posting.url,
                    "apply_url": record.posting.url,
                    "jd_text": record.posting.jd_text,
                    "contact_email": record.posting.contact_email,
                    "contact_name": record.posting.contact_name,
                    "application_channel": record.posting.application_channel,
                    "occurred_at": occurred_at.isoformat(),
                    "raw_source_ref": f"disc_{app_id[:8]}",
                }
                event = from_harvester_event(event_data)
                self._ledger.record_event(event)

            # 2. Resume Tailored Event
            if record.tailored_resume:
                tr = record.tailored_resume
                event_data = {
                    "application_id": app_id,
                    "job_id": app_id,
                    "company": company,
                    "role_title": title,
                    "tailoring_run_id": tr.run_id,
                    "run_id": tr.run_id,
                    "diff_summary": tr.diff_summary,
                    "resume_diff_summary": tr.diff_summary,
                    "match_score": tr.match_score,
                    "skills_matched": tr.skills_matched,
                    "skills_gap": tr.skills_gap,
                    "tailored_content": tr.tailored_content,
                    "occurred_at": occurred_at.isoformat(),
                    "raw_source_ref": f"tailor_{tr.run_id}",
                }
                event = from_align_resume_event(event_data)
                self._ledger.record_event(event)

            # 3. Outreach Sent Event
            if record.outreach and status in ("outreach_sent", "sent", "completed"):
                o = record.outreach
                event_data = {
                    "application_id": app_id,
                    "job_id": app_id,
                    "company": company,
                    "role_title": title,
                    "domain": company.lower().replace(" ", "") + ".com",
                    "draft_subject": o.draft_subject,
                    "subject": o.draft_subject,
                    "draft_body": o.draft_body,
                    "body": o.draft_body,
                    "send_id": o.message_id or f"msg_{app_id[:8]}",
                    "email_id": o.message_id or f"msg_{app_id[:8]}",
                    "personalization_score": o.personalization_score,
                    "word_count": o.word_count,
                    "mode": o.mode,
                    "status": o.status,
                    "occurred_at": occurred_at.isoformat(),
                    "raw_source_ref": f"outreach_{app_id[:8]}",
                }
                event = from_overture_event(event_data)
                self._ledger.record_event(event)

            # 4. Application Submitted Event (PDF Auto-Apply)
            if record.auto_apply and status in ("auto_applied", "submitted", "completed"):
                aa = record.auto_apply
                event_data = {
                    "application_id": app_id,
                    "job_id": app_id,
                    "company": company,
                    "role_title": title,
                    "domain": company.lower().replace(" ", "") + ".com",
                    "submission_id": aa.submission_id,
                    "attempt_id": aa.submission_id,
                    "portal_url": aa.portal_url,
                    "pdf_artifact_path": aa.pdf_resume_path,
                    "pdf_resume_path": aa.pdf_resume_path,
                    "form_fields_filled": aa.fields_submitted,
                    "fields_submitted": aa.fields_submitted,
                    "cover_note": aa.cover_note,
                    "mode": aa.mode,
                    "status": aa.status,
                    "occurred_at": occurred_at.isoformat(),
                    "raw_source_ref": f"apply_{aa.submission_id}",
                }
                event = from_auto_apply_receipt(event_data)
                self._ledger.record_event(event)

            # 5. Inbound Sentiment Classification Event
            if record.sentiment_signal:
                sig = record.sentiment_signal
                event_data = {
                    "application_id": app_id,
                    "job_id": app_id,
                    "company": company,
                    "domain": company.lower().replace(" ", "") + ".com",
                    "macro_sentiment": sig.macro_sentiment,
                    "intent_label": sig.intent_label,
                    "urgency_score": sig.urgency_score,
                    "confidence": sig.confidence,
                    "key_phrases": sig.key_phrases,
                    "recommended_action": sig.recommended_action,
                    "raw_text": getattr(sig, "raw_response", None) or getattr(sig, "raw_text", ""),
                    "classified_at": occurred_at.isoformat(),
                    "response_id": f"resp_{app_id[:8]}",
                }
                event = from_classified_signal(event_data)
                self._ledger.record_event(event)

            return True

        except Exception as e:
            logger.error("[EventSourcedMemoryStore] Failed to save application %s: %s", record.job_id, e)
            return False

    def get_application(self, job_id: str) -> Optional[ConductorAppRecord]:
        """Retrieve an application record by its job_id / application_id."""
        raw = self._ledger.get_application(job_id)
        if not raw:
            # Fallback: check if job_id matches job_id in list
            apps = self._ledger.list_applications()
            for a in apps:
                if a.job_id == job_id or a.application_id == job_id:
                    return self._to_conductor_record(a)
            return None
        return self._to_conductor_record(raw)

    def find_latest_application_by_company(self, company: str) -> Optional[ConductorAppRecord]:
        """Retrieve the most recent application record for a given company name."""
        apps = self._ledger.list_applications()
        matching = [
            a for a in apps
            if a.company.strip().lower() == company.strip().lower()
        ]
        if not matching:
            return None
        matching.sort(key=lambda a: a.last_updated, reverse=True)
        return self._to_conductor_record(matching[0])

    def list_applications(
        self,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> List[ConductorAppRecord]:
        """List application records, optionally filtered by status."""
        target_status = None
        if status:
            try:
                target_status = StandaloneAppStatus(status.lower())
            except ValueError:
                target_status = None

        raw_list = self._ledger.list_applications(status=target_status)
        results = [self._to_conductor_record(r) for r in raw_list[:limit]]
        return results

    def is_duplicate_posting(
        self,
        link: Optional[str] = None,
        company: Optional[str] = None,
        title: Optional[str] = None,
    ) -> bool:
        """
        Check if a posting was already ingested or processed (EC-06 & Task 2.4).
        Matches on URL/link or normalized (company + title) combination.
        """
        events = self._ledger.db.get_all_events()
        norm_company = company.strip().lower() if company else None
        norm_title = title.strip().lower() if title else None

        for ev in events:
            p = ev.payload or {}
            ev_url = p.get("url") or p.get("apply_url") or p.get("link")
            if link and ev_url and ev_url.strip().lower() == link.strip().lower():
                return True

            ev_comp = (p.get("company") or "").strip().lower()
            ev_title = (p.get("role_title") or p.get("title") or p.get("role") or "").strip().lower()
            if norm_company and norm_title and ev_comp == norm_company and ev_title == norm_title:
                return True

        return False

    def is_company_in_cooldown(self, company: str, cooldown_days: int = 30) -> bool:
        """
        Check if outreach to this company was recently rejected or sent (EC-07 & Task 3.3).
        Checks 30-day domain cooldowns and recent rejection events.
        """
        domain = company.lower().replace(" ", "") + ".com"
        cd_info = self._ledger.check_domain_cooldown(domain)
        if cd_info.get("is_blocked"):
            return True

        # Check applications marked REJECTED directly
        apps = self._ledger.list_applications(status=StandaloneAppStatus.REJECTED)
        now = datetime.now(timezone.utc)
        for a in apps:
            if a.company.strip().lower() == company.strip().lower():
                last_up = a.last_updated
                if last_up.tzinfo is None:
                    last_up = last_up.replace(tzinfo=timezone.utc)
                delta_days = (now - last_up).total_seconds() / 86400.0
                if delta_days <= cooldown_days:
                    return True

        return False

    def record_inbound_response(
        self,
        target_id_or_company: str,
        signal: ConductorSentimentSignal,
    ) -> Optional[ConductorAppRecord]:
        """
        Ingest sentiment signal from inbound response, emit RESPONSE_CLASSIFIED event,
        and update application state.
        """
        app = self.get_application(target_id_or_company) or self.find_latest_application_by_company(target_id_or_company)
        app_id = app.job_id if app else target_id_or_company
        company = app.posting.company if app else target_id_or_company

        raw_txt = getattr(signal, "raw_response", None) or getattr(signal, "raw_text", "")
        event_data = {
            "application_id": app_id,
            "job_id": app_id,
            "company": company,
            "domain": company.lower().replace(" ", "") + ".com",
            "macro_sentiment": signal.macro_sentiment,
            "intent_label": signal.intent_label,
            "urgency_score": signal.urgency_score,
            "confidence": signal.confidence,
            "key_phrases": signal.key_phrases,
            "recommended_action": signal.recommended_action,
            "raw_text": raw_txt,
            "classified_at": datetime.now(timezone.utc).isoformat(),
            "response_id": f"resp_{app_id[:8]}",
        }
        event = from_classified_signal(event_data)
        self._ledger.record_event(event)

        return self.get_application(app_id)

    def save_candidate_profile(self, profile: ConductorCandidateProfile) -> bool:
        """Persist candidate profile."""
        self._cached_profiles[profile.candidate_id] = profile
        return True

    def get_candidate_profile(self, candidate_id: str = "sdn9300") -> Optional[ConductorCandidateProfile]:
        """Retrieve candidate profile."""
        return self._cached_profiles.get(candidate_id)
