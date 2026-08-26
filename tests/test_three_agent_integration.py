"""
Full 3-Agent Integration Test Suite (Phase 2 MVP).
Verifies complete end-to-end orchestration across Harvester, AlignResume, and Overture.
"""

import os
import pytest
import tempfile
from pathlib import Path
from conductor.adapters.align_resume import AlignResumeAdapter
from conductor.adapters.harvester import HarvesterAdapter
from conductor.adapters.overture import OvertureAdapter
from conductor.graph.nodes import NodeContext
from conductor.graph.workflow import build_conductor_graph
from conductor.state import ApplicationRecord, ConductorState, PostingRef
from conductor.storage.local_store import SQLiteMemoryStore


@pytest.fixture
def test_environment():
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_3agent.db"
    store = SQLiteMemoryStore(str(db_path))

    ctx = NodeContext(
        harvester_adapter=HarvesterAdapter(allow_fallback=True),
        align_resume_adapter=AlignResumeAdapter(allow_fallback=True),
        overture_adapter=OvertureAdapter(dry_run=True),
        memory_store=store,
        human_gate_callback=lambda s: "approve",
    )

    yield {"store": store, "context": ctx}

    for f in Path(temp_dir).glob("*"):
        try:
            f.unlink()
        except Exception:
            pass
    try:
        os.rmdir(temp_dir)
    except Exception:
        pass


def test_three_agent_end_to_end_orchestration(test_environment):
    """
    Execute 3-agent orchestration:
    1. Harvester discovers/supplies job opportunity.
    2. AlignResume tailors master resume against specific JD.
    3. Human Gate approves.
    4. Overture generates customized cold email & dry-run dispatches.
    5. MemoryStore commits run checkpoint with no silent drops.
    """
    ctx = test_environment["context"]
    store = test_environment["store"]

    # Initialize graph
    graph = build_conductor_graph(ctx)

    # 1. Fetch real or fallback postings via Harvester
    postings = ctx.harvester_adapter.fetch_jobs(role="AI Engineer", location="Remote", limit=1)
    assert len(postings) >= 1
    target_posting = postings[0]

    # 2. Package into state
    app_record = ApplicationRecord(
        source=target_posting.source,
        posting=target_posting,
        status="discovered",
    )
    initial_state = ConductorState(
        candidate_id="sdn9300",
        job_id=app_record.job_id,
        application=app_record,
        master_resume_text=(
            "Soumyadeep Nath — AI & Agentic Systems Engineer\n"
            "Expert in LangGraph multi-agent coordination, Python backend architectures, and LLM evaluations."
        ),
    )

    # 3. Invoke Graph
    result = graph.invoke(initial_state)
    final_state = result if isinstance(result, ConductorState) else ConductorState.model_validate(result)

    # 4. Assert Complete Pipeline Traversal
    assert final_state.application.status == "outreach_sent"
    assert final_state.node_trace == ["discover", "research", "tailor", "human_gate", "outreach", "persist"]

    # 5. Assert AlignResume artifact attached
    assert final_state.application.tailored_resume is not None
    assert final_state.application.tailored_resume.match_score is not None
    assert len(final_state.application.tailored_resume.skills_matched) > 0

    # 6. Assert Overture outreach attached
    assert final_state.application.outreach is not None
    assert final_state.application.outreach.status == "dry_run"
    assert final_state.application.outreach.draft_subject is not None
    assert target_posting.company in final_state.application.outreach.draft_subject or "Soumyadeep" in final_state.application.outreach.draft_subject

    # 7. Assert Persistence
    persisted = store.get_application(final_state.job_id)
    assert persisted is not None
    assert persisted.status == "outreach_sent"
    assert persisted.posting.company == target_posting.company
