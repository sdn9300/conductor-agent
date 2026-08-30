# CONDUCTOR_07 — Integration Architecture Design

**Scope:** Wiring Memory Module (#8), Candidate Profile (#10), and Usher / PDF Auto-Apply (#7) into the Conductor orchestrator (#6).
**Continues:** CONDUCTOR_01–06 (existing conductor-agent repo).
**Status:** Design — not yet implemented. See CONDUCTOR_08 for the phased build plan.

---

## 0. Purpose & Scope

Conductor currently runs with three self-contained, in-repo implementations standing in for components that now exist as their own, more capable standalone packages:

| In Conductor today | Standalone package now available |
|---|---|
| `conductor/state.py` → `ConductorState` + `data/master_resume.txt` | `candidate_profile` (conductor-candidate-profile) |
| `conductor/storage/local_store.py` → `SQLiteMemoryStore`/`JSONMemoryStore` | `conductor-memory-module`'s event-sourced `MemoryStore` |
| `conductor/adapters/auto_apply.py` (stub-level) | `usher` (conductor-auto-apply) |

This document designs how the three standalone packages actually get consumed by Conductor's LangGraph state machine, without a rewrite of the graph itself. CONDUCTOR_08 sequences the build.

## 1. Source-Confidence Table

Not all three integrations rest on the same quality of evidence. Stated plainly so the implementation plan doesn't treat a README description and a verified function signature as the same thing.

| # | Source | Confidence | Basis | What this means for the design below |
|---|---|---|---|---|
| 1 | `candidate_profile` package surface | **High** | Actual function signatures, class names, and a worked LangGraph code sample seen directly in the repo's README | §4.1 can specify exact calls |
| 2 | `conductor-memory-module` package surface | **High for what's shown, gap for what isn't** | `MemoryStore`, `record_event()`, `get_application()`, `get_stale_applications()`, `rebuild_derived_state()`, and two adapter functions (`from_harvester_event`, `from_classified_signal`) confirmed directly. No adapter function confirmed for `RESUME_TAILORED`, `OUTREACH_SENT`, or `APPLICATION_SUBMITTED` events, and no confirmed query method for dedup-by-URL-hash | §4.2 flags one concrete gap to close before or during implementation |
| 3 | `usher` package internals | **Low** | Only the "About" description ("Policy-Gated PDF Auto-Apply Agent with 4-Tier Field Resolution & Multi-ATS Adapters") and file/folder names (`usher/`, `tests/`, `fixtures/`) — no README, only 1 commit | §4.3 proposes a shape, not a spec, and Implementation Plan Phase 0 makes reading the actual source a hard prerequisite |
| 4 | Conductor's own internals | **High** | Full README with architecture diagram, file tree, ADRs, and CLI reference read directly | Baseline in §2 is reliable |

## 2. Current State — What Conductor Does Today

For reference, unchanged by this design:

```
Harvester → Dedup → Cooldown → Research Agent → AlignResume → Human Approval Gate
   → Dynamic Channel Routing → (Overture | PDF Auto-Apply) → MemoryStore checkpoint → Prometheus
```

- State carried as `ConductorState` (Pydantic v2, in `conductor/state.py`).
- Candidate data read from a flat `data/master_resume.txt`.
- Dedup/cooldown/checkpointing read and write `conductor/storage/local_store.py`'s SQLite or JSON store, behind the abstract `MemoryStore` interface in `conductor/storage/base.py` (ADR-2: pluggable storage was already a stated design goal).
- `auto_apply.py` exists as an adapter slot in the routing graph; its current internal logic is not confirmed by anything read so far.

The pluggable-storage ADR already in place (ADR-2) is doing a lot of work for this design — it means Conductor was built expecting its storage layer to be swapped, which is exactly what §4.2 proposes.

## 3. ADR-7 (New): How the Three Sibling Repos Get Consumed

Three options, in order of recommendation:

1. **Git submodule + editable local install** (`git submodule add`, then `pip install -e ./vendor/<name>`). *Recommended.* All three repos are actively evolving, single-author, and small enough that cross-repo edits during integration are likely. Submodules keep each repo's own commit history and README intact (useful — each is independently presentable in a portfolio or interview) while `pip install -e` means a change in the sibling repo is immediately live in Conductor without a republish step.
2. **Pinned pip install from GitHub** (`pip install git+https://github.com/sdn9300/conductor-memory-module.git@<commit>`). Simpler, no submodule bookkeeping, but every edit during integration means re-pinning a commit hash — friction that matters while the interfaces are still being proven out together.
3. **Vendor (copy) the code into conductor-agent.** Rejected — it duplicates the source of truth, and defeats the point of these being separately versioned, separately testable components.

**Decision:** Option 1 for the integration/development phase. Revisit option 2 once all three interfaces are stable and the goal shifts from "iterate together" to "deploy independently" (relevant once this reaches the K8s manifests already in `deploy/k8s/`).

## 4. Per-Component Integration Design

### 4.1 Candidate Profile (#10) — High Confidence

The package is explicitly designed for this exact integration — its own README shows the intended LangGraph pattern directly:

```python
from typing import TypedDict, Annotated
from candidate_profile import CandidateProfile, CandidateProfilePatch, merge_candidate_profile

class ConductorState(TypedDict):
    profile: Annotated[CandidateProfile, merge_candidate_profile]
    ...  # existing ConductorState fields unchanged
```

**Design:**

- Add `profile: Annotated[CandidateProfile, merge_candidate_profile]` to Conductor's existing `ConductorState` in `conductor/state.py`. This is additive, not a replacement of the existing state shape.
- New adapter, `conductor/adapters/candidate_profile.py`, wrapping `CandidateProfileStore` (`get`, `put`, `list_versions`) and the six projection functions (`to_resume_profile`, `to_gleaner_query`, `to_outreach_context`, `to_application_view`, `to_usher_profile`, `to_research_scope`).
- **Reads:** each node that currently reads `master_resume.txt` or hardcodes candidate data switches to calling the matching projection function against `state["profile"]`:
  - `align_resume.py` → `to_resume_profile(profile)`
  - `research.py` → `to_research_scope(profile)`
  - `auto_apply.py` → `to_application_view(profile)` and/or `to_usher_profile(profile)` (both exist — §4.3 needs to confirm which Usher actually expects)
  - `harvester.py` → `to_gleaner_query(profile)` for search-criteria-driven discovery, if applicable
- **Writes:** per the package's own ownership map, each node emits a `CandidateProfilePatch` for its owned section only — AlignResume → `tailoring_history`, Overture → `outreach_history`, Usher → `application_history`, Sentiment Classifier → `interaction_signals`, Conductor itself → `profile_metadata`. The `merge_candidate_profile` reducer handles the merge; nodes don't need to read-modify-write the whole profile.
- **Anti-fabrication hook:** `check_skill_provenance(candidate_id, skill_name)` is a natural fit for AlignResume's tailoring step, immediately before any resume bullet claims a skill — reject or flag any generated bullet whose skill claim doesn't resolve to a verified provenance record. This is the same guardrail philosophy already used in AlignResume standalone (deterministic hallucination guardrail) — worth wiring through rather than leaving the two guardrails disconnected.
- **Telemetry consolidation:** the package's five Prometheus metrics (`candidate_profile_writes_total`, `_validation_failures_total`, `_schema_version_gauge`, `_write_latency_seconds`, `_ownership_violations_total`) can register against Conductor's existing Prometheus registry if run in-process (Option 1 above makes this straightforward), landing on the same Grafana dashboard already built for Conductor rather than requiring a second one.

### 4.2 Memory Module (#8) — High Confidence, One Gap to Close

**Key architectural decision:** Memory Module does not replace Conductor's `MemoryStore` interface — it becomes the concrete implementation behind it. Conductor's own ADR-2 already declared the storage layer pluggable; this is that plug being used as designed.

```python
# conductor/storage/event_sourced_store.py  (new)
from conductor.storage.base import MemoryStore as ConductorMemoryStoreInterface
from memory_module.store import MemoryStore as EventLedger
from memory_module.adapters import from_harvester_event, from_classified_signal

class EventSourcedMemoryStore(ConductorMemoryStoreInterface):
    def __init__(self, db_path: str):
        self._ledger = EventLedger(db_path)

    # Implements whatever methods conductor/storage/base.py's
    # abstract interface actually declares — confirm exact method
    # names against source before writing this class (Phase 0).
    ...
```

This keeps every call site in `conductor/graph/nodes.py` unchanged — they already call through the `MemoryStore` interface, not the concrete class, precisely because ADR-2 was designed for this.

**The one confirmed gap:** Conductor's dedup check ("cross-referencing incoming postings against URL hashes and normalized (company + title) records") and cooldown check need query methods. Only `get_application()` and `get_stale_applications()` are confirmed from Memory Module's README. Two options once Phase 0 confirms whether more query methods already exist:
- If they exist (e.g., `find_by_url_hash()`, `find_by_company()`), use them directly.
- If they don't, add them to `conductor-memory-module` — a small, additive change, not a redesign, since the underlying SQLite schema already indexes on job/application identifiers per the README's DDL description.

**Event emission points** to add across Conductor's existing adapters:

| Conductor adapter | Event to emit | Adapter function |
|---|---|---|
| `harvester.py` | `JOB_DISCOVERED` | `from_harvester_event()` — confirmed |
| `align_resume.py` | `RESUME_TAILORED` | Not confirmed to exist yet — verify in Phase 0 |
| `overture.py` | `OUTREACH_SENT` | Not confirmed to exist yet — verify in Phase 0 |
| `auto_apply.py` | `APPLICATION_SUBMITTED` | Not confirmed to exist yet — verify in Phase 0 |
| `sentiment.py` | `RESPONSE_CLASSIFIED` | `from_classified_signal()` — confirmed |

**What does NOT change:** Conductor's own `conductor_memory.db` continues to serve LangGraph execution-state checkpointing (ADR-4's "Zero Silent Drops" — resuming an interrupted graph run). That is a different concern from the business-domain application lifecycle Memory Module tracks. Collapsing the two into one store would conflate infrastructure state with domain history; keep them as two stores behind two purposes, even though both now happen to be SQLite.

