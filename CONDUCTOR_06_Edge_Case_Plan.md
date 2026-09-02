# CONDUCTOR — Edge Case Plan

**Document ID:** CND-EDGE-v1.0
**Status:** Draft for review
**Date:** 2026-08-25

---

## Registry

| ID | Category | Scenario | Likelihood | Impact | Handling |
|---|---|---|---|---|---|
| EC-01 | Upstream failure | AlignResume's endpoint times out mid-tailoring | Medium | Medium | `AgentAdapter` returns `AgentResult(success=False)`; graph halts at a resumable checkpoint (ADR-4); retried on next trigger, not silently abandoned |
| EC-02 | Upstream failure | Overture's Gmail OAuth token expires mid-send | Low | High | Adapter detects the auth error specifically (distinct from a generic failure), halts before any partial send, surfaces a clear re-auth prompt rather than a stack trace |
| EC-03 | Upstream failure | Gleaner returns zero postings for a run | High (expected, not exceptional) | Low | Not an error — the graph completes normally with an empty Tier-1 loop; this is the routine "no new opportunities today" path, distinct from EC-01 |
| EC-04 | Schema | A hand-supplied JD (Phase 1 manual-input stub) is malformed or empty | Medium | Low | Validated at the stub node before entering the graph; rejected with a specific error, never passed downstream as if valid |
| EC-05 | Schema | Candidate Profile JSON write fails validation | Low | High | Write rejected, not coerced; failure logged with the specific field that failed, per CND-EVAL §2 |
| EC-06 | Duplicate / re-entrancy | The same posting is discovered twice across two Gleaner runs | Medium | Medium | Deduplication check against the persisted run log (CND-IMPL Task 2.4) before entering the Tier-1 loop a second time |
| EC-07 | Duplicate / re-entrancy | A company already marked `rejected` by Sentiment Classifier resurfaces via a different posting | Medium | Medium | Company-level cooldown suppression (CND-IMPL Task 3.3), independent of the specific posting ID |
| EC-08 | Rate limit / cost | Groq free-tier limit is hit mid-run | Medium | Medium | Adapter-level backoff consistent with the rate-limit-aware pattern already used elsewhere in the portfolio; run pauses and resumes rather than failing outright |
| EC-09 | Rate limit / cost | A single run's cost estimate (from `AgentResult.cost_estimate`) exceeds a configured threshold | Low | Medium | Run halts before the expensive step (typically outreach) and requires explicit approval to proceed — cost overruns are visible before they happen, not after |
| EC-10 | Partial completion | The Conductor process crashes between the tailoring and send steps | Low | High | Because state is persisted at every node boundary (ADR-4), the next trigger resumes from the last completed step rather than restarting the whole job from discovery |
| EC-11 | Partial completion | A run is manually interrupted while awaiting human approval | High (expected) | Low | This is not a failure state — the run sits indefinitely at the approval gate; no timeout auto-rejects or auto-sends it |
| EC-12 | Human-in-the-loop | The candidate rejects a tailored resume at the approval gate | High (expected) | Low | Rejection routes back to AlignResume with the rejection reason attached, not simply discarded — this is the same feedback discipline as ADR-4 applied to a human decision instead of an agent failure |
| EC-13 | Human-in-the-loop | The temptation to remove the approval gate entirely for speed, once the system "feels reliable" | Medium (behavioral, not technical) | High | Named explicitly here because it is the most likely edge case to be dismissed as unnecessary caution. Per ADR-6, removing the gate is a distinct, separately-evaluated architectural decision requiring its own ADR — not a default that erodes quietly through convenience |

## Note on Category 6 (Human-in-the-Loop)

This category exists because Overture sends real email, under the candidate's real identity, to real recruiters. AlignResume already treats unreviewed LLM output as a reputational risk serious enough to warrant a dedicated guardrail layer before export. Conductor extends that same judgment to outbound communication, rather than treating orchestration automation as a reason to relax it. EC-13 is listed with "High" impact specifically because it is the one edge case most likely to be removed through gradual convenience rather than a deliberate decision — naming it here is the safeguard against that.
