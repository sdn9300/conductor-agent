# CONDUCTOR — Evaluation Plan

**Document ID:** CND-EVAL-v1.0
**Status:** Draft for review
**Date:** 2026-08-25

---

## 1. Evaluation Philosophy

Conductor has two separable axes of "working," and conflating them produces false confidence:

- **Orchestration correctness** — did it call the right agents, in the right order, with the right state, and record what happened? This is testable deterministically, independent of whether any given job application succeeds.
- **Outcome value** — did it actually help land interviews? This is a slow, noisy, real-world signal that cannot be gated on before shipping v1, only tracked over time.

v1 acceptance is judged entirely on orchestration correctness. Outcome value is monitored, never blocking.

## 2. Hard-Blocking Gates (Must Pass — Tier 1)

These gate a phase transition in CND-IMPL. Failure here means the phase is not done, regardless of how much else works.

| Gate | Requirement |
|---|---|
| Zero silent drops | Across 10 consecutive test runs including at least 2 deliberately induced failures (e.g., a mocked AlignResume timeout), every run produces a persisted state record — none simply vanish |
| Schema validation | Every write to the Candidate Profile JSON validates against the v0.1 schema (CND-ARCH §3.1) before persisting; invalid writes are rejected and logged, not silently coerced |
| Human gate enforcement | Overture's send adapter cannot be reached by the graph without first passing through the approval node (ADR-6) — verified by a test that attempts to bypass the gate and confirms it is structurally impossible, not just discouraged |
| Graceful degradation | A failure in any single `AgentAdapter` (simulated) does not crash the graph process; the run halts at a resumable checkpoint with a logged reason |
| MVP orchestration proof | At least two of AlignResume, Gleaner, Overture are demonstrably chained end-to-end on a real or realistic posting, per CND-PS §8 |

## 3. Monitoring Metrics (Tracked, Not Blocking — Tier 2)

| Metric | Why it's tracked |
|---|---|
| End-to-end run latency | Surfaces whether MCP-wrapped calls (ADR-3) become a bottleneck as volume grows |
| Groq token cost per run | Keeps the system inside free-tier constraints already load-bearing elsewhere in the portfolio |
| Outreach → response rate | The first real signal of outcome value, once Phase 3's feedback loop is live |
| Sentiment signal distribution over time | Whether "approved" outcomes trend up as the system accumulates history — the actual point of the Memory feedback loop |
| Human-gate approval vs. edit vs. reject rate | If the gate is rejecting or editing most tailored resumes, that is a signal AlignResume's tailoring quality — not Conductor's orchestration — needs attention |

## 4. Test Strategy

Consistent with the pytest-first pattern already established for Overture:

- **Unit tests per adapter** — each `AgentAdapter` tested in isolation against a mocked upstream (mocked AlignResume response, mocked Overture send confirmation, mocked Gleaner posting).
- **Integration test for the full graph** — one staged, end-to-end run against a fixture job posting, asserting the final persisted record matches the expected shape at every intermediate status transition (`discovered → tailored → outreach_pending_review → outreach_sent`).
- **Failure-injection tests** — deliberately fail each adapter in turn and assert ADR-4's no-silent-drop guarantee holds in every case, not just the happy path.

## 5. Acceptance Checklist — "Conductor v1 Done"

Operationalizing CND-PS §8 as a literal checklist:

- [ ] AlignResume and Overture adapters both pass their unit tests
- [ ] Full graph integration test passes against a fixture posting
- [ ] All Tier 1 hard-blocking gates (§2 above) pass
- [ ] A complete run record exists and is human-readable without needing to read the code
- [ ] The human-approval gate has been exercised at least once with a real (not mocked) tailored resume
- [ ] Prometheus metrics under the `conductor_*` namespace are visible and non-zero after a real run
