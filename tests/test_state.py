"""
Unit tests for Conductor state and schema definitions.
Validates Pydantic schema constraints, JSON serialization, and transitions.
"""

import pytest
from pydantic import ValidationError
from conductor.state import (
    PostingRef,
    ApplicationRecord,
    CandidateProfile,
    ConductorState,
    TailoredResumeRef,
    OutreachRef,
    SentimentSignal,
)


def test_posting_ref_validation():
    """PostingRef must enforce minimum JD length and required fields."""
    with pytest.raises(ValidationError):
        PostingRef(company="Acme", title="Dev", jd_text="Short")

    valid_posting = PostingRef(
        company="Acme Corp",
        title="AI Engineer",
        jd_text="A comprehensive job description with sufficient length for testing.",
    )
    assert valid_posting.company == "Acme Corp"
    assert valid_posting.title == "AI Engineer"


def test_application_record_lifecycle():
    """ApplicationRecord initializes with discovered status and supports timestamp updates."""
    posting = PostingRef(
        company="Tech Innovations",
        title="Senior Python Engineer",
        jd_text="Build scalable backend services in Python and FastAPI with LangGraph.",
    )
    app = ApplicationRecord(posting=posting)
    assert app.status == "discovered"
    assert "discovered" in app.timestamps
    assert app.job_id is not None

    app.update_timestamp("tailored")
    assert "tailored" in app.timestamps
    assert "last_updated" in app.timestamps


def test_candidate_profile_schema():
    """CandidateProfile must validate schema matching Candidate Profile JSON v0.1."""
    profile = CandidateProfile()
    assert profile.candidate_id == "sdn9300"
    assert len(profile.target_roles) >= 1

    posting = PostingRef(
        company="Test Corp",
        title="ML Engineer",
        jd_text="Machine learning pipelines and model evaluation frameworks.",
    )
    app = ApplicationRecord(posting=posting)
    profile.applications.append(app)

    profile_json = profile.model_dump_json()
    assert "Test Corp" in profile_json

    restored = CandidateProfile.model_validate_json(profile_json)
    assert restored.applications[0].posting.company == "Test Corp"


def test_conductor_state_recording():
    """ConductorState must record node transitions and handle errors cleanly."""
    posting = PostingRef(
        company="NextGen AI",
        title="Agentic Engineer",
        jd_text="Develop agentic workflows and tool integrations with MCP.",
    )
    app = ApplicationRecord(posting=posting)
    state = ConductorState(job_id=app.job_id, application=app)

    state.record_node("discover")
    assert state.current_node == "discover"
    assert state.node_trace == ["discover"]
    assert state.application.checkpoint == "discover"

    state.record_error("Simulated timeout error")
    assert len(state.errors) == 1
    assert state.application.status == "error"
    assert state.application.error == "Simulated timeout error"
