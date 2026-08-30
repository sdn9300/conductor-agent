# CONDUCTOR_08 — Integration Implementation Plan

**Implements:** CONDUCTOR_07_Integration_Architecture_Design.md
**Gate/ADR numbering continues Conductor's own convention** (ADR-1…6 already in use; this plan adds ADR-7…9 and a new set of integration gates, IG-#).

---

## 0. Sequencing Rationale

Three integrations, ordered by risk and dependency, not by the order they were named in the request:

1. **Memory Module first** — lowest risk. It's a pure sink (per its own design principle: "never originates actions"), so wiring it in is additive and easy to roll back. It's also the item the Sept–Oct Execution Plan already names for Week 7 (Oct 15–21) — doing it first keeps this plan aligned with the calendar you're already committed to.
2. **Candidate Profile second** — foundational, but touches more call sites (every node that currently reads `master_resume.txt`). Needs Memory Module's event emission points to already exist, since AlignResume/Overture/Usher nodes will emit both a Memory Module event and a Candidate Profile patch at the same point in the graph — doing this after Phase 1 means that pattern only gets written once, not twice.
3. **Usher third** — highest uncertainty (per CONDUCTOR_07 §1) and highest real-world consequence (actual portal submissions). Sequenced last deliberately: by the time this phase starts, the profile-projection and event-emission plumbing already exists and is tested, so Usher's integration is "plug into an existing pattern" rather than "build the pattern and plug in simultaneously."

**Honest scope note:** the Sept–Oct Plan's Week 7 line item names only Memory Module. This plan's Phases 2–3 (Candidate Profile, Usher) are scope beyond that single week. §9 below gives a time estimate against your own stated 10–15 hr/week budget so this can be weighed against what else is already booked into Weeks 7–8 (Sentiment Analysis Agent extension, Future Fit Live Step 2, DL/NLP topics per Sept–Oct Plan §5) rather than assumed to fit silently on top of it.

---

## Phase 0 — Verification (Hard Gate Before Any Code)

Per CONDUCTOR_07 §1, two of the three integrations rest on README-level confidence, not source-level confidence. This phase closes that gap before Phase 1 starts.

**IG-1 (Integration Gate 1): Read Memory Module's actual `src/adapters.py`.** Confirm whether adapter functions exist for `RESUME_TAILORED`, `OUTREACH_SENT`, `APPLICATION_SUBMITTED` beyond the two confirmed (`from_harvester_event`, `from_classified_signal`). If missing, write them — small, additive, same shape as the existing two.

**IG-2: Read Memory Module's actual `src/store.py` and `src/db.py`.** Confirm query methods available for dedup (URL hash / normalized company+title) and cooldown (last rejection date per company). If missing, add them — the SQLite schema almost certainly already indexes what's needed; this is a query-method gap, not a schema gap.

**IG-3: Read Usher's actual `usher/` source.** This is the one that matters most. Confirm: (a) the exact input shape Usher's entry point expects — does it match `to_application_view()` or `to_usher_profile()` from Candidate Profile, or neither; (b) what "4-tier field resolution" actually resolves fields against (its own internal schema? an ATS-specific one per adapter?); (c) whether Usher has its own approval/policy gate that would double up with Conductor's existing ADR-6 gate, and if so, which one should own the check.

**IG-4: Confirm Conductor's abstract `MemoryStore` interface's exact method signatures** (`conductor/storage/base.py`) before writing `EventSourcedMemoryStore` in Phase 1 — CONDUCTOR_07 §4.2's sketch is illustrative, not final, until this is read directly.

**Deliverable:** a short `VERIFICATION_NOTES.md` recording what IG-1 through IG-4 found, committed before Phase 1 begins. If any finding changes the design in CONDUCTOR_07, update that document too — don't let the implementation silently diverge from the design doc it's supposed to implement.

**Estimated time:** 1–2 hours.

---

## Phase 1 — Memory Module Integration

