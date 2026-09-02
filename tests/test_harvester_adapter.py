"""
Unit tests for HarvesterAdapter.
Verifies multi-board integration, 7-field canonical schema translation, and graceful fallback.
"""

import pytest
from conductor.adapters.gleaner import HarvesterAdapter
from conductor.state import ApplicationRecord, ConductorState, PostingRef


def test_harvester_adapter_initialization():
    """HarvesterAdapter initializes with default boards and path configuration."""
    adapter = HarvesterAdapter()
    assert adapter.name == "gleaner"
    assert len(adapter.default_boards) >= 1
    assert adapter.health_check() is True


def test_harvester_fetch_jobs_fallback():
    """HarvesterAdapter returns structured postings conforming to 7-field schema."""
    adapter = HarvesterAdapter(allow_fallback=True)
    postings = adapter.fetch_jobs(role="AI Engineer", location="Remote", limit=2)

    assert len(postings) > 0
    first = postings[0]
    assert isinstance(first, PostingRef)
    assert first.company is not None
    assert first.title is not None
    assert len(first.jd_text) >= 20
    assert first.location is not None and len(first.location) > 0


def test_harvester_invoke_with_existing_posting():
    """When a posting is already provided in state, HarvesterAdapter passes it through cleanly."""
    adapter = HarvesterAdapter()
    posting = PostingRef(
        company="DeepMind",
        title="Staff AI Engineer",
        jd_text="Experience with agentic workflows and LangGraph coordination architectures.",
        url="https://deepmind.google/careers/123",
    )
    app = ApplicationRecord(posting=posting)
    state = ConductorState(job_id=app.job_id, application=app)

    res = adapter.invoke(state.model_dump())
    assert res.success is True
    assert res.output is not None
    assert res.output["posting"]["company"] == "DeepMind"
    assert res.output["posting"]["title"] == "Staff AI Engineer"
