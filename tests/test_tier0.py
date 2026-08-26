"""
Unit tests for Tier-0 Baseline Optimization Pass (ADR-1 & Task 2.3).
Verifies decoupled execution of general target-role resume optimization.
"""

import os
import pytest
import tempfile
from pathlib import Path
from conductor.graph.nodes import NodeContext, execute_tier0_baseline
from conductor.state import CandidateProfile
from conductor.storage.local_store import SQLiteMemoryStore


def test_tier0_baseline_execution():
    """Tier-0 baseline optimization executes and persists to CandidateProfile."""
    temp_dir = tempfile.mkdtemp()
    try:
        db_path = Path(temp_dir) / "test_tier0.db"
        store = SQLiteMemoryStore(str(db_path))
        ctx = NodeContext(memory_store=store)

        master_resume = (
            "Soumyadeep Nath — AI & Agentic Systems Engineer\n"
            "Experience with LangGraph orchestration, Python, LLMs, and distributed backend systems."
        )

        res = execute_tier0_baseline(
            role="GenAI Systems Architect",
            master_resume_text=master_resume,
            context=ctx,
        )

        assert res.get("success") is True
        assert res.get("role") == "GenAI Systems Architect"
        assert "optimization" in res
        assert res["optimization"]["match_score"] is not None

        # Verify candidate profile has the saved baseline
        profile = store.get_candidate_profile()
        assert profile is not None
        assert "GenAI Systems Architect" in profile.baseline_optimizations
        opt = profile.baseline_optimizations["GenAI Systems Architect"]
        assert opt["match_score"] is not None
        assert "updated_at" in opt

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
