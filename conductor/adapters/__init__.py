from conductor.adapters.base import AgentAdapter, AgentResult
from conductor.adapters.gleaner import GleanerAdapter, HarvesterAdapter
from conductor.adapters.harvester_stub import HarvesterStubAdapter
from conductor.adapters.research import ResearchAgentAdapter
from conductor.adapters.align_resume import AlignResumeAdapter
from conductor.adapters.overture import OvertureAdapter
from conductor.adapters.auto_apply import PDFAutoApplyAdapter
from conductor.adapters.sentiment import SentimentClassifierAdapter

GleanerStubAdapter = HarvesterStubAdapter

__all__ = [
    "AgentAdapter",
    "AgentResult",
    "GleanerAdapter",
    "HarvesterAdapter",
    "GleanerStubAdapter",
    "HarvesterStubAdapter",
    "ResearchAgentAdapter",
    "AlignResumeAdapter",
    "OvertureAdapter",
    "PDFAutoApplyAdapter",
    "SentimentClassifierAdapter",
]
