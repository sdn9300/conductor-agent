"""
Unit tests for Conductor MemoryStore implementations.
Tests SQLiteMemoryStore and JSONMemoryStore.
"""

import os
import tempfile
from pathlib import Path
from conductor.state import ApplicationRecord, CandidateProfile, PostingRef
from conductor.storage.local_store import SQLiteMemoryStore, JSONMemoryStore


def test_sqlite_memory_store():
    """SQLite store persists application, retrieves it, and handles cooldown."""
    temp_dir = tempfile.mkdtemp()
    try:
        db_path = Path(temp_dir) / "test_memory.db"
        store = SQLiteMemoryStore(str(db_path))

        posting = PostingRef(
            company="Anthropic Labs",
            title="Prompt Engineer",
            jd_text="Prompt optimization and eval harness development with Python.",
        )
        app = ApplicationRecord(posting=posting, status="outreach_sent")

        # Save
        assert store.save_application(app) is True

        # Retrieve
        fetched = store.get_application(app.job_id)
        assert fetched is not None
        assert fetched.posting.company == "Anthropic Labs"
        assert fetched.status == "outreach_sent"

        # List
        apps = store.list_applications(limit=10)
        assert len(apps) == 1

        # Cooldown check
        assert store.is_company_in_cooldown("Anthropic Labs", cooldown_days=30) is True
        assert store.is_company_in_cooldown("Unknown Co", cooldown_days=30) is False

        # Profile Save & Get
        profile = CandidateProfile(candidate_id="test_candidate")
        assert store.save_candidate_profile(profile) is True
        fetched_profile = store.get_candidate_profile("test_candidate")
        assert fetched_profile is not None
        assert fetched_profile.candidate_id == "test_candidate"
    finally:
        # cleanup
        for f in Path(temp_dir).glob("*"):
            try:
                f.unlink()
            except Exception:
                pass
        try:
            os.rmdir(temp_dir)
        except Exception:
            pass


def test_json_memory_store():
    """JSON store persists application and retrieves correctly."""
    temp_dir = tempfile.mkdtemp()
    try:
        json_path = Path(temp_dir) / "test_log.json"
        store = JSONMemoryStore(str(json_path))

        posting = PostingRef(
            company="OpenAI Corp",
            title="Systems Engineer",
            jd_text="High performance infrastructure for AI workloads and training.",
        )
        app = ApplicationRecord(posting=posting, status="discovered")

        assert store.save_application(app) is True
        fetched = store.get_application(app.job_id)
        assert fetched is not None
        assert fetched.posting.company == "OpenAI Corp"

        # Update status
        app.status = "outreach_sent"
        app.update_timestamp("last_updated")
        assert store.save_application(app) is True
        assert store.is_company_in_cooldown("OpenAI Corp", cooldown_days=30) is True
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
