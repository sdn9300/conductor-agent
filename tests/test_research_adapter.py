"""
Unit tests for ResearchAgentAdapter (Phase 4).
Verifies company intelligence synthesis, tech signals extraction, and graceful fallback.
"""

import pytest
from conductor.adapters.research import ResearchAgentAdapter
from conductor.state import CompanyBriefRef


def test_research_adapter_initialization():
    """ResearchAgentAdapter initializes and passes health check."""
    adapter = ResearchAgentAdapter()
    assert adapter.name == "research_agent"
    assert adapter.health_check() is True


def test_research_company_synthesis():
    """ResearchAgentAdapter produces structured CompanyBriefRef with tech signals."""
    adapter = ResearchAgentAdapter()
    jd = "We are seeking an AI Engineer skilled in LangGraph, Python, FastAPI, and Kubernetes."
    
    brief = adapter.research_company(
        company_name="Nexus AI",
        job_description=jd,
        role="AI Engineer",
    )

    assert isinstance(brief, CompanyBriefRef)
    assert brief.company_name == "Nexus AI"
    assert len(brief.summary) > 10
    assert len(brief.tech_signals) > 0
    assert any(s.lower() in ("langgraph", "python", "fastapi", "kubernetes") for s in brief.tech_signals)
    assert len(brief.recent_news) > 0
    assert len(brief.culture_notes) > 5


def test_research_adapter_invoke():
    """Adapter.invoke handles state dictionaries and returns AgentResult."""
    adapter = ResearchAgentAdapter()
    state_dict = {
        "application": {
            "posting": {
                "company": "DeepMind",
                "title": "Staff Research Engineer",
                "jd_text": "Working on LLM agent architectures, distributed Python systems, and evaluations.",
            }
        }
    }
    res = adapter.invoke(state_dict)
    assert res.success is True
    assert res.output is not None
    assert "company_brief" in res.output
    brief_data = res.output["company_brief"]
    assert brief_data["company_name"] == "DeepMind"
    assert len(brief_data["tech_signals"]) > 0
