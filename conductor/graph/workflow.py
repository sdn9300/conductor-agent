"""
LangGraph StateGraph Workflow for Conductor.
Assembles the complete 10-component orchestration graph with dynamic channel routing.
"""

from typing import Optional, Callable
from langgraph.graph import StateGraph, START, END

from conductor.graph.nodes import (
    NodeContext,
    discover_node,
    research_node,
    tailor_node,
    human_gate_node,
    outreach_node,
    auto_apply_node,
    persist_node,
    execute_tier0_baseline,
)
from conductor.state import ConductorState


def route_after_discover(state: ConductorState) -> str:
    """Route after discovery: if duplicate, cooldown, or error -> persist; else -> research."""
    if state.application.status in ("error", "skipped_duplicate", "skipped_cooldown") or state.errors:
        return "persist"
    return "research"


def route_after_research(state: ConductorState) -> str:
    """Route after research: if error -> persist; else -> tailor."""
    if state.application.status in ("error", "skipped_duplicate", "skipped_cooldown") or state.errors:
        return "persist"
    return "tailor"


def route_after_tailor(state: ConductorState) -> str:
    """Route after tailoring: if error -> persist; else -> human_gate."""
    if state.application.status in ("error", "skipped_duplicate", "skipped_cooldown") or state.errors:
        return "persist"
    return "human_gate"


def route_after_human_gate(state: ConductorState) -> str:
    """
    Dynamic Channel Routing (Task 4.3):
    After human gate approval, dynamically routes to Overture cold-email (outreach)
    or PDF Auto-Apply portal submission (auto_apply).
    """
    if state.application.status in ("error", "skipped_duplicate", "skipped_cooldown") or state.errors:
        return "persist"
    if state.human_approval not in ("approve", "edit"):
        return "persist"

    channel = state.target_channel
    if channel == "auto":
        channel = state.application.posting.application_channel

    if channel == "auto":
        posting = state.application.posting
        ats_portal_indicators = [
            "boards.greenhouse.io",
            "jobs.lever.co",
            "myworkdayjobs.com",
            "ashbyhq.com",
            "smartrecruiters.com",
            "icims.com",
        ]
        url = (posting.url or "").lower()

        if any(p in url for p in ats_portal_indicators):
            channel = "form"
        else:
            channel = "email"

    if channel == "form":
        return "auto_apply"
    return "outreach"


def build_conductor_graph(context: Optional[NodeContext] = None) -> StateGraph:
    """Construct and compile the full 10-component Conductor LangGraph state machine."""
    ctx = context or NodeContext()

    workflow = StateGraph(ConductorState)

    # Add Nodes
    workflow.add_node("discover", lambda s: discover_node(s, ctx))
    workflow.add_node("research", lambda s: research_node(s, ctx))
    workflow.add_node("tailor", lambda s: tailor_node(s, ctx))
    workflow.add_node("human_gate", lambda s: human_gate_node(s, ctx))
    workflow.add_node("outreach", lambda s: outreach_node(s, ctx))
    workflow.add_node("auto_apply", lambda s: auto_apply_node(s, ctx))
    workflow.add_node("persist", lambda s: persist_node(s, ctx))

    # Add Edges & Conditional Routing
    workflow.add_edge(START, "discover")
    workflow.add_conditional_edges(
        "discover",
        route_after_discover,
        {"research": "research", "persist": "persist"}
    )
    workflow.add_conditional_edges(
        "research",
        route_after_research,
        {"tailor": "tailor", "persist": "persist"}
    )
    workflow.add_conditional_edges(
        "tailor",
        route_after_tailor,
        {"human_gate": "human_gate", "persist": "persist"}
    )
    workflow.add_conditional_edges(
        "human_gate",
        route_after_human_gate,
        {"outreach": "outreach", "auto_apply": "auto_apply", "persist": "persist"}
    )
    workflow.add_edge("outreach", "persist")
    workflow.add_edge("auto_apply", "persist")
    workflow.add_edge("persist", END)

    return workflow.compile()