### 4.3 Usher / PDF Auto-Apply (#7) — Proposed Shape, Pending Verification

Given the confidence gap in §1, this section proposes an integration *shape* consistent with everything else in this design, not a committed interface.

**Proposed:**
- Replace the body of `conductor/adapters/auto_apply.py` with a call into the `usher` package instead of whatever stub logic exists there now.
- Input: `to_application_view(profile)` and/or `to_usher_profile(profile)` from Candidate Profile (§4.1) — Usher's own repo naming ("Usher Schema Match") suggests it has a specific expected input shape; both projections exist so either could be the one it wants — Phase 0 confirms which.
- Output: on successful submission, emit `APPLICATION_SUBMITTED` to Memory Module (§4.2), and a `CandidateProfilePatch` against `application_history` (§4.1).
- The "4-tier field resolution" and "Multi-ATS adapters" described in Usher's own README title suggest it may already assume some structured input schema per ATS (Greenhouse, Lever, Workday, Ashby — matching the four named in Conductor's own dynamic-channel-routing description). If so, `to_application_view`/`to_usher_profile` need to produce whatever shape Usher's per-ATS resolvers expect — this is the single highest-uncertainty interface point in the whole integration and the reason Phase 0 treats reading Usher's actual source as a hard gate, not an optional nice-to-have.
- Given the Human Approval Gate (ADR-6) already sits upstream of both outreach and application-submission channels, no *additional* approval gate is needed here — Usher's own "policy-gated" framing should be checked against whether it duplicates ADR-6 or adds a distinct, narrower policy layer (e.g., per-ATS rate limiting) worth keeping alongside it rather than instead of it.

