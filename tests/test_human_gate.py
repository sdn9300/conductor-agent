"""
Unit and structural tests for the Human Approval Gate (ADR-6 & EC-13).
Verifies that outreach dispatch can never execute without explicit prior approval.
"""

import os
import pytest
import tempfile
from pathlib import Path
from conductor.graph.nodes import NodeContext, outreach_node, human_gate_node
from conductor.graph.workflow import build_conductor_graph
from conductor.state import ApplicationRecord, ConductorState, PostingRef
from conductor.storage.local_store import SQLiteMemoryStore


@pytest.fixture
def test_context():
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_gate.db"
    store = SQLiteMemoryStore(str(db_path))
    yield NodeContext(memory_store=store)
    for f in Path(temp_dir).glob("*"):
        try:
            f.unlink()
        except Exception:
            pass
    try:
        os.rmdir(temp_dir)
    except Exception:
        pass


@pytest.fixture
def sample_state():
    posting = PostingRef(
        company="Horizon Robotics",
        title="Autonomous Systems Engineer",
        jd_text="Develop agentic planning and robotics control software with Python.",
    )
    app = ApplicationRecord(posting=posting, status="outreach_pending_review")
    return ConductorState(job_id=app.job_id, application=app)


def test_structural_gate_bypass_prevention(test_context, sample_state):
    """Direct invocation of outreach_node without prior approval must be rejected."""
    sample_state.human_approval = None  # No approval given
    result_state = outreach_node(sample_state, test_context)

    # Must record error and not send
    assert result_state.application.status == "error"
    assert any("bypass attempted" in err for err in result_state.errors)
    assert result_state.application.outreach is None


def test_human_gate_approval_workflow(test_context, sample_state):
    """When approved, the graph completes through outreach."""
    ctx = NodeContext(
        memory_store=test_context.memory_store,
        human_gate_callback=lambda s: "approve",
    )
    graph = build_conductor_graph(ctx)

    res = graph.invoke(sample_state)
    final_state = res if isinstance(res, ConductorState) else ConductorState.model_validate(res)

    assert final_state.human_approval == "approve"
    assert final_state.application.status == "outreach_sent"
    assert "human_gate" in final_state.node_trace
    assert "outreach" in final_state.node_trace
    assert "persist" in final_state.node_trace


def test_human_gate_rejection_workflow(test_context, sample_state):
    """When rejected, outreach node is bypassed and status is outreach_rejected."""
    ctx = NodeContext(
        memory_store=test_context.memory_store,
        human_gate_callback=lambda s: "reject",
    )
    graph = build_conductor_graph(ctx)

    res = graph.invoke(sample_state)
    final_state = res if isinstance(res, ConductorState) else ConductorState.model_validate(res)

    assert final_state.human_approval == "reject"
    assert final_state.application.status == "outreach_rejected"
    assert "outreach" not in final_state.node_trace
    assert "persist" in final_state.node_trace


def test_human_gate_abort_workflow(test_context, sample_state):
    """When aborted/quit, status is closed and outreach is not sent."""
    ctx = NodeContext(
        memory_store=test_context.memory_store,
        human_gate_callback=lambda s: "abort",
    )
    graph = build_conductor_graph(ctx)

    res = graph.invoke(sample_state)
    final_state = res if isinstance(res, ConductorState) else ConductorState.model_validate(res)

    assert final_state.human_approval == "abort"
    assert final_state.application.status == "closed"
    assert "outreach" not in final_state.node_trace
