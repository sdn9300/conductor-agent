"""
Unit tests for Conductor Agent adapters.
Tests HarvesterStubAdapter, AlignResumeAdapter, and OvertureAdapter in isolation.
"""

import pytest
from conductor.adapters.harvester_stub import HarvesterStubAdapter
from conductor.adapters.align_resume import AlignResumeAdapter
from conductor.adapters.overture import OvertureAdapter
from conductor.state import ApplicationRecord, ConductorState, PostingRef


@pytest.fixture
def sample_state():
    posting = PostingRef(
        company="DeepMind Solutions",
        title="Agentic AI Engineer",
        jd_text="Experience with LangGraph, Python, LLM evaluation, and agentic workflows.",
    )
    app = ApplicationRecord(posting=posting)
    return ConductorState(job_id=app.job_id, application=app)


def test_harvester_stub_adapter(sample_state):
    """HarvesterStubAdapter extracts posting successfully."""
    adapter = HarvesterStubAdapter()
    res = adapter.invoke(sample_state.model_dump())
    assert res.success is True
    assert res.output is not None
    assert res.output["posting"]["company"] == "DeepMind Solutions"


def test_harvester_stub_empty():
    """HarvesterStubAdapter returns clean error on empty posting."""
    adapter = HarvesterStubAdapter()
    res = adapter.invoke({})
    assert res.success is False
    assert "No seed job posting" in (res.error or "")


def test_align_resume_adapter_fallback(sample_state):
    """AlignResumeAdapter generates deterministic tailored resume even when service is offline."""
    adapter = AlignResumeAdapter(base_url="http://localhost:9999", timeout=0.1, allow_fallback=True)
    res = adapter.invoke(sample_state.model_dump())
    assert res.success is True
    assert res.output is not None
    assert "tailored_content" in res.output
    assert res.output["match_score"] > 50.0
    assert "Python" in res.output["skills_matched"] or "Langgraph" in res.output["skills_matched"]


def test_align_resume_adapter_rejects_short_jd():
    """AlignResumeAdapter fails gracefully if JD is too short."""
    adapter = AlignResumeAdapter()
    state_dict = {
        "application": {
            "posting": {"company": "Test", "title": "Dev", "jd_text": "Too short"}
        }
    }
    res = adapter.invoke(state_dict)
    assert res.success is False
    assert "too short" in (res.error or "")


def test_overture_adapter_dry_run(sample_state):
    """OvertureAdapter generates email draft and returns dry_run status."""
    adapter = OvertureAdapter(dry_run=True)
    res = adapter.invoke(sample_state.model_dump())
    assert res.success is True
    assert res.output is not None
    assert res.output["status"] == "dry_run"
    assert "DeepMind Solutions" in res.output["draft_subject"]
    assert "Soumyadeep Nath" in res.output["draft_body"]
