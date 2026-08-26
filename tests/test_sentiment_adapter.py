"""
Unit tests for SentimentClassifierAdapter (Phase 3).
Verifies classification of interview invites, rejections, and schema translation into SentimentSignal.
"""

import pytest
from conductor.adapters.sentiment import SentimentClassifierAdapter
from conductor.state import SentimentSignal


def test_sentiment_adapter_initialization():
    """SentimentClassifierAdapter initializes and passes health check."""
    adapter = SentimentClassifierAdapter()
    assert adapter.name == "sentiment_classifier"
    assert adapter.health_check() is True


def test_sentiment_interview_invite_classification():
    """Positive interview invitation response is classified with high urgency."""
    adapter = SentimentClassifierAdapter()
    raw = "Hi Soumyadeep, we reviewed your application and would love to schedule a 30-minute introductory call next week."
    
    signal = adapter.classify_response(
        raw_text=raw,
        company="OpenAI",
        role="AI Systems Engineer",
    )

    assert isinstance(signal, SentimentSignal)
    assert signal.macro_sentiment == "positive"
    assert signal.intent_label in ("interview_invite", "scheduling_link")
    assert signal.urgency_score == 5
    assert signal.confidence > 0.70
    assert "OpenAI" in (signal.recommended_action or "")


def test_sentiment_soft_rejection_classification():
    """Soft rejection response is classified as negative with cooldown guidance."""
    adapter = SentimentClassifierAdapter()
    raw = "Thank you for your interest in the AI role. Unfortunately, we have decided to pursue other candidates whose experience more closely matches our needs, but we will keep your resume for future opportunities."

    signal = adapter.classify_response(
        raw_text=raw,
        company="Databricks",
        role="Staff AI Engineer",
    )

    assert isinstance(signal, SentimentSignal)
    assert signal.macro_sentiment == "negative"
    assert signal.intent_label in ("soft_rejection", "hard_rejection")
    assert signal.urgency_score <= 2
    assert "cooldown" in (signal.recommended_action or "").lower() or "Databricks" in (signal.recommended_action or "")


def test_sentiment_adapter_invoke():
    """Adapter.invoke handles state dictionaries and returns AgentResult."""
    adapter = SentimentClassifierAdapter()
    state_dict = {
        "company": "DeepMind",
        "role": "Research Scientist",
        "raw_text": "We are pleased to invite you to an interview.",
    }
    res = adapter.invoke(state_dict)
    assert res.success is True
    assert res.output is not None
    assert "sentiment_signal" in res.output
    assert res.output["sentiment_signal"]["macro_sentiment"] == "positive"
