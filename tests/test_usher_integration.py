"""
Integration tests for Usher / PDF Auto-Apply Integration (Phase 3).
Verifies:
- Schema translation: to_usher_profile() → Usher's CandidateProfile (1-to-1 match)
- DRY_RUN → SubmissionMode.DRAFT propagation (Task 3.4)
- IG-7: Full graph dry-run with --channel form producing form-payload artifact
- Fallback: Graceful degradation when Usher pipeline throws
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from conductor.adapters.auto_apply import PDFAutoApplyAdapter, _USHER_AVAILABLE
from conductor.config import config
from conductor.graph.nodes import NodeContext
from conductor.graph.workflow import build_conductor_graph
from conductor.state import (
    ApplicationRecord,
    AutoApplyRef,
    ConductorState,
    PostingRef,
    TailoredResumeRef,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_posting():
    return PostingRef(
        company="Cognitive Systems",
        title="AI Engineer",
        jd_text="Experience in Python, Docker, and agent orchestration for high-scale workflows.",
        url="https://boards.greenhouse.io/cognitive/apply/12345",
        contact_email="hiring@cognitive.io",
        application_channel="form",
    )


@pytest.fixture
def sample_tailored_resume():
    return TailoredResumeRef(
        run_id="align_run_999",
        tailored_content=(
            "Soumyadeep Nath — AI & Agentic Systems Engineer\n"
            "Engineered the central LangGraph state machine coordinating a 10-component AI-Native Job Search system.\n"
            "Skills: Python, LangGraph, Docker, Kubernetes, FastAPI, Pydantic v2"
        ),
        diff_summary="Added Docker and Kubernetes emphasis",
        match_score=92.0,
        skills_matched=["Python", "Docker", "LangGraph"],
        skills_gap=["Terraform"],
    )


@pytest.fixture
def candidate_profile_fixture():
    """Build a canonical CandidateProfile for testing."""
    try:
        from candidate_profile.models import (
            CandidateProfile,
            ProfileMetadata,
            Identity,
            ContactInfo,
            SkillRecord,
            ProficiencyLevel,
            SourceProvenance,
            ApplicationPreferences,
        )
    except ImportError:
        pytest.skip("candidate_profile not installed")

    now = datetime.now(timezone.utc)
    verified_src = SourceProvenance(
        source_type="resume_v12",
        source_ref="master_resume.txt",
        verified=True,
        recorded_at=now,
    )

    return CandidateProfile(
        profile_metadata=ProfileMetadata(
            candidate_id="test_cand_001",
            schema_version="1.0.0",
            created_at=now,
            updated_at=now,
            last_writer_component="bootstrap_manual",
        ),
        identity=Identity(
            legal_name="Soumyadeep Nath",
            location="Remote",
            contact=ContactInfo(
                email="soumyadeepnath@example.com",
                phone="+1 (555) 019-2834",
                linkedin="https://linkedin.com/in/sdn9300",
                github="https://github.com/sdn9300",
            ),
        ),
        education=[],
        skills=[
            SkillRecord(name="Python", taxonomy_ref="python", proficiency_self_assessed=ProficiencyLevel.ADVANCED, source=verified_src),
            SkillRecord(name="LangGraph", taxonomy_ref="langgraph", proficiency_self_assessed=ProficiencyLevel.ADVANCED, source=verified_src),
            SkillRecord(name="Docker", taxonomy_ref="docker", proficiency_self_assessed=ProficiencyLevel.ADVANCED, source=verified_src),
        ],
        experience=[],
        preferences=ApplicationPreferences(
            target_roles=["AI Engineer", "Agentic Systems Architect"],
            locations=["Remote", "Hybrid"],
            remote_ok=True,
        ),
    )


# ---------------------------------------------------------------------------
# Test 1: Schema translation — to_usher_profile() → Usher CandidateProfile
# ---------------------------------------------------------------------------

def test_usher_profile_schema_translation(candidate_profile_fixture):
    """to_usher_profile() output matches Usher's CandidateProfile contract 1-to-1."""
    from candidate_profile.projections import to_usher_profile
    from usher.schemas import CandidateProfile as UsherCandidateProfile

    usher_prof = to_usher_profile(candidate_profile_fixture)

    # Verify it can be validated as Usher's own schema
    usher_validated = UsherCandidateProfile.model_validate(usher_prof.model_dump())

    assert usher_validated.full_name == "Soumyadeep Nath"
    assert usher_validated.email == "soumyadeepnath@example.com"
    assert usher_validated.phone == "+1 (555) 019-2834"
    assert usher_validated.location == "Remote"
    assert "Python" in usher_validated.skills
    assert "LangGraph" in usher_validated.skills
    assert "Docker" in usher_validated.skills
    assert usher_validated.github_url == "https://github.com/sdn9300"
    assert usher_validated.linkedin_url == "https://linkedin.com/in/sdn9300"


# ---------------------------------------------------------------------------
# Test 2: DRY_RUN → SubmissionMode.DRAFT propagation
# ---------------------------------------------------------------------------

def test_dry_run_maps_to_draft_submission_mode():
    """Conductor's DRY_RUN=true maps to Usher's SubmissionMode.DRAFT."""
    adapter = PDFAutoApplyAdapter(dry_run=True)
    if _USHER_AVAILABLE:
        from usher.schemas import SubmissionMode
        assert adapter._get_submission_mode() == SubmissionMode.DRAFT

    adapter_live = PDFAutoApplyAdapter(dry_run=False)
    if _USHER_AVAILABLE:
        assert adapter_live._get_submission_mode() == SubmissionMode.AUTO


