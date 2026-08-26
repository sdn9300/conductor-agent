"""
Sentiment Classifier Adapter.
Interfaces with Sentiment Classifier (#9) to categorize inbound recruiter/company responses.
Implements ADR-4, Task 3.1, and EC-07.
"""

import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from conductor.adapters.base import AgentAdapter, AgentResult
from conductor.config import config
from conductor.state import SentimentSignal

logger = logging.getLogger(__name__)


class SentimentClassifierAdapter(AgentAdapter):
    """Adapter for wrapping Sentiment Classifier (#9)."""

    def __init__(self, sentiment_dir: Optional[str] = None):
        self.sentiment_dir = Path(sentiment_dir or config.SENTIMENT_CLASSIFIER_DIR)
        self._setup_path()

    def _setup_path(self) -> None:
        """Add Sentiment-Analysis directory to sys.path to enable module imports."""
        if self.sentiment_dir.exists() and str(self.sentiment_dir) not in sys.path:
            sys.path.insert(0, str(self.sentiment_dir))

    @property
    def name(self) -> str:
        return "sentiment_classifier"

    def classify_response(
        self,
        raw_text: str,
        company: str,
        role: str = "AI Engineer",
        application_id: Optional[str] = None,
        source: str = "overture_email",
    ) -> SentimentSignal:
        """
        Classify inbound text response using Sentiment Classifier or rule-based fallback.
        """
        resp_id = f"resp_{uuid4().hex[:8]}"
        app_id = application_id or f"app_{uuid4().hex[:8]}"

        try:
            from sentiment_classifier.schemas import IncomingResponse
            from sentiment_classifier.classify import classify

            inc_resp = IncomingResponse(
                response_id=resp_id,
                source=source if source in ("overture_email", "job_board", "linkedin", "manual") else "manual", # type: ignore
                company=company,
                role=role,
                raw_text=raw_text,
                received_at=datetime.now(timezone.utc),
                application_id=app_id,
            )

            classified = classify(inc_resp)

            # If LLM failed or returned low confidence unclear fallback, enhance with deterministic rules
            if classified.confidence == 0.0 or classified.classifier_route == "error" or classified.intent_label == "unclear":
                logger.info("Sentiment Classifier returned unconfident signal, falling back to deterministic classifier.")
                return self._fallback_classifier(raw_text, company, resp_id)

            return SentimentSignal(
                response_id=classified.response_id,
                macro_sentiment=classified.macro_sentiment,
                intent_label=classified.intent_label,
                urgency_score=classified.urgency_score,
                confidence=classified.confidence,
                recommended_action=classified.recommended_action,
                key_phrases=classified.key_phrases,
                requires_manual_review=classified.requires_manual_review,
                flagged_for_conductor=classified.flagged_for_conductor,
                raw_response=raw_text,
                classified_at=classified.classified_at.isoformat(),
            )

        except Exception as e:
            logger.warning("Sentiment Classifier module execution failed (%s), using deterministic classifier fallback.", e)
            return self._fallback_classifier(raw_text, company, resp_id)

    def _fallback_classifier(self, raw_text: str, company: str, resp_id: str) -> SentimentSignal:
        """Deterministic pattern matching when sentiment_classifier module or LLM is offline."""
        text_lower = raw_text.lower()

        # 1. Positive Interview / Scheduling Patterns
        interview_keywords = [
            "interview", "schedule a call", "calendly", "cal.com", "chat next week",
            "discuss your background", "availability", "speak with you", "introductory call",
            "phone screen", "technical interview", "short call"
        ]
        if any(w in text_lower for w in interview_keywords):
            return SentimentSignal(
                response_id=resp_id,
                macro_sentiment="positive",
                intent_label="interview_invite",
                urgency_score=5,
                confidence=0.98,
                recommended_action=f"High urgency: Reply to {company} immediately with available interview times.",
                key_phrases=[w for w in interview_keywords if w in text_lower],
                raw_response=raw_text,
            )

        # 2. Negative Soft / Hard Rejection Patterns
        rejection_keywords = [
            "pursue other candidates", "not moving forward", "unfortunately", "declined",
            "position has been filled", "not selected", "decided not to proceed",
            "move forward with other", "other applicants", "competitive applicant pool"
        ]
        if any(w in text_lower for w in rejection_keywords):
            is_soft = any(w in text_lower for w in ["future", "keep your resume", "on file", "touch with you in the future"])
            return SentimentSignal(
                response_id=resp_id,
                macro_sentiment="negative",
                intent_label="soft_rejection" if is_soft else "hard_rejection",
                urgency_score=1,
                confidence=0.95,
                recommended_action=f"Acknowledge rejection and suppress future outreach to {company} during cooldown period.",
                key_phrases=[w for w in rejection_keywords if w in text_lower],
                raw_response=raw_text,
            )

        # 3. Default Neutral / Under review
        return SentimentSignal(
            response_id=resp_id,
            macro_sentiment="neutral",
            intent_label="under_review",
            urgency_score=3,
            confidence=0.80,
            recommended_action=f"Application acknowledged by {company}. Awaiting technical screening decision.",
            raw_response=raw_text,
        )

    def invoke(self, state_dict: Dict[str, Any]) -> AgentResult:
        start_time = time.time()
        try:
            raw_text = state_dict.get("raw_text") or state_dict.get("metadata", {}).get("inbound_text")
            company = state_dict.get("company") or state_dict.get("application", {}).get("posting", {}).get("company", "Unknown")
            role = state_dict.get("role") or state_dict.get("application", {}).get("posting", {}).get("title", "AI Engineer")
            app_id = state_dict.get("job_id") or state_dict.get("application", {}).get("job_id")

            if not raw_text:
                return AgentResult(
                    success=False,
                    error="No raw inbound response text provided to classify.",
                    latency_ms=(time.time() - start_time) * 1000,
                )

            signal = self.classify_response(
                raw_text=raw_text,
                company=company,
                role=role,
                application_id=app_id,
            )

            return AgentResult(
                success=True,
                output={"sentiment_signal": signal.model_dump()},
                latency_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            return AgentResult(
                success=False,
                error=f"SentimentClassifierAdapter error: {str(e)}",
                latency_ms=(time.time() - start_time) * 1000,
            )

    def health_check(self) -> bool:
        return self.sentiment_dir.exists()
