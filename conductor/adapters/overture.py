"""
Overture Adapter.
Interfaces with Overture (cold-email-agent #3) for email generation and outbound dispatch.
Implements ADR-4, ADR-6, and EC-02.
"""

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from conductor.adapters.base import AgentAdapter, AgentResult
from conductor.config import config


class OvertureAdapter(AgentAdapter):
    """Adapter for wrapping Overture Cold Email Writer & Dispatcher."""

    def __init__(self, overture_dir: Optional[str] = None, dry_run: bool = True):
        self.overture_dir = Path(overture_dir or config.OVERTURE_DIR)
        self.dry_run = dry_run
        self._setup_path()

    def _setup_path(self) -> None:
        """Add cold-email-agent directory to sys.path to enable imports."""
        other_docs = self.overture_dir / "Other_Documents"
        if other_docs.exists() and str(other_docs) not in sys.path:
            sys.path.insert(0, str(other_docs))
        elif self.overture_dir.exists() and str(self.overture_dir) not in sys.path:
            sys.path.insert(0, str(self.overture_dir))

    @property
    def name(self) -> str:
        return "overture"

    def _build_contact_dict(self, state_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize state into contact dictionary expected by Overture."""
        app = state_dict.get("application", {})
        posting = app.get("posting", {}) if isinstance(app, dict) else getattr(app, "posting", {})

        if isinstance(posting, dict):
            company = posting.get("company", "Unknown Company")
            role = posting.get("title", "AI Engineer")
            contact_email = posting.get("contact_email") or f"recruiting@{company.lower().replace(' ', '')}.com"
            contact_name = posting.get("contact_name") or "Hiring Team"
            job_url = posting.get("url") or ""
        else:
            company = getattr(posting, "company", "Unknown Company")
            role = getattr(posting, "title", "AI Engineer")
            contact_email = getattr(posting, "contact_email", None) or f"recruiting@{company.lower().replace(' ', '')}.com"
            contact_name = getattr(posting, "contact_name", None) or "Hiring Team"
            job_url = getattr(posting, "url", None) or ""

        return {
            "company": company,
            "role": role,
            "recipient_email": contact_email,
            "recipient_name": contact_name,
            "job_url": job_url,
            "candidate_name": config.CANDIDATE_NAME,
            "candidate_background": "AI & Agentic Systems Engineer specializing in LangGraph, multi-agent orchestration, and backend systems",
            "portfolio_url": "https://github.com/sdn9300",
            "personalization_note": f"how {company} is scaling its AI engineering stack",
        }

    def draft_email(self, contact: Dict[str, Any], use_llm: bool = False) -> Dict[str, Any]:
        """Generate email draft without sending."""
        # Ensure mandatory candidate fields are set
        if "candidate_name" not in contact:
            contact["candidate_name"] = config.CANDIDATE_NAME
        if "candidate_background" not in contact:
            contact["candidate_background"] = "AI & Agentic Systems Engineer"
        if "personalization_note" not in contact:
            contact["personalization_note"] = f"{contact.get('company', 'this team')} is doing interesting work in AI"

        try:
            from email_generator import generate_email
            draft = generate_email(contact, use_llm=use_llm)
            return {
                "draft_subject": draft.subject,
                "draft_body": draft.body,
                "personalization_score": draft.personalization_score,
                "word_count": draft.word_count,
            }
        except Exception:
            # Fallback generator
            company = contact.get("company", "the team")
            role = contact.get("role", "the role")
            name = contact.get("recipient_name", "Hiring Team")
            candidate = contact.get("candidate_name", config.CANDIDATE_NAME)
            background = contact.get("candidate_background", "AI Engineer")

            subject = f"Application for {role} at {company} — {candidate}"
            body = (
                f"Hi {name},\n\n"
                f"I noticed the open {role} role at {company} and wanted to reach out directly. "
                f"I'm {candidate} — {background}.\n\n"
                f"I have attached my tailored resume for your review. Would love to discuss how my background aligns with {company}'s technical initiatives.\n\n"
                f"Best regards,\n"
                f"{candidate}"
            )
            return {
                "draft_subject": subject,
                "draft_body": body,
                "personalization_score": 2,
                "word_count": len(body.split()),
            }

    def invoke(self, state_dict: Dict[str, Any]) -> AgentResult:
        start_time = time.time()
        try:
            contact = self._build_contact_dict(state_dict)

            # Check if an existing draft was created during human gate or needs generation
            app = state_dict.get("application", {})
            existing_outreach = app.get("outreach", {}) if isinstance(app, dict) else getattr(app, "outreach", {})
            if isinstance(existing_outreach, dict) and existing_outreach.get("draft_subject"):
                draft_data = existing_outreach
            else:
                draft_data = self.draft_email(contact, use_llm=bool(config.GROQ_API_KEY))

            # Perform send action
            mode = "dry_run" if self.dry_run else "send"

            if self.dry_run:
                return AgentResult(
                    success=True,
                    output={
                        "draft_subject": draft_data.get("draft_subject"),
                        "draft_body": draft_data.get("draft_body"),
                        "personalization_score": draft_data.get("personalization_score", 2),
                        "word_count": draft_data.get("word_count", 80),
                        "mode": "dry_run",
                        "status": "dry_run",
                        "message_id": f"dry-run-msg-{int(time.time())}",
                        "sent_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    },
                    cost_estimate=0.0,
                    latency_ms=(time.time() - start_time) * 1000,
                )

            # Live Send via Overture modules
            try:
                from email_sender import send_email
                from config import load_config
                from email_generator import EmailDraft

                overture_cfg = load_config()
                overture_cfg.DRY_RUN = False

                draft_obj = EmailDraft(
                    subject=draft_data["draft_subject"],
                    body=draft_data["draft_body"],
                    personalization_score=draft_data.get("personalization_score", 2),
                    word_count=draft_data.get("word_count", 80),
                )

                send_res = send_email(contact, draft_obj, mode="send", config=overture_cfg)

                if send_res.status == "failed":
                    return AgentResult(
                        success=False,
                        error=send_res.error or "Overture email send failed.",
                        output={
                            **draft_data,
                            "mode": "send",
                            "status": "failed",
                            "error": send_res.error,
                        },
                        latency_ms=(time.time() - start_time) * 1000,
                    )

                return AgentResult(
                    success=True,
                    output={
                        **draft_data,
                        "mode": "send",
                        "status": send_res.status,
                        "message_id": send_res.message_id,
                        "sent_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    },
                    latency_ms=(time.time() - start_time) * 1000,
                )

            except Exception as live_err:
                return AgentResult(
                    success=False,
                    error=f"Failed to execute live send via Overture: {live_err}",
                    output={**draft_data, "mode": "send", "status": "failed"},
                    latency_ms=(time.time() - start_time) * 1000,
                )

        except Exception as e:
            return AgentResult(
                success=False,
                error=f"OvertureAdapter unexpected error: {str(e)}",
                latency_ms=(time.time() - start_time) * 1000,
            )

    def health_check(self) -> bool:
        return self.overture_dir.exists()
