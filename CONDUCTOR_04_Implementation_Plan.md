# CONDUCTOR — Phase-Wise Implementation Plan

**Document ID:** CND-IMPL-v1.0
**Status:** Draft for review
**Date:** 2026-08-25
**Reads against:** CND-ARCH-v1.0 (all ADR references below are defined there)

---

## Phase 0 — Foundations (Complete)

| Deliverable | Status |
|---|---|
| `conductor_architecture.md` | Done |
| CND-PS, CND-MP, CND-ARCH, CND-IMPL, CND-EVAL, CND-EDGE | Done (this document set) |

**Exit criterion:** All six documents exist and are internally consistent. Met.

---

## Phase 1 — Two-Agent MVP (AlignResume + Overture, manually-seeded jobs)

No dependency on Gleaner's implementation — this phase is fully buildable today.

| Task | Detail |
|---|---|
| 1.1 | Confirm/build a programmatic interface to AlignResume (API endpoint or CLI wrapper around the existing Next.js deployment) |
| 1.2 | Confirm/build a programmatic interface to Overture's send pipeline |
| 1.3 | Define and implement the `ConductorState` object and the minimal Candidate Profile JSON schema (CND-ARCH §3.1–3.2) |
| 1.4 | Implement `AgentAdapter` base interface + `AlignResumeAdapter` + `OvertureAdapter` (ADR-3 for AlignResume specifically: MCP wrapper) |
| 1.5 | Build the LangGraph topology for the Tier-1 loop with Gleaner replaced by a manual-input stub node (accepts a hand-supplied JD) |
| 1.6 | Implement the human-approval gate node (ADR-6) between tailoring and send |
| 1.7 | Implement the local `MemoryStore` (ADR-2): append-only JSON or SQLite run log |
| 1.8 | Wire minimal Prometheus metrics under the `conductor_*` namespace (ADR-5) |

**Exit criterion:** Given a manually supplied job posting, Conductor produces a tailored resume, holds for human approval, sends via Overture on approval, and writes a complete, inspectable run record with zero unhandled exceptions across 10 consecutive manual test runs.

---

## Phase 2 — Gleaner Integration (Full Three-Agent MVP)

Gated on Gleaner's Sprint 1 implementation landing.

| Task | Detail |
|---|---|
| 2.1 | Implement `HarvesterAdapter` against Gleaner's already-specced 7-field canonical schema |
| 2.2 | Replace the Phase 1 manual-input stub with the real Gleaner node in the Tier-1 loop |
| 2.3 | Implement Tier-0 baseline pass (ADR-1) as an independently schedulable node, decoupled from the per-job loop |
| 2.4 | Add deduplication logic at the Conductor level — skip postings Gleaner has already surfaced and Conductor has already processed (cross-reference against the run log) |

**Exit criterion:** Conductor's Tier-1 loop runs unmodified from live Gleaner output through to a sent (or gated) outreach, satisfying the umbrella Mission Plan's pinned MVP criterion in full — all three of AlignResume, Gleaner, and Overture orchestrated end-to-end.

---

## Phase 3 — Sentiment Classifier + Memory Feedback Loop

Gated on Sentiment Classifier clearing its own Phase 1 labeled-dataset gate.

| Task | Detail |
|---|---|
| 3.1 | Implement `SentimentClassifierAdapter`, ingesting `ClassifiedSignal` objects as Conductor's outcome format |
| 3.2 | Extend the Candidate Profile JSON schema with the `sentiment_signal` field (already present in the v0.1 draft schema, CND-ARCH §3.1) |
| 3.3 | Add a feedback rule: a `rejected` or `closed` signal on a company suppresses future outreach to that same company for a configurable cooldown period |
| 3.4 | Migrate the local `MemoryStore` (ADR-2) toward the real Memory Module's eventual interface, or integrate directly if Memory Module has shipped by this point |

**Exit criterion:** A simulated "rejected" signal on a test company measurably changes Conductor's next-run behavior (suppressed re-outreach), proving the feedback loop is live, not cosmetic.

---

## Phase 4 — Full Ten-Component Orchestration

| Task | Detail |
|---|---|
| 4.1 | Implement `ResearchAgentAdapter` — inserted between Gleaner and AlignResume, enriching the JD with company intelligence before tailoring |
| 4.2 | Implement `PDFAutoApplyAdapter` — inserted as an alternative branch to Overture for postings that require an application form rather than a cold email |
| 4.3 | Extend the graph with a routing node deciding Overture-path vs. PDF-Auto-Apply-path per posting |

**Exit criterion:** All ten components are reachable from a single Conductor trigger; the routing decision (email vs. form) is made automatically per posting type.

---

## Phase 5 — Observability and Production Hardening

| Task | Detail |
|---|---|
| 5.1 | Grafana dashboards on top of the unified Prometheus instance (DevOps roadmap Phase 10) |
| 5.2 | Containerize each `AgentAdapter` per the multi-stage Docker pattern already used for Overture |
| 5.3 | Migrate scheduling to Kubernetes Jobs/Deployments once DevOps roadmap Phase 7 comfort is reached, informed by the Minikube work already completed |

**Exit criterion:** Conductor runs as a scheduled, monitored, containerized system rather than a manually triggered local script — matching the "running on real infrastructure, not just local scripts" bar set in the umbrella Mission Plan's 12-month checkpoint.

---

## Cross-Phase Note

Phases 1 and 2 are deliberately decoupled so that Gleaner's implementation timeline never blocks Conductor's own progress. This is the direct, structural fix for the avoidance pattern named in CND-MP §6 — there is no phase boundary here that requires waiting on something outside Conductor's own control before Phase 1 can start.
