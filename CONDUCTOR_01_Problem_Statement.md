# CONDUCTOR — Problem Statement

**Document ID:** CND-PS-v1.0
**Component:** #6 — Coordination Layer, AI-Native Job Agent Architecture
**Status:** Draft for review
**Author:** Soumyadeep Nath (AI-assisted drafting per Spec-Driven Development)
**Date:** 2026-08-25
**Companion documents:** CND-MP (Mission Plan), CND-ARCH (Architecture Design), CND-IMPL (Implementation Plan), CND-EVAL (Evaluation Plan), CND-EDGE (Edge Case Plan)

---

## 1. Purpose of This Document

This document defines *what problem Conductor solves* and *what "solved" means*, before any architecture or code exists. Per the constitution phase of this project's Spec-Driven Development lifecycle, this is the source-of-truth statement that every downstream document is accountable to.

## 2. Background

Four of the nine sibling components in the AI-Native Job Agent Architecture are complete or substantially built: AlignResume (deployed), Future Fit (deployed), Overture (built and hardened), and Sentiment Classifier (implementation complete at v1.0.1, gated only on a labeled evaluation dataset). Harvester has a full six-document planning suite but no implementation yet. Research Agent has cleared Phase 0. Memory Module, PDF Auto-Apply Agent, and Candidate Profile JSON remain unbuilt or only partially designed.

Each of these is, individually, a strong and independently defensible piece of engineering. None of them talks to any of the others. Running a real job search today means manually invoking AlignResume for one posting, manually feeding company names into Gleaner-era scripts, manually deciding when to send an Overture email, and manually reading whatever Sentiment Classifier reports back — with no persisted record connecting a specific resume, to a specific posting, to a specific outreach, to a specific outcome.

In the candidate's own framing: every other agent in this system is a specialist. Conductor is the one component whose entire job is to turn N independent specialists into one system.

## 3. The Problem, Precisely Stated

This is a **multi-agent coordination problem**, not a missing-feature problem. The individual agents are not the gap. The gap is the absence of:

| Missing element | Consequence of its absence |
|---|---|
| Shared state | No single record of what has and hasn't been done for a given job opportunity |
| Control flow | Agent invocation order is decided ad hoc, by memory, each time |
| Failure semantics | A stalled or errored agent call has no defined fallback — work is silently lost |
| A trigger boundary | "Run a job search" is not a single action; it is a sequence of separate, manually-timed actions |
| Outcome feedback | Sentiment Classifier's signals do not currently change what the system does next |

## 4. Why This Matters Now

Three independent reasons converge on the same conclusion:

1. **It is the pinned MVP gate.** Per Mission Plan v1.5 §14, "Conductor" is not "done" until it demonstrably orchestrates at least two of the three core agents (AlignResume, Harvester, Overture) end-to-end. Phase 3 (AI/Agentic Engineer) readiness is measured against this, not against any other component.
2. **It is the Phase 5 business prototype, not a portfolio checkbox.** Per Mission Plan v1.5 §13, "AI Automation / Agentic Orchestration" is both the long-term business category and the literal technical function of this component, at a different scale. Building it well now is building the actual business early.
3. **It has a documented avoidance pattern.** Per Mission Plan v1.5 §13–14, Conductor has been deferred for months behind a rotating set of legitimate-sounding prerequisites (LangChain, then Linux, then Docker, then Kubernetes). The three-question unlock in `conductor_architecture.md` breaks that pattern. This document set exists to make sure the break holds.

## 5. Goals (In Scope for v1)

- Deterministically orchestrate the sequence: discover or receive a posting → tailor a resume against it → send outreach → capture and classify whatever comes back.
- Maintain one persisted, inspectable state object per job opportunity, from discovery through outcome.
- Fail loud and recoverable, never silent — every node either succeeds, degrades with a logged reason, or halts with a resumable checkpoint.
- Be runnable end-to-end against **two** of the three core agents (AlignResume, Overture) without requiring Harvester to exist in code yet, since it currently doesn't.
- Establish the Candidate Profile JSON as the canonical shared-state schema other components (starting with Memory Module) will consume.

## 6. Non-Goals (Explicitly Out of Scope for v1)

- Full ten-agent orchestration (Research Agent and PDF Auto-Apply Agent integrate in later phases — see CND-IMPL).
- A production Memory Module with semantic search or long-term reasoning — v1 needs a durable store, not an intelligent one.
- Kubernetes deployment. Per Mission Plan v1.5 §9, K8s *informs* Conductor's design (scheduling, health-checking, restart semantics) but is not a build blocker for the MVP.
- Multi-tenant or multi-user operation. This is a single-candidate system.
- Fully autonomous email dispatch with zero human checkpoint (see CND-EDGE, category 6).

## 7. Stakeholders

| Stakeholder | Interest |
|---|---|
| Soumyadeep Nath (primary/sole user) | A working pipeline that reduces manual coordination overhead in an active job search |
| Future interview panels | Conductor is the single piece of evidence that most directly demonstrates agent orchestration, the named core competency of the target AI/Agentic Engineer role |
| Sibling components (AlignResume, Harvester, Overture, Sentiment Classifier, Memory Module) | Conductor is their first real consumer; its interface contracts become the de facto integration standard for the rest of the architecture |

## 8. Success Definition

Conductor v1 is done when it satisfies the pinned criterion from Mission Plan v1.5 §14, restated precisely: **Conductor successfully orchestrates at least two of the three existing agents (AlignResume, Harvester, Overture) against a real or realistic job opportunity, producing a persisted, inspectable run record, with no silently dropped state.** Full operationalized acceptance criteria are in CND-EVAL.

## 9. Assumptions and Dependencies

- AlignResume and Overture expose or can be made to expose a programmatically callable interface (not only a browser UI). This is a working assumption to be verified in CND-IMPL Phase 1, not yet confirmed.
- Harvester's implementation, when it lands, will honor its own six-document spec (canonical 7-field schema, abstract adapter pattern) closely enough that Conductor's Harvester-adapter can be written against that spec now, ahead of Harvester's code.
- Groq API rate limits and free-tier constraints (already load-bearing in AlignResume, Overture, Sentiment Classifier) apply equally to any LLM calls Conductor itself makes or routes.
- Memory Module does not need to exist as a finished component for Conductor v1 — see ADR-2 in CND-ARCH.

## 10. Out-of-Scope Exclusions List

Explicitly deferred, not forgotten: Research Agent integration, PDF Auto-Apply integration, full Candidate Profile JSON schema finalization across all ten agents, Kubernetes-based scheduling, multi-user support, and any UI beyond structured logs and run summaries.
