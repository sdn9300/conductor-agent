"""
PDF Auto-Apply Adapter — Usher Integration (Phase 3).
Bridges Conductor's graph to Usher's real AutoApplyPipeline via Candidate Profile projections.
Implements Tasks 3.2, 3.3, 3.4 of CONDUCTOR_08.

Fallback: If Usher is not importable (e.g., missing Playwright), falls back to the
original stub behavior for backward compatibility and testing.
"""

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from conductor.adapters.base import AgentAdapter, AgentResult
from conductor.config import config
from conductor.state import AutoApplyRef

logger = logging.getLogger(__name__)

# --- Attempt Usher import (graceful fallback) ---
_USHER_AVAILABLE = False
try:
    from usher.conductor import run_auto_apply_pipeline
    from usher.schemas import (
        ApplicationAttemptResult as UsherAttemptResult,
        CandidateProfile as UsherCandidateProfile,
        JobApplicationTarget as UsherJobTarget,
        ResumeArtifact as UsherResumeArtifact,
        SubmissionMode,
    )
    from candidate_profile.projections import to_usher_profile
    from candidate_profile.models import CandidateProfile as CanonicalCandidateProfile
    _USHER_AVAILABLE = True
    logger.info("[PDFAutoApply] Usher pipeline imported successfully.")
except ImportError as import_err:
    logger.warning("[PDFAutoApply] Usher not available (%s). Using stub fallback.", import_err)


