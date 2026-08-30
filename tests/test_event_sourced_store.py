"""
Unit and Integration tests for EventSourcedMemoryStore (Phase 1).
Verifies that Conductor's MemoryStore operations seamlessly emit canonical MemoryEvents
and materialize ApplicationRecords into CareerOS Memory Module (#8).
"""

import os
import tempfile
from datetime import datetime, timezone
import pytest

from conductor.state import (
    ApplicationRecord,
    PostingRef,
    TailoredResumeRef,
    OutreachRef,
    SentimentSignal,
    ConductorState,
)
from conductor.storage.event_sourced_store import EventSourcedMemoryStore
from conductor.graph.nodes import NodeContext
from conductor.graph.workflow import build_conductor_graph
from src.models import EventType


@pytest.fixture
def temp_event_store(tmp_path):
    """Provides a temporary EventSourcedMemoryStore instance."""
    db_file = str(tmp_path / "test_memory_module.db")
    store = EventSourcedMemoryStore(db_path=db_file)
    return store


def test_event_sourced_store_initialization(temp_event_store):
    """EventSourcedMemoryStore initializes tables and connects to Memory Module."""
    assert temp_event_store._ledger is not None
    assert os.path.exists(temp_event_store.db_path)


def test_event_sourced_store_save_and_get_application(temp_event_store):
    """Saving an ApplicationRecord emits JOB_DISCOVERED and RESUME_TAILORED events."""
    posting = PostingRef(
        company="Anthropic",
        title="AI Alignment Engineer",
        jd_text="Experience in LangGraph and model evaluation required.",
        url="https://anthropic.com/jobs/123",
        contact_email="talent@anthropic.com",
    )
    tailored = TailoredResumeRef(
        run_id="align_run_001",
        tailored_content="Soumyadeep Nath — Tailored Resume for Anthropic",
        diff_summary="Enhanced LLM guardrails experience",
        match_score=92.5,
        skills_matched=["LangGraph", "Python"],
        skills_gap=["Rust"],
    )
    record = ApplicationRecord(
        job_id="job_anthropic_001",
        source="harvester",
        posting=posting,
        status="tailored",
        tailored_resume=tailored,
    )

    success = temp_event_store.save_application(record)
    assert success is True

    # Verify retrieval
    retrieved = temp_event_store.get_application("job_anthropic_001")
    assert retrieved is not None
    assert retrieved.posting.company == "Anthropic"
    assert retrieved.posting.title == "AI Alignment Engineer"
    assert retrieved.status == "tailored"
    assert retrieved.tailored_resume is not None
    assert retrieved.tailored_resume.match_score == 92.5

    # Verify events written to event ledger
    events = temp_event_store._ledger.get_history("job_anthropic_001")
    event_types = [e.event_type for e in events]
    assert EventType.JOB_DISCOVERED in event_types
    assert EventType.RESUME_TAILORED in event_types


def test_event_sourced_store_deduplication(temp_event_store):
    """is_duplicate_posting matches on URL and normalized (company + title)."""
    posting = PostingRef(
        company="Google DeepMind",
        title="Staff AI Engineer",
        jd_text="Distributed agent systems",
        url="https://deepmind.google/careers/ai-eng",
    )
    record = ApplicationRecord(
        job_id="job_deepmind_001",
        source="harvester",
        posting=posting,
        status="discovered",
    )
    temp_event_store.save_application(record)

    # 1. Duplicate URL match
    assert temp_event_store.is_duplicate_posting(link="https://deepmind.google/careers/ai-eng") is True
    # 2. Duplicate Company + Title match
    assert temp_event_store.is_duplicate_posting(company="google deepmind", title="staff ai engineer") is True
    # 3. Non-duplicate
    assert temp_event_store.is_duplicate_posting(link="https://other.com/job") is False
    assert temp_event_store.is_duplicate_posting(company="OpenAI", title="Researcher") is False


def test_event_sourced_store_cooldown_and_sentiment_inbound(temp_event_store):
    """Inbound rejection triggers 30-day domain cooldown and status transition."""
    posting = PostingRef(
        company="VentureScale",
        title="Senior AI Engineer",
        jd_text="Autonomous agents and multi-agent coordination systems for enterprise applications.",
        url="https://venturescale.io/job/1",
    )
    record = ApplicationRecord(
        job_id="job_venture_001",
        source="harvester",
        posting=posting,
        status="outreach_sent",
    )
    temp_event_store.save_application(record)

    # Ingest negative sentiment response
    signal = SentimentSignal(
        macro_sentiment="negative",
        intent_label="soft_rejection",
        urgency_score=1,
        confidence=0.95,
        key_phrases=["pursuing other candidates"],
        recommended_action="close",
        raw_text="Thank you, but we are pursuing other candidates.",
    )
    updated = temp_event_store.record_inbound_response("job_venture_001", signal)
    assert updated is not None
    assert updated.status == "closed"

    # Verify cooldown check
    assert temp_event_store.is_company_in_cooldown("VentureScale", cooldown_days=30) is True


def test_event_sourced_store_end_to_end_graph_execution(temp_event_store):
    """End-to-end LangGraph execution dry-run writes events to EventSourcedMemoryStore."""
    posting = PostingRef(
        company="Meta AI",
        title="Research Scientist",
        jd_text="PyTorch, LangGraph, and multi-agent coordination expert needed.",
        contact_email="recruiting@meta.com",
        application_channel="email",
    )
    app_record = ApplicationRecord(
        job_id="job_meta_001",
        source="manual",
        posting=posting,
        status="discovered",
    )
    initial_state = ConductorState(
        candidate_id="sdn9300",
        job_id="job_meta_001",
        application=app_record,
        master_resume_text="Soumyadeep Nath — AI Systems Engineer",
        target_channel="email",
    )

    ctx = NodeContext(
        memory_store=temp_event_store,
        human_gate_callback=lambda s: "approve",
    )
    graph = build_conductor_graph(ctx)

    final_output = graph.invoke(initial_state)
    final_state = final_output if isinstance(final_output, ConductorState) else ConductorState.model_validate(final_output)

    assert final_state.application.status == "outreach_sent"
    assert "discover" in final_state.node_trace
    assert "persist" in final_state.node_trace

    # Verify event ledger
    events = temp_event_store._ledger.get_history("job_meta_001")
    event_types = [e.event_type for e in events]
    assert EventType.JOB_DISCOVERED in event_types
    assert EventType.RESUME_TAILORED in event_types
    assert EventType.OUTREACH_SENT in event_types