## 5. Updated Tier-1 Execution Loop

```
[Harvester] ──► JOB_DISCOVERED (Memory Module)
     │
     ▼
[Dedup Check] ──(via Memory Module query, §4.2 gap)──► skip if duplicate
     │
     ▼
[Cooldown Check] ──(via Memory Module query)──► skip if in cooldown
     │
     ▼
[Research Agent] ──uses to_research_scope(profile)──► CompanyBrief
     │
     ▼
[AlignResume] ──uses to_resume_profile(profile)──► tailored resume
     │         ──check_skill_provenance()──► guardrail check
     │         ──emits RESUME_TAILORED (Memory Module)
     │         ──emits CandidateProfilePatch: tailoring_history
     ▼
[Human Approval Gate] (unchanged, ADR-6)
     │
     ▼
[Dynamic Channel Routing]
     │                              │
     ▼ (email)                     ▼ (form/portal)
[Overture]                    [Usher / PDF Auto-Apply]
  uses to_outreach_context()    uses to_application_view()/to_usher_profile()
  emits OUTREACH_SENT            emits APPLICATION_SUBMITTED
  emits patch: outreach_history  emits patch: application_history
     │                              │
     └──────────────┬───────────────┘
                     ▼
        [EventSourcedMemoryStore] ──► Memory Module ledger (business history)
        [Conductor's own MemoryStore] ──► execution-state checkpoint (unchanged)
                     │
                     ▼
              [Prometheus Metrics] ──► existing exporter + candidate_profile_* metrics
```

