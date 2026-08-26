"""
Integration test suite for Conductor Agent Phase 1 MVP.
Runs 10 consecutive automated end-to-end runs asserting complete trace, zero silent drops,
schema compliance, and persistence (per CONDUCTOR_05_Evaluation_Plan.md).
"""

import os
import tempfile
from pathlib import Path
import pytest
from conductor.graph.nodes import NodeContext
from conductor.graph.workflow import build_conductor_graph
from conductor.state import ApplicationRecord, ConductorState, PostingRef
from conductor.storage.local_store import SQLiteMemoryStore


@pytest.fixture
def clean_store():
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_integration.db"
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


def test_ten_consecutive_runs_end_to_end(clean_store):
    """
    Execute 10 varied end-to-end runs including happy path, human rejection,
    human abort, and edge cases. Assert zero silent drops across all 10.
    """
    scenarios = [
        # (Company, Role, Approval Choice, Expected Status)
        ("Google DeepMind", "Research Engineer", "approve", "outreach_sent"),
        ("Anthropic", "Alignment Engineer", "approve", "outreach_sent"),
        ("OpenAI", "Systems Engineer", "reject", "outreach_rejected"),
        ("Meta AI", "Production AI Engineer", "approve", "outreach_sent"),
        ("Mistral AI", "LLM Infrastructure Engineer", "abort", "closed"),
        ("Cohere", "NLP Engineer", "approve", "outreach_sent"),
        ("Scale AI", "Data Infrastructure Lead", "approve", "outreach_sent"),
        ("Hugging Face", "Open Source AI Engineer", "reject", "outreach_rejected"),
        ("Perplexity", "Search Systems Engineer", "approve", "outreach_sent"),
        ("Amazon AGI", "Applied AI Scientist", "approve", "outreach_sent"),
    ]

    for idx, (company, role, choice, expected_status) in enumerate(scenarios, start=1):
        posting = PostingRef(
            company=company,
            title=role,
            jd_text=(
                f"We are hiring a {role} at {company} to build scalable AI systems, "
                f"multi-agent orchestration architectures, and robust evaluation suites. "
                f"Requires strong Python, LangGraph, backend engineering, and distributed systems."
            ),
            url=f"https://{company.lower().replace(' ', '')}.com/careers/{idx}",
        )

        app_record = ApplicationRecord(posting=posting)
        state = ConductorState(
            candidate_id="sdn9300",
            job_id=app_record.job_id,
            application=app_record,
        )

        ctx = NodeContext(
            memory_store=clean_store,
            human_gate_callback=lambda s, c=choice: c,
        )
        graph = build_conductor_graph(ctx)

        result = graph.invoke(state)
        final_state = result if isinstance(result, ConductorState) else ConductorState.model_validate(result)

        # 1. State must match expected lifecycle status
        assert final_state.application.status == expected_status, (
            f"Run #{idx} ({company}): expected {expected_status}, got {final_state.application.status}, errors: {final_state.errors}"
        )

        # 2. Persisted record must exist in SQLite (ADR-4 No-Silent-Drop)
        persisted = clean_store.get_application(final_state.job_id)
        assert persisted is not None, f"Run #{idx} ({company}): record was not persisted!"
        assert persisted.status == expected_status
        assert persisted.posting.company == company

        # 3. Intermediate milestones must have timestamps
        assert "discovered" in persisted.timestamps
        assert "last_updated" in persisted.timestamps

        # 4. If approved and sent, tailored resume and outreach must exist
        if expected_status == "outreach_sent":
            assert persisted.tailored_resume is not None
            assert persisted.tailored_resume.match_score is not None
            assert persisted.outreach is not None
            assert persisted.outreach.draft_subject is not None

    # Assert total persisted records in store is exactly 10
    all_records = clean_store.list_applications(limit=50)
    assert len(all_records) == 10
