"""
Candidate Profile Adapter for Conductor Agent (#6).
Bridges Conductor to the canonical Candidate Profile JSON data layer (#10) and FastMCP server.
Provides store access, projection functions, section patch reducer, and skill provenance verification.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from candidate_profile.models import CandidateProfile, ProfileMetadata
from candidate_profile.storage import CandidateProfileStore
from candidate_profile.projections import (
    ResumeProfile,
    GleanerQuery,
    OutreachContext,
    ApplicationView,
    UsherCandidateProfile,
    ResearchScope,
    to_resume_profile,
    to_gleaner_query,
    to_outreach_context,
    to_application_view,
    to_usher_profile,
    to_research_scope,
)
from candidate_profile.concurrency import (
    CandidateProfilePatch,
    merge_candidate_profile,
)
from candidate_profile.server import check_skill_provenance

logger = logging.getLogger("conductor.adapters.candidate_profile")


class CandidateProfileAdapter:
    """Adapter wrapping Candidate Profile (#10) data store, projections, and anti-fabrication hooks."""

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = data_dir or str(Path(__file__).resolve().parent.parent.parent / "Candidate Profile" / "data" / "candidate_profile")
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        self.store = CandidateProfileStore(base_dir=self.data_dir)

    def get_profile(self, candidate_id: str = "sdn9300") -> Optional[CandidateProfile]:
        """Fetch candidate profile by ID, falling back to real profile fixture if uninitialized."""
        profile = self.store.get(candidate_id)
        if not profile:
            # Fallback: check real candidate fixture
            fixture_path = Path(__file__).resolve().parent.parent.parent / "Candidate Profile" / "fixtures" / "real_candidate_profile.json"
            if fixture_path.exists():
                try:
                    profile = CandidateProfile.model_validate_json(fixture_path.read_text(encoding="utf-8"))
                    profile.profile_metadata.candidate_id = candidate_id
                    profile.profile_metadata.last_writer_component = "conductor_init"
                    self.store.put(profile)
                except Exception as e:
                    logger.warning("[CandidateProfileAdapter] Error loading default fixture: %s", e)
        return profile

    def save_profile(self, profile: CandidateProfile, writer_component: str = "conductor") -> CandidateProfile:
        """Save full candidate profile."""
        from datetime import datetime, timezone
        profile.profile_metadata.last_writer_component = writer_component
        profile.profile_metadata.updated_at = datetime.now(timezone.utc)
        self.store.put(profile)
        return profile

    def apply_patch(
        self,
        base_profile: CandidateProfile,
        section: str,
        patch_payload: Union[Dict[str, Any], List[Any]],
        writer_component: str,
    ) -> CandidateProfile:
        """
        Applies a localized section patch via the merge_candidate_profile reducer (ADR-3 & ADR-7).
        """
        patch = CandidateProfilePatch(
            section=section,
            writer_component=writer_component,
            value=patch_payload,
        )
        updated_profile = merge_candidate_profile(base_profile, patch)
        self.store.put(updated_profile)
        return updated_profile

    # -------------------------------------------------------------------
    # Projections
    # -------------------------------------------------------------------

    def get_resume_profile(self, profile: CandidateProfile) -> ResumeProfile:
        """Project onto AlignResume tailoring schema (#2)."""
        return to_resume_profile(profile)

    def get_gleaner_query(self, profile: CandidateProfile) -> GleanerQuery:
        """Project onto Gleaner/Gleaner discovery query (#1)."""
        return to_gleaner_query(profile)

    def get_outreach_context(self, profile: CandidateProfile) -> OutreachContext:
        """Project onto Overture cold outreach context (#3)."""
        return to_outreach_context(profile)

    def get_application_view(self, profile: CandidateProfile) -> ApplicationView:
        """Project onto portal application view (#7)."""
        return to_application_view(profile)

    def get_usher_profile(self, profile: CandidateProfile) -> UsherCandidateProfile:
        """Project onto Usher schema (#7)."""
        return to_usher_profile(profile)

    def get_research_scope(self, profile: CandidateProfile) -> ResearchScope:
        """Project onto Research Agent context (#4)."""
        return to_research_scope(profile)

    # -------------------------------------------------------------------
    # Anti-Fabrication Hook
    # -------------------------------------------------------------------

    def verify_skill_provenance(self, candidate_id: str, skill_name: str) -> Dict[str, Any]:
        """
        Verify skill provenance to block LLM hallucinations during resume tailoring.
        Returns {'verified': bool, 'skill_name': str, 'provenance': ...}
        """
        try:
            return check_skill_provenance(candidate_id=candidate_id, skill_name=skill_name)
        except Exception as e:
            logger.warning("[CandidateProfileAdapter] check_skill_provenance lookup error: %s", e)
            # Fallback to local profile check
            profile = self.get_profile(candidate_id)
            if profile:
                norm_target = skill_name.strip().lower()
                for s in profile.skills:
                    if s.name.strip().lower() == norm_target:
                        return {
                            "candidate_id": candidate_id,
                            "skill_name": s.name,
                            "found": True,
                            "verified": s.source.verified,
                            "source_type": s.source.source_type,
                            "source_ref": s.source.source_ref,
                            "evidence_count": len(s.evidence_refs),
                        }
            return {
                "candidate_id": candidate_id,
                "skill_name": skill_name,
                "found": False,
                "verified": False,
                "source_type": "unrecorded",
                "source_ref": None,
                "evidence_count": 0,
            }
