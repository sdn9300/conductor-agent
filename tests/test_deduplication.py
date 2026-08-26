"""
Unit and integration tests for Conductor deduplication logic (EC-06 & Task 2.4).
Verifies that previously processed postings are identified and bypassed without redundant LLM calls.
"""

import os
import pytest
import tempfile
from pathlib import Path
from conductor.graph.nodes import NodeContext
from conductor.graph.workflow import build_conductor_graph
from conductor.state import ApplicationRecord, ConductorState, PostingRef
from conductor.storage.local_store import SQLiteMemoryStore, JSONMemoryStore


@pytest.fixture
def temp_store():
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_dedupe.db"
    store = SQLiteMemoryStore(str(db_path))
    yield store
    for f in Path(temp_dir).glob("*"):
        try:
            f.unlink()
        except Exception:
            pass
    try:
        os.rmdir(temp_dir)
    except Exception:
        pass


def test_sqlite_deduplication_matching(temp_store):
    """SQLiteMemoryStore detects duplicates by link or (company + title)."""
    posting1 = PostingRef(
        company="Scale AI",
        title="Agent Engineer",
        jd_text="Build high-throughput LLM pipelines and multi-agent coordination.",
        url="https://scale.com/careers/agent-eng-1",
    )
    app1 = ApplicationRecord(posting=posting1, status="outreach_sent")
    temp_store.save_application(app1)

    # 1. Matching by link
    assert temp_store.is_duplicate_posting(link="https://scale.com/careers/agent-eng-1") is True

    # 2. Matching by company + title (case-insensitive)
    assert temp_store.is_duplicate_posting(company="scale ai", title="agent engineer") is True

    # 3. New posting is not duplicate
    assert temp_store.is_duplicate_posting(link="https://other.com/job", company="Other Co", title="ML Dev") is False


def test_workflow_bypasses_duplicate_posting(temp_store):
    """Graph marks duplicate posting as skipped_duplicate and bypasses tailoring & outreach."""
    # Seed an existing application in the store
    existing_posting = PostingRef(
        company="Anthropic",
        title="Prompt Alignment Engineer",
        jd_text="Experience with prompt optimization, eval harnesses, and LLM safety.",
        url="https://anthropic.com/careers/eval-101",
    )
    existing_app = ApplicationRecord(posting=existing_posting, status="outreach_sent")
    temp_store.save_application(existing_app)

    # Now attempt to run the same posting through the graph
    dup_record = ApplicationRecord(posting=existing_posting, status="discovered")
    state = ConductorState(job_id=dup_record.job_id, application=dup_record)

    ctx = NodeContext(
        memory_store=temp_store,
        human_gate_callback=lambda s: "approve",
    )
    graph = build_conductor_graph(ctx)

    res = graph.invoke(state)
    final_state = res if isinstance(res, ConductorState) else ConductorState.model_validate(res)

    # Verify status and trace
    assert final_state.application.status == "skipped_duplicate"
    assert "discover" in final_state.node_trace
    assert "tailor" not in final_state.node_trace
    assert "human_gate" not in final_state.node_trace
    assert "outreach" not in final_state.node_trace
    assert "persist" in final_state.node_trace