| Task | Detail |
|---|---|
| 1.1 | Add `conductor-memory-module` as a git submodule under `vendor/`; `pip install -e` it (ADR-7) |
| 1.2 | Write `conductor/storage/event_sourced_store.py` implementing Conductor's `MemoryStore` interface (per IG-4), delegating to the standalone `EventLedger` |
| 1.3 | Add the missing adapter functions from IG-1 to `conductor-memory-module` if needed, with their own unit tests in that repo |
| 1.4 | Add the missing query methods from IG-2 if needed |
| 1.5 | Wire event emission into `harvester.py` (`JOB_DISCOVERED`) and `sentiment.py` (`RESPONSE_CLASSIFIED`) — these two are already fully confirmed, so do them first as the proof-of-pattern |
| 1.6 | Wire event emission into `align_resume.py`, `overture.py`, `auto_apply.py` for the remaining three event types |
| 1.7 | Swap Conductor's storage instantiation (wherever `SQLiteMemoryStore`/`JSONMemoryStore` is currently constructed) to `EventSourcedMemoryStore`, behind a config flag (`MEMORY_BACKEND=event_sourced` vs `legacy`) so this is reversible without a git revert |
| 1.8 | Update `conductor history` and `conductor inspect` CLI commands to read from the new store |

**IG-5 (acceptance gate):** `conductor run --dry-run` completes end-to-end with events visible via `memory_cli.py history <app_id>` in the standalone module's own CLI — proof the two systems are actually talking, not just that Conductor's tests pass in isolation.

**Estimated time:** 3–5 hours.

---

## Phase 2 — Candidate Profile Integration

| Task | Detail |
|---|---|
| 2.1 | Add `conductor-candidate-profile` as a git submodule; `pip install -e` it |
| 2.2 | Write the one-time migration script: parse `data/master_resume.txt` → populate a `CandidateProfile` object → `CandidateProfileStore.put()` |
| 2.3 | Add `profile: Annotated[CandidateProfile, merge_candidate_profile]` to `ConductorState` |
| 2.4 | Write `conductor/adapters/candidate_profile.py` wrapping the store + six projection functions |
| 2.5 | Switch `align_resume.py` to `to_resume_profile(profile)`; wire `check_skill_provenance()` into the tailoring step per CONDUCTOR_07 §4.1 |
| 2.6 | Switch `research.py` to `to_research_scope(profile)` |
| 2.7 | Add `CandidateProfilePatch` emission after AlignResume (`tailoring_history`), Overture (`outreach_history`), Sentiment Classifier (`interaction_signals`) — same nodes touched in Phase 1.6, so this is additive to code already open |
| 2.8 | Point Candidate Profile's five Prometheus metrics at Conductor's existing registry (per CONDUCTOR_07 §4.1) rather than standing up a second `/metrics` endpoint |
| 2.9 | Mark `data/master_resume.txt` deprecated in the repo (ADR-9) — don't delete it immediately, but stop reading it |

**IG-6 (acceptance gate):** `check_skill_provenance()` correctly rejects at least one deliberately-fabricated test skill during a dry run — this is the guardrail the whole point of this integration rests on; it needs a positive proof, not just an absence of errors.

**Estimated time:** 4–6 hours.

---

## Phase 3 — Usher / PDF Auto-Apply Integration

Gated entirely on IG-3's findings. Two branches:

**If Usher's expected input matches an existing projection cleanly:**

| Task | Detail |
|---|---|
| 3.1 | Add `conductor-auto-apply` as a git submodule; `pip install -e` it |
| 3.2 | Rewrite `conductor/adapters/auto_apply.py` to call Usher's real entry point with `to_application_view()`/`to_usher_profile()` output |
| 3.3 | Wire `APPLICATION_SUBMITTED` event emission (Phase 1 pattern) and `application_history` patch emission (Phase 2 pattern) on success |
| 3.4 | Reconcile Usher's own policy gate (if one exists per IG-3c) with Conductor's ADR-6 human approval gate — one should own the authorization decision, not both independently |
| 3.5 | Confirm `DRY_RUN` from Conductor's `.env` actually reaches Usher's submission step, not just Conductor's own logic |

