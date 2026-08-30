"""
Full Integration Test — CONDUCTOR_08 Phase 4, Task 4.1.
Definition of Done: A single `--dry-run` exercises real (not stubbed) Memory Module,
Candidate Profile, and Usher integrations end-to-end.

This test covers the complete pipeline:
  discover → research → tailor (with provenance check) → approve →
  route (form channel) → auto_apply (real Usher) → persist →
  all three stores updated (Memory Module event ledger, Candidate Profile, SQLite)
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from conductor.adapters.auto_apply import PDFAutoApplyAdapter
from conductor.adapters.candidate_profile import CandidateProfileAdapter
from conductor.config import config
from conductor.graph.nodes import NodeContext
from conductor.graph.workflow import build_conductor_graph
from conductor.state import (
    ApplicationRecord,
    ConductorState,
    PostingRef,
)
from conductor.storage.local_store import SQLiteMemoryStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def canonical_candidate_profile():
    """Build a full canonical CandidateProfile (#10) with verified skills."""
    from candidate_profile.models import (
        CandidateProfile,
        ProfileMetadata,
        Identity,
        ContactInfo,
        SkillRecord,
        ProficiencyLevel,
        SourceProvenance,
        ApplicationPreferences,
        EducationRecord,
        ExperienceRecord,
    )

    now = datetime.now(timezone.utc)
    verified_src = SourceProvenance(
        source_type="resume_v12",
        source_ref="master_resume.txt",
        verified=True,
        recorded_at=now,
    )

    return CandidateProfile(
        profile_metadata=ProfileMetadata(
            candidate_id="sdn9300",
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
                portfolio="https://sdn9300.dev",
            ),
        ),
        education=[
            EducationRecord(
                institution="National Institute of Technology",
                program="B.Tech Computer Science",
                status="completed",
                start_date="2018-08",
                end_date="2022-06",
            ),
        ],
        skills=[
            SkillRecord(name="Python", taxonomy_ref="python", proficiency_self_assessed=ProficiencyLevel.ADVANCED, source=verified_src),
            SkillRecord(name="LangGraph", taxonomy_ref="langgraph", proficiency_self_assessed=ProficiencyLevel.ADVANCED, source=verified_src),
            SkillRecord(name="Docker", taxonomy_ref="docker", proficiency_self_assessed=ProficiencyLevel.ADVANCED, source=verified_src),
            SkillRecord(name="FastAPI", taxonomy_ref="fastapi", proficiency_self_assessed=ProficiencyLevel.ADVANCED, source=verified_src),
            SkillRecord(name="Pydantic", taxonomy_ref="pydantic", proficiency_self_assessed=ProficiencyLevel.ADVANCED, source=verified_src),
        ],
        experience=[
            ExperienceRecord(
                title="AI Systems Engineer",
                kind="employment",
                bullets=[
                    "Engineered the central LangGraph state machine coordinating a 10-component AI-Native Job Agent system",
                    "Designed event-sourced memory ledger with deterministic idempotency and anti-fabrication provenance gates",
                ],
                stack=["Python", "LangGraph", "Pydantic", "Docker"],
                source=verified_src,
            ),
        ],
        preferences=ApplicationPreferences(
            target_roles=["AI Engineer", "Agentic Systems Architect"],
            locations=["Remote", "Hybrid"],
            remote_ok=True,
            target_industries=["AI/ML", "Developer Tools"],
        ),
    )


@pytest.fixture
def fresh_environment(tmp_path):
    """Create a completely fresh, isolated test environment."""
    return {
        "db_path": str(tmp_path / "full_integration_test.db"),
        "profiles_dir": str(tmp_path / "profiles"),
        "pdf_output_dir": str(tmp_path / "pdf_resumes"),
    }


# ---------------------------------------------------------------------------
# Test: Full End-to-End Dry-Run (Definition of Done)
# ---------------------------------------------------------------------------

