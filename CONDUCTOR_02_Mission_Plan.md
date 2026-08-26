# CONDUCTOR — Mission Plan (Component-Level)

**Document ID:** CND-MP-v1.0
**Status:** Draft for review
**Date:** 2026-08-25
**Scope note:** This is the component-level mission plan for Conductor (#6) alone. It is a companion to — not a replacement for — the umbrella *Career & Life Trajectory Mission Plan, v1.5*. Where the two overlap (Phase 3 readiness, the Phase 5 business reframe), this document is the operational detail; the umbrella plan is the strategic frame.

---

## 1. Mission Statement

Orchestrate the existing specialist agents — Harvester, AlignResume, Overture, and eventually the full ten-component architecture — into one coherent, observable, fault-tolerant pipeline, so that "run a job search" becomes a single triggered workflow with a persisted, inspectable record, rather than a sequence of manually-timed, disconnected actions.

## 2. Why Conductor, Why Now

Per the umbrella Mission Plan §13, this is not a portfolio-completion task sitting alongside the real business goal. It **is** the real business goal — "AI Automation / Agentic Orchestration" — built at prototype scale, years ahead of the formal Phase 5 founding date. Every month Conductor stays unbuilt is a month the most direct evidence of the target Phase 3 competency (agent orchestration) stays absent from the portfolio.

## 3. Scope Phases — Big-Picture Map

Granular tasks live in CND-IMPL; this section is the phase-level shape only.

| Phase | Scope | Depends on |
|---|---|---|
| 0 | This specification suite | `conductor_architecture.md` (done) |
| 1 | Two-agent MVP: AlignResume + Overture against manually-seeded jobs | AlignResume, Overture programmatic interfaces |
| 2 | Harvester integration — full three-agent MVP | Harvester Sprint 1 implementation |
| 3 | Sentiment Classifier + Memory Module feedback loop | Sentiment Classifier v1.0.1 dataset gate cleared; minimal Memory Module store |
| 4 | Research Agent + PDF Auto-Apply Agent — full ten-component orchestration | Both components reaching implementation |
| 5 | Observability and production hardening (Grafana, containerization, K8s scheduling) | DevOps roadmap Phase 7 (Kubernetes) comfort |

## 4. Relationship to Sibling Components

| Component | Current status | What Conductor needs from it |
|---|---|---|
| AlignResume | Complete, deployed | A callable tailoring interface (API or CLI), not just the web UI |
| Harvester (Gleaner) | Full spec suite; implementation not started | A stable output schema (the canonical 7-field format already specced) |
| Overture | Complete, hardened | A callable send interface with a pre-send hook for the human-approval gate (CND-EDGE, category 6) |
| Sentiment Classifier | Implementation complete (v1.0.1); gated on labeled dataset | `ClassifiedSignal` objects as Conductor's outcome-ingestion format |
| Memory Module | Not started | Nothing yet — Conductor defines the interface Memory Module will later implement (ADR-2, CND-ARCH) |
| Future Fit | Complete, deployed | Optional signal only; not a hard dependency for v1 |
| Research Agent | Phase 0 complete | Deferred to Phase 4 |
| PDF Auto-Apply Agent | Not started | Deferred to Phase 4 |
| Candidate Profile JSON | Designed, not implemented as a living store | Conductor is the first real consumer — its shape gets fixed here |

## 5. Definition of Done for v1

Restated from CND-PS §8: Conductor orchestrates at least two of AlignResume, Harvester, and Overture end-to-end against a real or realistic job opportunity, with a persisted, inspectable run record and zero silently dropped state. Given Harvester's current status, the honest v1 target is **AlignResume + Overture**, with Harvester's slot architecturally reserved and stubbed, not skipped.

## 6. Risks at the Mission Level

Full registers live in CND-EVAL (quality risk) and CND-EDGE (operational risk). At the mission level, the one risk worth naming here explicitly: **the same avoidance pattern that delayed Conductor for months could resurface at the phase boundary** — e.g., treating "wait for Harvester to be fully done" as a reason to delay Phase 1, when Phase 1 does not require Harvester at all. The mitigation is structural: Phase 1's exit criteria (CND-IMPL) are written to be achievable with zero Harvester involvement, so there is no legitimate-sounding reason to wait.

## 7. Alignment with the Agentic AI Engineering Roadmap

This component is the named, concrete target of Stage 03 in the umbrella Mission Plan's specialization curriculum (§10.4): the "3-agent system (Researcher + Analyst + Writer) with supervisor handoff" checkpoint is explicitly described there as a "direct precursor to Conductor." Building Conductor now, using the same LangGraph + MCP + multi-agent patterns that checkpoint calls for, means the checkpoint and the real deliverable are the same build — not two separate pieces of work satisfying the same line item by coincidence, but one artifact satisfying both by construction, in the same spirit as the Stage 03/DevOps Phase 14 RAG reconciliation already documented there.
