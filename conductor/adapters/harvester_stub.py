"""
Harvester Stub Adapter for Phase 1.
Ingests manually seeded job descriptions while architecturally reserving Harvester's slot (CND-IMPL §Phase 1).
"""

import time
from typing import Any, Dict, Optional
from conductor.adapters.base import AgentAdapter, AgentResult
from conductor.state import PostingRef


class HarvesterStubAdapter(AgentAdapter):
    """Stub adapter substituting for Harvester until Phase 2."""

    @property
    def name(self) -> str:
        return "harvester_stub"

    def invoke(self, state_dict: Dict[str, Any]) -> AgentResult:
        start_time = time.time()
        try:
            # Check if seed posting exists in state
            app = state_dict.get("application")
            posting = None

            if app:
                if isinstance(app, dict):
                    posting = app.get("posting")
                else:
                    posting = getattr(app, "posting", None)

            if not posting:
                # Check top-level seed_posting or metadata
                posting = state_dict.get("seed_posting") or state_dict.get("metadata", {}).get("seed_posting")

            if not posting:
                return AgentResult(
                    success=False,
                    error="No seed job posting provided to HarvesterStubAdapter (EC-04).",
                    latency_ms=(time.time() - start_time) * 1000,
                )

            # Validate / normalize
            if isinstance(posting, dict):
                posting_obj = PostingRef.model_validate(posting)
            elif isinstance(posting, PostingRef):
                posting_obj = posting
            else:
                return AgentResult(
                    success=False,
                    error="Malformed posting object provided.",
                    latency_ms=(time.time() - start_time) * 1000,
                )

            return AgentResult(
                success=True,
                output={"posting": posting_obj.model_dump()},
                latency_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            return AgentResult(
                success=False,
                error=f"HarvesterStubAdapter error: {str(e)}",
                latency_ms=(time.time() - start_time) * 1000,
            )

    def health_check(self) -> bool:
        return True