def test_definition_of_done_single_dry_run_all_three_subsystems(
    canonical_candidate_profile,
    fresh_environment,
):
    """
    CONDUCTOR_08 Definition of Done:
    A single `conductor run --dry-run` exercises real (not stubbed) Memory Module,
    Candidate Profile, and Usher integrations end-to-end, with all stores updated.

    Pipeline: discover → research → tailor → human_gate → auto_apply → persist
    Subsystems: Memory Module event ledger, Candidate Profile #10, Usher auto-apply
    """
    unique_id = uuid4().hex[:6]

    # --- 1. Prepare posting (form channel, triggers auto_apply path) ---
    posting = PostingRef(
        company=f"FullIntTestCorp_{unique_id}",
        title="Staff AI Platform Engineer",
        jd_text=(
            "We are hiring a Staff AI Platform Engineer with deep experience in Python, "
            "LangGraph state machine orchestration, Docker containerization, and distributed "
            "agentic systems. Must have production experience with Pydantic v2 data models "
            "and event-sourced architectures."
        ),
        url=f"https://boards.greenhouse.io/fullinttest_{unique_id}/jobs/99999",
        contact_email=f"hiring@fullinttest_{unique_id}.io",
        application_channel="form",
    )

    app_record = ApplicationRecord(
        job_id=f"job_full_int_{unique_id}",
        source="manual",
        posting=posting,
        status="discovered",
    )

    initial_state = ConductorState(
        candidate_id="sdn9300",
        job_id=app_record.job_id,
        application=app_record,
        profile=canonical_candidate_profile,
        target_channel="form",
        master_resume_text="Soumyadeep Nath — AI & Agentic Systems Engineer",
    )

    # --- 2. Wire all three real subsystems ---
    # Subsystem A: Memory Module (event-sourced store)
    fresh_store = SQLiteMemoryStore(fresh_environment["db_path"])

    # Subsystem B: Candidate Profile (#10)
    cp_adapter = CandidateProfileAdapter(data_dir=fresh_environment["profiles_dir"])
    cp_adapter.save_profile(canonical_candidate_profile)

    # Subsystem C: Usher / PDF Auto-Apply (real adapter, dry-run mode)
    auto_apply_adapter = PDFAutoApplyAdapter(
        output_dir=fresh_environment["pdf_output_dir"],
        dry_run=True,
    )

    ctx = NodeContext(
        candidate_profile_adapter=cp_adapter,
        auto_apply_adapter=auto_apply_adapter,
        memory_store=fresh_store,
        human_gate_callback=lambda s: "approve",
    )

    # --- 3. Execute the full graph ---
    graph = build_conductor_graph(ctx)
    final_output = graph.invoke(initial_state)
    final_state = (
        final_output
        if isinstance(final_output, ConductorState)
        else ConductorState.model_validate(final_output)
    )

    # === ASSERTIONS ===

    # A. Pipeline completed successfully via auto_apply path
    assert final_state.application.status == "auto_applied", (
        f"Expected 'auto_applied', got '{final_state.application.status}'. "
        f"Errors: {final_state.errors}"
    )
    assert final_state.node_trace == [
        "discover", "research", "tailor", "human_gate", "auto_apply", "persist"
    ]
    assert final_state.human_approval == "approve"
    assert not final_state.errors

    # B. Research Agent produced CompanyBrief
    assert final_state.application.company_brief is not None
    assert final_state.application.company_brief.company_name == f"FullIntTestCorp_{unique_id}"

    # C. AlignResume produced tailored resume
    assert final_state.application.tailored_resume is not None
    assert final_state.application.tailored_resume.match_score is not None

    # D. Usher / Auto-Apply produced form-payload artifact
    auto_apply = final_state.application.auto_apply
    assert auto_apply is not None
    assert auto_apply.mode == "dry_run"
    assert auto_apply.fields_submitted  # non-empty payload
    assert auto_apply.pdf_resume_path

    # Verify the PDF resume file exists on disk
    resume_path = Path(auto_apply.pdf_resume_path)
    assert resume_path.exists(), f"Resume artifact not found at {resume_path}"
    content = resume_path.read_text(encoding="utf-8")
    assert "TAILORED RESUME" in content

    # E. Memory Module store was updated (persist_node saved the application)
    persisted = fresh_store.get_application(final_state.job_id)
    assert persisted is not None
    assert persisted.status == "auto_applied"

    # F. Candidate Profile was updated with application_history
    if final_state.profile:
        assert len(final_state.profile.tailoring_history) >= 1, (
            "Tailoring history should have at least 1 entry from tailor_node"
        )
        assert final_state.profile.tailoring_history[-1].component == "align_resume"

        assert len(final_state.profile.application_history) >= 1, (
            "Application history should have at least 1 entry from auto_apply_node"
        )
        assert final_state.profile.application_history[-1].component == "usher"

    # G. Anti-fabrication: skills_matched must only contain verified skills
    if final_state.application.tailored_resume.skills_matched:
        verified_skill_names = {s.name.lower() for s in canonical_candidate_profile.skills}
        for matched in final_state.application.tailored_resume.skills_matched:
            assert matched.lower() in verified_skill_names, (
                f"Matched skill '{matched}' not in verified profile skills — anti-fabrication violation!"
            )


# ---------------------------------------------------------------------------
# Test: Email channel end-to-end (Overture path)
# ---------------------------------------------------------------------------

def test_full_integration_email_channel(
    canonical_candidate_profile,
    fresh_environment,
):
    """Full pipeline via email channel: discover → ... → outreach → persist."""
    unique_id = uuid4().hex[:6]

    posting = PostingRef(
        company=f"EmailTestCorp_{unique_id}",
        title="AI Research Engineer",
        jd_text=(
            "Looking for an AI Research Engineer skilled in Python, transformer architectures, "
            "and evaluation-driven development for production LLM systems."
        ),
        contact_email=f"recruiting@emailtest_{unique_id}.io",
        application_channel="email",
    )

    app_record = ApplicationRecord(
        job_id=f"job_email_{unique_id}",
        source="manual",
        posting=posting,
        status="discovered",
    )

    initial_state = ConductorState(
        candidate_id="sdn9300",
        job_id=app_record.job_id,
        application=app_record,
        profile=canonical_candidate_profile,
        target_channel="email",
        master_resume_text="Soumyadeep Nath — AI & Agentic Systems Engineer",
    )

    fresh_store = SQLiteMemoryStore(fresh_environment["db_path"])
    cp_adapter = CandidateProfileAdapter(data_dir=fresh_environment["profiles_dir"])
    cp_adapter.save_profile(canonical_candidate_profile)

    ctx = NodeContext(
        candidate_profile_adapter=cp_adapter,
        memory_store=fresh_store,
        human_gate_callback=lambda s: "approve",
    )

    graph = build_conductor_graph(ctx)
    final_output = graph.invoke(initial_state)
    final_state = (
        final_output
        if isinstance(final_output, ConductorState)
        else ConductorState.model_validate(final_output)
    )

    assert final_state.application.status == "outreach_sent"
    assert final_state.node_trace == [
        "discover", "research", "tailor", "human_gate", "outreach", "persist"
    ]
    assert not final_state.errors

    # Candidate Profile updated with outreach_history
    if final_state.profile:
        assert len(final_state.profile.outreach_history) >= 1
        assert final_state.profile.outreach_history[-1].component == "overture"