## 6. Migration Plan

| From | To | Approach |
|---|---|---|
| `data/master_resume.txt` | `CandidateProfile` (identity, education, skills, experience, preferences sections) | One-time script, run once, not part of the LangGraph loop. Parse the existing text into the profile schema, `CandidateProfileStore.put()` once, then treat `master_resume.txt` as deprecated — don't maintain both. |
| `conductor_memory.db` (existing runs) | — | **Not migrated.** It continues serving its original checkpointing purpose (§4.2). No data loss risk since nothing is being discarded — it's a second store for a second purpose, not a superseded one. |

## 7. Updated Component Integration Map

Supersedes the table in Conductor's current README once implemented:

| Component | Role | Integration Mechanism |
|---|---|---|
| #1 Harvester | Job Discovery | `HarvesterAdapter` (unchanged) |
| #2 AlignResume | Resume Tailoring | `AlignResumeAdapter` + `to_resume_profile()` + `check_skill_provenance()` |
| #3 Overture | Cold Outreach | `OvertureAdapter` + `to_outreach_context()` |
| #4 Research Agent | Company Intelligence | `ResearchAgentAdapter` + `to_research_scope()` |
| #7 Usher | Portal Form Application | `AutoApplyAdapter` → `usher` package + `to_application_view()`/`to_usher_profile()` (pending Phase 0) |
| #6 Conductor | Coordination | LangGraph `StateGraph` + `ConductorState` (now includes `profile`) |
| #8 Memory Module | Business-Event Ledger | `EventSourcedMemoryStore` implementing Conductor's `MemoryStore` interface, backed by `conductor-memory-module` |
| #9 Sentiment Classifier | Response Classification | `SentimentClassifierAdapter` + `from_classified_signal()` |
| #10 Candidate Profile | Canonical Data Layer | `candidate_profile` package, in-process or via `conductor-cp-mcp` |
| — | Execution-State Checkpointing | Conductor's own `SQLiteMemoryStore`/`JSONMemoryStore` (unchanged, distinct purpose from #8) |
| Observability | Telemetry | Prometheus (Conductor's + Candidate Profile's metrics, one registry) + Grafana |

## 8. New ADRs to Record in Conductor's Own Docs

- **ADR-7:** Sibling components consumed as editable local packages via git submodule during integration (§3).
- **ADR-8:** Memory Module's event ledger and Conductor's execution-state store are deliberately kept separate despite both being SQLite — different purposes, not redundant (§4.2).
- **ADR-9:** `master_resume.txt` is deprecated in favor of `CandidateProfile` after a one-time migration; not maintained in parallel (§6).

## 9. Risks & Open Questions

| # | Risk / Question | Severity | Resolve by |
|---|---|---|---|
| 1 | Usher's actual input schema is unconfirmed — `to_application_view` vs `to_usher_profile` may not be a clean match | Medium-High | Implementation Phase 0 (read `usher/` source directly) |
| 2 | Memory Module may not yet have adapter functions for `RESUME_TAILORED`/`OUTREACH_SENT`/`APPLICATION_SUBMITTED` | Medium | Implementation Phase 0 |
| 3 | Dedup/cooldown query methods on Memory Module's `MemoryStore` are unconfirmed | Medium | Implementation Phase 0; small additive change if missing |
| 4 | Whether Conductor's own DRY_RUN flag should gate Usher's real submissions the same way it gates Overture's real sends | Low — almost certainly yes, but worth stating explicitly rather than assuming | Confirm during Phase 3 (CONDUCTOR_08) |
| 5 | This is genuinely three integrations, not one — CONDUCTOR_08 treats them as separable phases so a partial integration (e.g., Memory Module only) is still a coherent, shippable state | — | See CONDUCTOR_08 §0 |
