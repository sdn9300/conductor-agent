"""
Full multi-channel routing and 10-component orchestration tests (Phase 4).
Verifies automatic routing between Overture (cold email) and PDF Auto-Apply (portal submission),
as well as Research Agent enrichment before resume tailoring.
"""

import os
import pytest
import tempfile
from pathlib import Path
from conductor.adapters.align_resume import AlignResumeAdapter
from conductor.adapters.auto_apply import PDFAutoApplyAdapter
from conductor.adapters.harvester import HarvesterAdapter
from conductor.adapters.overture import OvertureAdapter
from conductor.adapters.research import ResearchAgentAdapter
from conductor.adapters.sentiment import SentimentClassifierAdapter
from conductor.graph.nodes import NodeContext
from conductor.graph.workflow import build_conductor_graph
from conductor.state import ApplicationRecord, ConductorState, PostingRef
from conductor.storage.local_store import SQLiteMemoryStore


@pytest.fixture
def test_environment():
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_routing.db"
    store = SQLiteMemoryStore(str(db_path))

    ctx = NodeContext(
        harvester_adapter=HarvesterAdapter(allow_fallback=True),
        research_adapter=ResearchAgentAdapter(),
        align_resume_adapter=AlignResumeAdapter(allow_fallback=True),
        overture_adapter=OvertureAdapter(dry_run=True),
        auto_apply_adapter=PDFAutoApplyAdapter(output_dir=temp_dir, dry_run=True),
        sentiment_adapter=SentimentClassifierAdapter(),
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


def test_email_channel_routing(test_environment):
    """
    Posting with recruiter email routes automatically to Overture:
    discover -> research -> tailor -> human_gate -> outreach -> persist
    """
    ctx = test_environment["context"]
    store = test_environment["store"]
    graph = build_conductor_graph(ctx)

    posting = PostingRef(
        company="Anthropic",
        title="Prompt Alignment Engineer",
        jd_text="Experience with prompt optimization, eval harnesses, Python, and LangGraph.",
        contact_email="talent@anthropic.com",
        contact_name="Sarah",
        application_channel="auto",
    )
    app = ApplicationRecord(posting=posting, status="discovered")
    state = ConductorState(
        candidate_id="sdn9300",
        job_id=app.job_id,
        application=app,
        master_resume_text="Soumyadeep Nath — AI Systems Engineer",
        target_channel="auto",
    )

    res = graph.invoke(state)
    final = res if isinstance(res, ConductorState) else ConductorState.model_validate(res)

    assert final.application.status == "outreach_sent"
    assert final.node_trace == ["discover", "research", "tailor", "human_gate", "outreach", "persist"]

    # Verify Research Agent enrichment
    assert final.application.company_brief is not None
    assert final.application.company_brief.company_name == "Anthropic"

    # Verify Overture draft & dispatch
    assert final.application.outreach is not None
    assert final.application.outreach.status == "dry_run"


def test_form_portal_channel_routing(test_environment):
    """
    Posting with careers portal link (e.g. Greenhouse/Lever) routes automatically to PDF Auto-Apply:
    discover -> research -> tailor -> human_gate -> auto_apply -> persist
    """
    ctx = test_environment["context"]
    store = test_environment["store"]
    graph = build_conductor_graph(ctx)

    posting = PostingRef(
        company="Stripe",
        title="Infrastructure AI Engineer",
        jd_text="Build scalable backend systems with Python, FastAPI, Docker, and distributed architectures.",
        url="https://boards.greenhouse.io/stripe/jobs/456789",
        application_channel="auto",
    )
    app = ApplicationRecord(posting=posting, status="discovered")
    state = ConductorState(
        candidate_id="sdn9300",
        job_id=app.job_id,
        application=app,
        master_resume_text="Soumyadeep Nath — AI Systems Engineer",
        target_channel="auto",
    )

    res = graph.invoke(state)
    final = res if isinstance(res, ConductorState) else ConductorState.model_validate(res)

    assert final.application.status == "auto_applied"
    assert final.node_trace == ["discover", "research", "tailor", "human_gate", "auto_apply", "persist"]

    # Verify Research Agent enrichment
    assert final.application.company_brief is not None
    assert final.application.company_brief.company_name == "Stripe"

    # Verify PDF Auto-Apply artifact & payload
    assert final.application.auto_apply is not None
    assert final.application.auto_apply.mode == "dry_run"
    assert "stripe" in (final.application.auto_apply.pdf_resume_path or "").lower()
    assert final.application.auto_apply.fields_submitted["company"] == "Stripe"

    # Verify persistence
    persisted = store.get_application(final.job_id)
    assert persisted is not None
    assert persisted.status == "auto_applied"
