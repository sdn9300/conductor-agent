"""
Feedback loop integration tests for Conductor Agent (Phase 3).
Proves that inbound rejection sentiment signals measurably alter Conductor's next-run behavior
by suppressing re-outreach during the cooldown window (EC-07 & Task 3.3).
"""

import os
import pytest
import tempfile
from pathlib import Path
from conductor.adapters.sentiment import SentimentClassifierAdapter
from conductor.graph.nodes import NodeContext
from conductor.graph.workflow import build_conductor_graph
from conductor.state import ApplicationRecord, ConductorState, PostingRef
from conductor.storage.local_store import SQLiteMemoryStore


@pytest.fixture
def test_env():
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_feedback.db"
    store = SQLiteMemoryStore(str(db_path))
    sentiment_adapter = SentimentClassifierAdapter()

    ctx = NodeContext(
        memory_store=store,
        sentiment_adapter=sentiment_adapter,
        human_gate_callback=lambda s: "approve",
    )

    yield {"store": store, "context": ctx, "sentiment": sentiment_adapter}

    for f in Path(temp_dir).glob("*"):
        try:
            f.unlink()
        except Exception:
            pass
    try:
        os.rmdir(temp_dir)
    except Exception:
        pass


def test_rejection_sentiment_feedback_loop_suppression(test_env):
    """
    Phase 3 Exit Criterion Verification:
    1. Initial application to 'Apex Systems' succeeds through outreach.
    2. Apex Systems sends an inbound rejection email ('pursue other candidates').
    3. SentimentClassifier categorizes rejection and updates MemoryStore.
    4. Conductor encounters a new posting from 'Apex Systems'.
    5. Conductor suppresses outreach ('skipped_cooldown') due to active feedback cooldown.
    """
    store = test_env["store"]
    ctx = test_env["context"]
    sentiment_adapter = test_env["sentiment"]
    graph = build_conductor_graph(ctx)

    company_name = "Apex Systems"

    # ── Step 1: Initial Successful Outreach Run ──────────────────────────────
    initial_posting = PostingRef(
        company=company_name,
        title="AI Engineer",
        jd_text="Build LangGraph multi-agent pipelines and LLM evaluation tools in Python.",
        url="https://apexsystems.example/jobs/ai-1",
    )
    app1 = ApplicationRecord(posting=initial_posting, status="discovered")
    state1 = ConductorState(
        candidate_id="sdn9300",
        job_id=app1.job_id,
        application=app1,
        master_resume_text="Soumyadeep Nath — AI Systems Engineer",
    )

    res1 = graph.invoke(state1)
    state1_final = res1 if isinstance(res1, ConductorState) else ConductorState.model_validate(res1)

    assert state1_final.application.status == "outreach_sent"
    assert "outreach" in state1_final.node_trace

    # ── Step 2: Ingest Inbound Rejection Email ────────────────────────────────
    rejection_email = (
        "Thank you for taking the time to apply for the AI Engineer role at Apex Systems. "
        "Unfortunately, we have decided to pursue other candidates whose qualifications more closely fit our needs."
    )

    signal = sentiment_adapter.classify_response(
        raw_text=rejection_email,
        company=company_name,
        application_id=app1.job_id,
    )

    assert signal.macro_sentiment == "negative"
    assert signal.intent_label in ("soft_rejection", "hard_rejection")

    # Update MemoryStore with sentiment outcome
    updated = store.record_inbound_response(app1.job_id, signal)
    assert updated is not None
    assert updated.status == "closed"
    assert updated.sentiment_signal is not None

    # ── Step 3: Verify MemoryStore Cooldown is Active ────────────────────────
    assert store.is_company_in_cooldown(company_name, cooldown_days=30) is True

    # ── Step 4: Next Conductor Run on a NEW Posting from Apex Systems ────────
    new_posting = PostingRef(
        company=company_name,
        title="Lead Machine Learning Engineer",
        jd_text="Leading machine learning infrastructure, model fine-tuning, and LLM evaluation pipelines.",
        url="https://apexsystems.example/jobs/lead-ml-2",  # Different URL, not a duplicate posting
    )
    app2 = ApplicationRecord(posting=new_posting, status="discovered")
    state2 = ConductorState(
        candidate_id="sdn9300",
        job_id=app2.job_id,
        application=app2,
        master_resume_text="Soumyadeep Nath — AI Systems Engineer",
    )

    res2 = graph.invoke(state2)
    state2_final = res2 if isinstance(res2, ConductorState) else ConductorState.model_validate(res2)

    # ── Step 5: Assert Feedback Loop Suppressed Outreach ─────────────────────
    assert state2_final.application.status == "skipped_cooldown"
    assert state2_final.metadata.get("skip_reason") == "company_in_cooldown"
    assert "discover" in state2_final.node_trace
    assert "tailor" not in state2_final.node_trace
    assert "human_gate" not in state2_final.node_trace
    assert "outreach" not in state2_final.node_trace
    assert "persist" in state2_final.node_trace

    # Confirm persisted status in store
    persisted2 = store.get_application(state2_final.job_id)
    assert persisted2 is not None
    assert persisted2.status == "skipped_cooldown"
