"""
Failure injection test suite for Conductor Agent.
Verifies ADR-4 (No-Silent-Drop principle) and graceful degradation across all adapter failure modes.
"""

import os
import pytest
import tempfile
from pathlib import Path
from conductor.adapters.base import AgentAdapter, AgentResult
from conductor.graph.nodes import NodeContext
from conductor.graph.workflow import build_conductor_graph
from conductor.state import ApplicationRecord, ConductorState, PostingRef
from conductor.storage.local_store import SQLiteMemoryStore


class FailingAdapter(AgentAdapter):
    """Mock adapter that deliberately fails with a configured error."""

    def __init__(self, name: str, error_msg: str):
        self._name = name
        self._error_msg = error_msg

    @property
    def name(self) -> str:
        return self._name

    def invoke(self, state_dict):
        return AgentResult(success=False, error=self._error_msg)

    def draft_email(self, contact, use_llm=False):
        return {
            "draft_subject": f"Subject for {contact.get('company', 'Company')}",
            "draft_body": "Sample draft body",
        }

    def health_check(self):
        return False


@pytest.fixture
def base_state():
    posting = PostingRef(
        company="Failure Lab",
        title="Test Engineer",
        jd_text="Testing fault tolerance and error boundaries in distributed multi-agent systems.",
    )
    app = ApplicationRecord(posting=posting)
    return ConductorState(job_id=app.job_id, application=app)


def test_harvester_failure_injection(base_state):
    """When Harvester fails, graph halts at discover, persists error, and returns without unhandled crash."""
    temp_dir = tempfile.mkdtemp()
    try:
        db_path = Path(temp_dir) / "test_fail1.db"
        store = SQLiteMemoryStore(str(db_path))
        ctx = NodeContext(
            harvester_adapter=FailingAdapter("harvester_stub", "Simulated Harvester timeout"),
            memory_store=store,
            human_gate_callback=lambda s: "approve",
        )
        graph = build_conductor_graph(ctx)

        res = graph.invoke(base_state)
        final_state = res if isinstance(res, ConductorState) else ConductorState.model_validate(res)

        assert final_state.application.status == "error"
        assert any("Harvester" in e for e in final_state.errors)
        assert "tailor" not in final_state.node_trace
        assert "persist" in final_state.node_trace

        # Assert persisted record exists (ADR-4)
        persisted = store.get_application(final_state.job_id)
        assert persisted is not None
        assert persisted.status == "error"
    finally:
        for f in Path(temp_dir).glob("*"):
            try:
                f.unlink()
            except Exception:
                pass
        try:
            os.rmdir(temp_dir)
        except Exception:
            pass


def test_align_resume_failure_injection(base_state):
    """When AlignResume fails, graph halts at tailor, persists error, and skips human gate & outreach."""
    temp_dir = tempfile.mkdtemp()
    try:
        db_path = Path(temp_dir) / "test_fail2.db"
        store = SQLiteMemoryStore(str(db_path))
        ctx = NodeContext(
            align_resume_adapter=FailingAdapter("align_resume", "Simulated 500 LLM Rate Limit"),
            memory_store=store,
            human_gate_callback=lambda s: "approve",
        )
        graph = build_conductor_graph(ctx)

        res = graph.invoke(base_state)
        final_state = res if isinstance(res, ConductorState) else ConductorState.model_validate(res)

        assert final_state.application.status == "error"
        assert any("Simulated 500 LLM Rate Limit" in e or "AlignResume" in e for e in final_state.errors)
        assert "human_gate" not in final_state.node_trace
        assert "outreach" not in final_state.node_trace
        assert "persist" in final_state.node_trace

        persisted = store.get_application(final_state.job_id)
        assert persisted is not None
        assert persisted.status == "error"
    finally:
        for f in Path(temp_dir).glob("*"):
            try:
                f.unlink()
            except Exception:
                pass
        try:
            os.rmdir(temp_dir)
        except Exception:
            pass


def test_overture_failure_injection(base_state):
    """When Overture fails, error is recorded and application status reflects failure."""
    temp_dir = tempfile.mkdtemp()
    try:
        db_path = Path(temp_dir) / "test_fail3.db"
        store = SQLiteMemoryStore(str(db_path))
        ctx = NodeContext(
            overture_adapter=FailingAdapter("overture", "Simulated Gmail OAuth Expired"),
            memory_store=store,
            human_gate_callback=lambda s: "approve",
        )
        graph = build_conductor_graph(ctx)

        res = graph.invoke(base_state)
        final_state = res if isinstance(res, ConductorState) else ConductorState.model_validate(res)

        assert final_state.application.status == "error"
        assert any("Simulated Gmail OAuth Expired" in e or "Overture" in e for e in final_state.errors)
        assert "persist" in final_state.node_trace

        persisted = store.get_application(final_state.job_id)
        assert persisted is not None
        assert persisted.status == "error"
    finally:
        for f in Path(temp_dir).glob("*"):
            try:
                f.unlink()
            except Exception:
                pass
        try:
            os.rmdir(temp_dir)
        except Exception:
            pass