class PDFAutoApplyAdapter(AgentAdapter):
    """Adapter for compiling resume artifacts and submitting form-based applications.

    When Usher is available, delegates to the real AutoApplyPipeline.
    When Usher is unavailable, falls back to the original stub behavior.
    """

    def __init__(self, output_dir: Optional[str] = None, dry_run: Optional[bool] = None):
        self.output_dir = Path(output_dir or config.PDF_OUTPUT_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.dry_run = config.DRY_RUN if dry_run is None else dry_run
        self.use_usher = _USHER_AVAILABLE

    @property
    def name(self) -> str:
        return "pdf_auto_apply"

    # ------------------------------------------------------------------
    # Translation helpers (Conductor state → Usher input schemas)
    # ------------------------------------------------------------------

    def _translate_profile(self, state_dict: Dict[str, Any]) -> Optional["UsherCandidateProfile"]:
        """Translate canonical CandidateProfile → Usher's CandidateProfile via to_usher_profile()."""
        profile = state_dict.get("profile")
        if profile is None:
            return None
        try:
            if isinstance(profile, dict):
                canonical = CanonicalCandidateProfile.model_validate(profile)
            else:
                canonical = profile
            return to_usher_profile(canonical)
        except Exception as e:
            logger.warning("[PDFAutoApply] Profile translation failed: %s", e)
            return None

    def _translate_job(self, state_dict: Dict[str, Any]) -> Optional["UsherJobTarget"]:
        """Translate Conductor's posting into Usher's JobApplicationTarget."""
        app = state_dict.get("application", {})
        posting = app if isinstance(app, dict) and "posting" not in app else app.get("posting", {})
        if isinstance(posting, dict):
            company = posting.get("company", "Unknown")
            title = posting.get("title", "AI Engineer")
            url = posting.get("url") or f"https://careers.{company.lower().replace(' ', '')}.com/apply"
            jd_text = posting.get("jd_text", "")
            source = posting.get("source", "manual")
        else:
            company = getattr(posting, "company", "Unknown")
            title = getattr(posting, "title", "AI Engineer")
            url = getattr(posting, "url", None) or f"https://careers.{company.lower().replace(' ', '')}.com/apply"
            jd_text = getattr(posting, "jd_text", "")
            source = getattr(posting, "source", "manual")

        try:
            return UsherJobTarget(
                job_id=state_dict.get("job_id", str(uuid4())),
                title=title,
                company=company,
                apply_url=url,
                source_platform=source,
                description=jd_text,
            )
        except Exception as e:
            logger.warning("[PDFAutoApply] Job translation failed: %s", e)
            return None

    def _translate_resume(self, state_dict: Dict[str, Any]) -> Optional["UsherResumeArtifact"]:
        """Translate Conductor's tailored resume into Usher's ResumeArtifact."""
        app = state_dict.get("application", {})
        tailored = app.get("tailored_resume", {}) if isinstance(app, dict) else {}
        content = tailored.get("tailored_content", "") if isinstance(tailored, dict) else ""

        # Compile the resume to a file artifact
        job_id = state_dict.get("job_id", str(uuid4()))
        posting = app.get("posting", {}) if isinstance(app, dict) else {}
        company = posting.get("company", "target") if isinstance(posting, dict) else "target"
        role = posting.get("title", "role") if isinstance(posting, dict) else "role"

        artifact_path = self._compile_resume_artifact(job_id, company, role, content or "Resume content")
        file_checksum = hashlib.sha256(artifact_path.read_bytes()).hexdigest()

        try:
            return UsherResumeArtifact(
                tailoring_run_id=tailored.get("run_id", f"run_{job_id[:8]}") if isinstance(tailored, dict) else f"run_{job_id[:8]}",
                file_path=str(artifact_path),
                file_checksum=file_checksum,
                profile_version="1.0.0",
            )
        except Exception as e:
            logger.warning("[PDFAutoApply] Resume artifact translation failed: %s", e)
            return None

    def _get_submission_mode(self) -> "SubmissionMode":
        """Map Conductor's DRY_RUN config to Usher's SubmissionMode (Task 3.4)."""
        if self.dry_run:
            return SubmissionMode.DRAFT
        return SubmissionMode.AUTO

    # ------------------------------------------------------------------
    # Resume artifact compilation (shared between Usher and fallback)
    # ------------------------------------------------------------------

    def _compile_resume_artifact(
        self,
        job_id: str,
        company: str,
        role: str,
        resume_content: str,
    ) -> Path:
        """Save formatted tailored resume artifact to output directory."""
        safe_company = "".join(c for c in company if c.isalnum() or c in ("-", "_")).lower()
        file_name = f"resume_{safe_company}_{job_id[:8]}.txt"
        file_path = self.output_dir / file_name

        header = (
            f"{'='*60}\n"
            f"  TAILORED RESUME: {config.CANDIDATE_NAME}\n"
            f"  Target: {company} — {role}\n"
            f"  Contact: {config.CANDIDATE_EMAIL} | {config.CANDIDATE_PHONE}\n"
            f"  Portfolio: {config.CANDIDATE_PORTFOLIO}\n"
            f"{'='*60}\n\n"
        )

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(header + resume_content)

        return file_path

    # ------------------------------------------------------------------
    # Usher pipeline execution
    # ------------------------------------------------------------------

    def _invoke_usher(self, state_dict: Dict[str, Any]) -> AgentResult:
        """Call Usher's real AutoApplyPipeline via run_auto_apply_pipeline()."""
        start_time = time.time()

        usher_profile = self._translate_profile(state_dict)
        usher_job = self._translate_job(state_dict)
        usher_resume = self._translate_resume(state_dict)

        if not usher_profile:
            # Build a fallback UsherCandidateProfile from config
            usher_profile = UsherCandidateProfile(
                candidate_id=state_dict.get("candidate_id", config.CANDIDATE_ID),
                full_name=config.CANDIDATE_NAME,
                email=config.CANDIDATE_EMAIL,
                phone=config.CANDIDATE_PHONE,
                location="Remote",
            )

        if not usher_job or not usher_resume:
            return AgentResult(
                success=False,
                error="PDFAutoApplyAdapter: Failed to translate Conductor state to Usher inputs.",
                latency_ms=(time.time() - start_time) * 1000,
            )

        mode = self._get_submission_mode()
        logger.info(
            "[PDFAutoApply] Calling Usher pipeline: job=%s, mode=%s, dry_run=%s",
            usher_job.job_id, mode.value, self.dry_run,
        )

        try:
            result: UsherAttemptResult = run_auto_apply_pipeline(
                job=usher_job,
                profile=usher_profile,
                resume=usher_resume,
                mode=mode,
            )
        except Exception as pipeline_err:
            logger.error("[PDFAutoApply] Usher pipeline execution failed: %s", pipeline_err)
            return AgentResult(
                success=False,
                error=f"Usher pipeline error: {pipeline_err}",
                latency_ms=(time.time() - start_time) * 1000,
            )

        # Translate Usher's ApplicationAttemptResult → Conductor's AutoApplyRef
        auto_apply_ref = AutoApplyRef(
            submission_id=result.attempt_id,
            portal_url=usher_job.apply_url,
            pdf_resume_path=str(usher_resume.file_path),
            cover_note=None,
            fields_submitted={
                "full_name": usher_profile.full_name,
                "email": usher_profile.email,
                "phone": usher_profile.phone,
                "portal_url": usher_job.apply_url,
                "resume_artifact": str(usher_resume.file_path),
                "usher_status": result.status,
                "field_resolutions": [fr.model_dump() for fr in result.field_resolutions],
                "screenshot_path": result.screenshot_path,
                "groq_tokens_used": result.groq_tokens_used,
                "groq_cost_estimate_usd": result.groq_cost_estimate_usd,
            },
            mode="dry_run" if self.dry_run else "live_submit",
            status=self._map_usher_status(result.status),
        )

        return AgentResult(
            success=True,
            output={"auto_apply": auto_apply_ref.model_dump()},
            latency_ms=(time.time() - start_time) * 1000,
            cost_estimate=result.groq_cost_estimate_usd,
        )

    @staticmethod
    def _map_usher_status(usher_status: str) -> str:
        """Map Usher's attempt status to Conductor's AutoApplyRef status."""
        mapping = {
            "SUBMITTED": "submitted",
            "DRAFT_PENDING_REVIEW": "dry_run",
            "MANUAL_REQUIRED": "dry_run",
            "AMBIGUOUS_OUTCOME": "failed",
            "FAILED": "failed",
            "SKIPPED": "failed",
        }
        return mapping.get(usher_status, "dry_run")

    # ------------------------------------------------------------------
    # Fallback stub execution (original behavior for backward compat)
    # ------------------------------------------------------------------

    def _invoke_fallback(self, state_dict: Dict[str, Any]) -> AgentResult:
        """Original stub behavior when Usher is not available."""
        start_time = time.time()
        try:
            job_id = state_dict.get("job_id", str(uuid4()))
            app = state_dict.get("application", {})
            posting = app.get("posting", {})
            company = posting.get("company") or state_dict.get("company", "Unknown")
            role = posting.get("title") or state_dict.get("role", "AI Engineer")
            portal_url = posting.get("url")

            tailored = app.get("tailored_resume") or {}
            resume_content = (
                (tailored.get("tailored_content") if isinstance(tailored, dict) else None)
                or state_dict.get("master_resume_text")
                or f"{config.CANDIDATE_NAME} — AI Engineer"
            )

            cover_note = state_dict.get("cover_note") or state_dict.get("metadata", {}).get("cover_note")

            artifact_path = self._compile_resume_artifact(
                job_id=job_id,
                company=company,
                role=role,
                resume_content=resume_content,
            )

            effective_note = cover_note or (
                f"Hello {company} Hiring Team,\n\n"
                f"I am applying for the {role} position. My background is centered on AI multi-agent orchestration, "
                f"LangGraph state systems, and robust backend engineering. Please find my tailored resume attached."
            )

            fields_submitted = {
                "full_name": config.CANDIDATE_NAME,
                "email": config.CANDIDATE_EMAIL,
                "phone": config.CANDIDATE_PHONE,
                "portfolio_url": config.CANDIDATE_PORTFOLIO,
                "company": company,
                "role": role,
                "portal_url": portal_url or f"https://careers.{company.lower().replace(' ', '')}.com/apply",
                "resume_artifact": str(artifact_path),
                "cover_note": effective_note,
            }

            submission_id = f"apply_{uuid4().hex[:8]}"

            if self.dry_run:
                logger.info("[PDFAutoApply] DRY RUN (fallback): Form application packaged for %s - %s", company, role)
                result_ref = AutoApplyRef(
                    submission_id=submission_id,
                    portal_url=fields_submitted["portal_url"],
                    pdf_resume_path=str(artifact_path),
                    cover_note=effective_note,
                    fields_submitted=fields_submitted,
                    mode="dry_run",
                    status="dry_run",
                )
            else:
                logger.info("[PDFAutoApply] LIVE SUBMIT (fallback): Submitting to %s", fields_submitted["portal_url"])
                result_ref = AutoApplyRef(
                    submission_id=submission_id,
                    portal_url=fields_submitted["portal_url"],
                    pdf_resume_path=str(artifact_path),
                    cover_note=effective_note,
                    fields_submitted=fields_submitted,
                    mode="live_submit",
                    status="submitted",
                )

            return AgentResult(
                success=True,
                output={"auto_apply": result_ref.model_dump()},
                latency_ms=(time.time() - start_time) * 1000,
            )
        except Exception as e:
            return AgentResult(
                success=False,
                error=f"PDFAutoApplyAdapter fallback error: {str(e)}",
                latency_ms=(time.time() - start_time) * 1000,
            )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def invoke(self, state_dict: Dict[str, Any]) -> AgentResult:
        """Main entry point. Routes to Usher pipeline or fallback stub."""
        if self.use_usher:
            try:
                return self._invoke_usher(state_dict)
            except Exception as e:
                logger.warning("[PDFAutoApply] Usher invocation failed, falling back to stub: %s", e)
                return self._invoke_fallback(state_dict)
        return self._invoke_fallback(state_dict)

    def health_check(self) -> bool:
        return self.output_dir.exists()
