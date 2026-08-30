"""
Unit tests for PDFAutoApplyAdapter (Phase 4, updated for Phase 3 Usher Integration).
Verifies application artifact compilation, form field extraction, and submission handling.
"""

import os
import pytest
import tempfile
from pathlib import Path
from conductor.adapters.auto_apply import PDFAutoApplyAdapter
from conductor.state import AutoApplyRef


def test_auto_apply_adapter_compilation():
    """PDFAutoApplyAdapter writes formatted resume artifact via internal compile method."""
    temp_dir = tempfile.mkdtemp()
    try:
        adapter = PDFAutoApplyAdapter(output_dir=temp_dir, dry_run=True)
        assert adapter.name == "pdf_auto_apply"
        assert adapter.health_check() is True

        # Test the internal compile method (renamed from public to private in Phase 3)
        resume_text = "Experienced AI Systems Engineer with deep expertise in LangGraph and Python backend architectures."
        artifact_path = adapter._compile_resume_artifact(
            job_id="test_job_12345",
            company="OpenAI",
            role="Research Systems Engineer",
            resume_content=resume_text,
        )

        assert artifact_path.exists()
        content = artifact_path.read_text(encoding="utf-8")
        assert "TAILORED RESUME" in content
        assert "OpenAI" in content
        assert resume_text in content

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


def test_auto_apply_adapter_invoke():
    """Adapter.invoke handles state dictionaries and returns AgentResult with form payload."""
    temp_dir = tempfile.mkdtemp()
    try:
        adapter = PDFAutoApplyAdapter(output_dir=temp_dir, dry_run=True)
        # Force fallback mode for deterministic test behavior
        adapter.use_usher = False

        state_dict = {
            "job_id": "test_invoke_999",
            "application": {
                "posting": {
                    "company": "Scale AI",
                    "title": "Staff AI Engineer",
                    "url": "https://scale.com/careers/999",
                    "jd_text": "Build scalable AI infrastructure with Python and distributed systems.",
                },
                "tailored_resume": {
                    "tailored_content": "Tailored resume content for Scale AI.",
                }
            }
        }
        res = adapter.invoke(state_dict)
        assert res.success is True
        assert res.output is not None
        assert "auto_apply" in res.output

        fields = res.output["auto_apply"]["fields_submitted"]
        assert fields["company"] == "Scale AI"
        assert fields["role"] == "Staff AI Engineer"
        assert "Soumyadeep Nath" in fields["full_name"]
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