**If Usher's expected input doesn't match cleanly:** write a thin translation function in the new adapter rather than modifying either Candidate Profile's projections (used elsewhere) or Usher's own schema (its own well-specified contract) — isolate the mismatch at the integration seam, which is exactly what an adapter layer is for.

**IG-7 (acceptance gate):** one full `conductor run --channel form --dry-run` completes with a real (non-mocked) call into Usher, producing a form-payload artifact that a human could review — the same "prove it's actually wired, not just passing tests in isolation" standard as IG-5.

**Estimated time:** 3–8 hours (wide range reflects the Phase 0 uncertainty this whole phase depends on).

---

## Phase 4 — Integration Testing & the Combined Milestone

| Task | Detail |
|---|---|
| 4.1 | New test file `tests/test_full_integration.py` — one end-to-end `--dry-run` covering all three: discover → tailor (with provenance check) → approve → route → submit/outreach → all three stores updated |
| 4.2 | Extend the existing 47-test suite rather than replacing it — Phases 1–3 should not have broken any existing test; if they did, that's a regression to fix before this phase, not to ship alongside it |
| 4.3 | Update `README.md`'s Component Integration Map to CONDUCTOR_07 §7's version |
| 4.4 | Update the Grafana dashboard JSON to include Candidate Profile's five new metrics alongside Conductor's existing ones |

**Definition of Done for this whole plan:** a single `conductor run --dry-run` exercises real (not stubbed) Memory Module, Candidate Profile, and Usher integrations end-to-end, with all three's own test suites passing independently and the new `test_full_integration.py` passing. This is a stricter bar than "adapter exists in the routing graph" — which was already true before this plan and is exactly the distinction flagged in the execution tracking log.

---

## Rollback Plan

Each phase is behind its own reversibility mechanism:
- Phase 1: `MEMORY_BACKEND` config flag (Task 1.7) — flip back to `legacy` without a code revert.
- Phase 2: `master_resume.txt` isn't deleted until confidence is high (Task 2.9) — the old read path can be restored by reverting one function, not the whole integration.
- Phase 3: gated behind `DRY_RUN` throughout; nothing irreversible (a real portal submission) happens until that's deliberately turned off, separately from this integration work.

---

## Effort Estimate & Fit Against the Sept–Oct Calendar

| Phase | Estimate | Sept–Oct Plan fit |
|---|---|---|
| 0 — Verification | 1–2 hrs | Fits inside Week 7's existing Track B allocation |
| 1 — Memory Module | 3–5 hrs | This is the Week 7 (Oct 15–21) deliverable as originally scoped — fits |
| 2 — Candidate Profile | 4–6 hrs | Not in the original Week 7 scope. Competes with Week 7's Sentiment Analysis Agent extension and Week 8's Future Fit Live Step 2 for the same hours |
| 3 — Usher | 3–8 hrs | Same competition as Phase 2, plus its own uncertainty range |
| 4 — Integration testing | 2–3 hrs | — |
| **Total** | **13–24 hrs** | **More than one week's Track B budget at the stated 10–15 hrs/week pace** |

**Recommendation:** treat Phase 1 as the Week 7 commitment (matches the existing plan exactly). Phases 2–4 are real, worthwhile scope, but calling them a Week 7 add-on rather than their own allocation risks the same pattern already flagged elsewhere in this log — a plan that looks complete on paper because it's thorough, not because the hours actually exist. If they matter enough to prioritize now, something else in Week 7–8's Track B/C queue should be named as what slips, rather than assuming both fit.

---

## Task Checklist (copy into Sept–Oct Plan Week 7–8 tracking, or the execution log, once scheduled)

- [ ] Phase 0: VERIFICATION_NOTES.md committed, CONDUCTOR_07 updated if findings diverge from its assumptions
- [ ] Phase 1: `EventSourcedMemoryStore` live, IG-5 passed
- [ ] Phase 2: `CandidateProfile` wired into state, IG-6 passed, `master_resume.txt` deprecated
- [ ] Phase 3: Usher wired, IG-7 passed
- [ ] Phase 4: `test_full_integration.py` passing, README + Grafana updated
- [ ] Definition of Done met: single `--dry-run` exercises all three, real not stubbed
