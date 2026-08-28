"""
Candidate Profile Bridge for Conductor Agent.
Connects Conductor Orchestrator (#6) with Component #10 (Candidate Profile JSON).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from candidate_profile import (
    ApplicationView,
    CandidateProfile,
    CandidateProfilePatch,
    CandidateProfileStore,
    GleanerQuery,
    OutreachContext,
    ResumeProfile,
    UsherCandidateProfile,
    merge_candidate_profile,
    to_application_view,
    to_gleaner_query,
    to_outreach_context,
    to_resume_profile,
    to_usher_profile,
)


class CandidateProfileBridge:
    """Orchestration bridge interfacing Conductor Agent with the canonical Candidate Profile store."""

    def __init__(self, store: Optional[CandidateProfileStore] = None) -> None:
        self.store = store or CandidateProfileStore(base_dir="./data/candidate_profile")

    def load_profile(self, candidate_id: str) -> Optional[CandidateProfile]:
        """Load canonical CandidateProfile from storage."""
        return self.store.get(candidate_id)

    def save_profile(self, profile: CandidateProfile) -> None:
        """Atomically persist canonical CandidateProfile to storage."""
        self.store.put(profile)

    def apply_patch(
        self,
        current: CandidateProfile,
        writer_component: str,
        section: str,
        value: Any,
        persist: bool = True,
    ) -> CandidateProfile:
        """Apply an ownership-validated patch to the profile state."""
        patch = CandidateProfilePatch(
            writer_component=writer_component,
            section=section,
            value=value,
        )
        updated = merge_candidate_profile(current, patch)
        if persist:
            self.save_profile(updated)
        return updated

    # Projection helpers for downstream nodes
    def project_for_align_resume(self, profile: CandidateProfile) -> ResumeProfile:
        """Project for AlignResume (#2)."""
        return to_resume_profile(profile)

    def project_for_gleaner(self, profile: CandidateProfile) -> GleanerQuery:
        """Project for Gleaner (#1)."""
        return to_gleaner_query(profile)

    def project_for_overture(self, profile: CandidateProfile) -> OutreachContext:
        """Project for Overture (#3)."""
        return to_outreach_context(profile)

    def project_for_usher(self, profile: CandidateProfile) -> ApplicationView:
        """Project for Usher (#7)."""
        return to_application_view(profile)

    def project_for_usher_profile(self, profile: CandidateProfile) -> UsherCandidateProfile:
        """Project for Usher internal schema match."""
        return to_usher_profile(profile)
