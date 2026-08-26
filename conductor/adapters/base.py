"""
Base AgentAdapter and AgentResult abstractions.
Implements CND-ARCH §3.3 unified contract across all specialist agents.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class AgentResult:
    """Standardized response from any AgentAdapter.invoke() call."""
    success: bool
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None  # Populated even on partial success / failure
    cost_estimate: Optional[float] = 0.0
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentAdapter(ABC):
    """Abstract interface for all sibling agent adapters."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Identifier name of the agent component."""
        pass

    @abstractmethod
    def invoke(self, state_dict: Dict[str, Any]) -> AgentResult:
        """
        Execute the agent logic given the current state dictionary.
        Must NEVER raise an unhandled exception to the caller (ADR-4 No-Silent-Drop).
        Always returns an AgentResult with success=False on failure.
        """
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check whether the downstream service/environment is available."""
        pass