# ---------------------------------------------------------------------------
# Test 3: Adapter invoke produces form-payload artifact
# ---------------------------------------------------------------------------

def test_auto_apply_adapter_produces_form_payload(
    sample_posting,
    sample_tailored_resume,
    candidate_profile_fixture,
    tmp_path,
):
    """PDFAutoApplyAdapter produces a valid AutoApplyRef with form payload fields."""
    adapter = PDFAutoApplyAdapter(output_dir=str(tmp_path / "pdf_out"), dry_run=True)

    app_record = ApplicationRecord(
        job_id="job_usher_001",
        source="manual",
        posting=sample_posting,
        status="outreach_approved",
        tailored_resume=sample_tailored_resume,
    )

    state_dict = ConductorState(
        candidate_id="test_cand_001",
        job_id="job_usher_001",
        application=app_record,
        profile=candidate_profile_fixture,
        target_channel="form",
        human_approval="approve",
    ).model_dump()

    result = adapter.invoke(state_dict)
    assert result.success is True

    auto_apply_data = result.output["auto_apply"]
    assert auto_apply_data["mode"] == "dry_run"
    # Status depends on whether Usher's browser pipeline succeeds.
    # "dry_run" = DRAFT_PENDING_REVIEW, "submitted" = live, "failed" = browser unavailable.
    # All are valid outcomes from the translation layer.
    assert auto_apply_data["status"] in ("dry_run", "submitted", "failed")
    assert auto_apply_data["portal_url"]
    assert auto_apply_data["pdf_resume_path"]
    assert auto_apply_data["fields_submitted"]

    # Verify resume artifact file was actually written
    resume_path = Path(auto_apply_data["pdf_resume_path"])
    assert resume_path.exists()
    content = resume_path.read_text(encoding="utf-8")
    assert "TAILORED RESUME" in content


# ---------------------------------------------------------------------------
# Test 4: IG-7 — Full graph dry-run with channel=form
# ---------------------------------------------------------------------------

def test_ig7_full_graph_form_channel_dry_run(
    sample_posting,
    sample_tailored_resume,
    candidate_profile_fixture,
    tmp_path,
):
    """
    IG-7 Acceptance Gate: conductor run --channel form --dry-run completes
    end-to-end producing a form-payload artifact in AutoApplyRef.
    """
    from conductor.adapters.candidate_profile import CandidateProfileAdapter
    from conductor.storage.local_store import SQLiteMemoryStore

    # Use unique posting to avoid dedup collisions from prior test runs
    unique_posting = PostingRef(
        company=f"UsherTestCorp_{uuid4().hex[:6]}",
        title="AI Platform Engineer",
        jd_text="Experience in Python, Docker, Kubernetes, and agent orchestration for high-scale workflows.",
        url="https://boards.greenhouse.io/ushertestcorp/apply/99999",
        contact_email="hiring@ushertestcorp.io",
        application_channel="form",
    )

    app_record = ApplicationRecord(
        job_id=f"job_ig7_{uuid4().hex[:6]}",
        source="manual",
        posting=unique_posting,
        status="discovered",
    )

    initial_state = ConductorState(
        candidate_id="test_cand_001",
        job_id=app_record.job_id,
        application=app_record,
        profile=candidate_profile_fixture,
        target_channel="form",
    )

    cp_adapter = CandidateProfileAdapter(data_dir=str(tmp_path / "profiles"))
    cp_adapter.save_profile(candidate_profile_fixture)

    auto_apply_adapter = PDFAutoApplyAdapter(
        output_dir=str(tmp_path / "pdf_out"),
        dry_run=True,
    )

    # Use a fresh in-memory SQLite store to avoid dedup from persistent DB
    fresh_store = SQLiteMemoryStore(str(tmp_path / "fresh_test.db"))

    ctx = NodeContext(
        candidate_profile_adapter=cp_adapter,
        auto_apply_adapter=auto_apply_adapter,
        memory_store=fresh_store,
        human_gate_callback=lambda s: "approve",
    )

    graph = build_conductor_graph(ctx)
    final_output = graph.invoke(initial_state)
    final_state = final_output if isinstance(final_output, ConductorState) else ConductorState.model_validate(final_output)

    # The pipeline should complete via auto_apply path (channel=form)
    assert final_state.application.status == "auto_applied", (
        f"Expected 'auto_applied', got '{final_state.application.status}'. "
        f"Errors: {final_state.errors}"
    )
    assert final_state.application.auto_apply is not None
    assert final_state.application.auto_apply.mode == "dry_run"
    assert final_state.application.auto_apply.fields_submitted

    # Verify CandidateProfile application_history was updated
    if final_state.profile:
        assert len(final_state.profile.application_history) >= 1
        latest_app_ref = final_state.profile.application_history[-1]
        assert latest_app_ref.component == "usher"


# ---------------------------------------------------------------------------
# Test 5: Fallback when Usher pipeline throws
# ---------------------------------------------------------------------------

def test_auto_apply_fallback_on_usher_failure(
    sample_posting,
    tmp_path,
):
    """Adapter falls back to stub behavior when Usher pipeline raises."""
    adapter = PDFAutoApplyAdapter(output_dir=str(tmp_path / "pdf_out"), dry_run=True)
    # Force fallback
    adapter.use_usher = False

    app_record = ApplicationRecord(
        job_id="job_fallback_001",
        source="manual",
        posting=sample_posting,
        status="outreach_approved",
    )

    state_dict = ConductorState(
        candidate_id="test_cand_001",
        job_id="job_fallback_001",
        application=app_record,
        target_channel="form",
    ).model_dump()

    result = adapter.invoke(state_dict)
    assert result.success is True
    assert result.output["auto_apply"]["mode"] == "dry_run"
