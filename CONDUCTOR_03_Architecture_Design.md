# CONDUCTOR — Architecture Design

**Document ID:** CND-ARCH-v1.0
**Status:** Draft for review
**Date:** 2026-08-25
**Framework applied:** Requirements → High-level design → Deep dive → Scale/reliability → Trade-off analysis

---

## 1. Architecture Goals and Constraints

- **Orchestration engine:** LangGraph, per umbrella Mission Plan §10.5/§13 — already decided, not re-litigated here.
- **Shared state:** Candidate Profile JSON as the canonical object flowing through the graph — already decided.
- **Cost-awareness:** inherit Future Fit's and Sentiment Classifier's two-tier pattern — cheap deterministic checks before any LLM call, LLM calls routed and rate-limit-aware.
- **No-silent-drop:** inherit Sentiment Classifier's principle directly — every node produces a persisted result, including on failure.
- **Full observability:** every sub-agent call is logged, timed, and attributable to a specific job-opportunity record.

## 2. System Context Diagram

```
                         ┌─────────────────────────┐
                         │   Candidate Profile JSON │
                         │   (shared state, #10)    │
                         └────────────┬─────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              │                       ▼                       │
              │                 ┌───────────┐                 │
   Discovery  │  ┌──────────►   │ CONDUCTOR │   ◄──────────┐  │  Application
              │  │              │    (#6)   │              │  │
              │  │              └─────┬─────┘              │  │
              │  │                    │                     │  │
        ┌─────▼──┴───┐        ┌───────▼───────┐      ┌──────┴──▼─────┐
        │  Harvester  │        │  Sentiment    │      │   AlignResume  │
        │    (#1)     │        │  Classifier   │      │      (#2)      │
        └─────────────┘        │    (#9)       │      └───────┬────────┘
                                └───────▲───────┘              │
                                        │                       ▼
                                ┌───────┴───────┐       ┌───────────────┐
                                │   Overture     │◄──────┤ (tailored PDF) │
                                │    (#3)        │       └───────────────┘
                                └───────┬────────┘
                                        │
                                        ▼
                                ┌───────────────┐
                                │ Memory Module  │
                                │     (#8)       │
                                └───────────────┘
```

Research Agent (#4) and PDF Auto-Apply Agent (#7) are omitted from this diagram — they attach in Phase 4 (CND-IMPL) and do not change the core topology below.

## 3. Core Abstractions

### 3.1 Candidate Profile JSON (proposed v0.1 schema — illustrative, not final)

```json
{
  "candidate_id": "sdn9300",
  "resume_master_ref": "align-resume/base-v12",
  "target_roles": ["AI Engineer", "Data Scientist", "GenAI Engineer"],
  "applications": [
    {
      "job_id": "uuid",
      "source": "harvester | manual",
      "posting_ref": { "company": "", "title": "", "jd_text_ref": "" },
      "status": "discovered | tailored | outreach_pending_review | outreach_sent | responded | closed",
      "tailored_resume_ref": "align-resume/run-id",
      "outreach_ref": "overture/run-id",
      "sentiment_signal": { "urgency": null, "action": null, "classified_at": null },
      "timestamps": { "discovered": "", "tailored": "", "sent": "", "last_updated": "" }
    }
  ]
}
```

This schema is intentionally minimal for v1. It is expected to be revised once Memory Module's actual query patterns are known — schema-first, but not schema-frozen.

### 3.2 ConductorState (LangGraph state object)

The per-run object passed between graph nodes. A thin wrapper around one `applications[]` entry from the Candidate Profile JSON plus run-scoped metadata (run ID, node trace, error log). Kept separate from the full Candidate Profile JSON so that a single job's processing never requires loading or locking the entire candidate record.

### 3.3 AgentAdapter Interface

Every sibling component Conductor calls is wrapped behind the same contract, deliberately reusing the **abstract adapter pattern already established in Harvester's own architecture** for its four job-board scrapers — the same shape now applied one level up, to whole agents rather than data sources:

```
AgentAdapter:
    invoke(state: ConductorState) -> AgentResult
    health_check() -> bool

AgentResult:
    success: bool
    output: dict | None
    error: str | None        # populated even on partial success
    cost_estimate: float | None
```

Concretely: `HarvesterAdapter`, `AlignResumeAdapter`, `OvertureAdapter`, `SentimentClassifierAdapter`. Each translates Conductor's generic call into whatever that specific agent actually needs (a Python function call for same-repo agents, an HTTP call for AlignResume's Vercel deployment).

## 4. Graph Topology (v1 — AlignResume + Overture, Harvester stubbed)

```
[Entry] → Load State
             │
             ▼
      ┌─────────────┐   no seed job available   ┌─────┐
      │  Harvester   ├───────────────────────────►│ End │
      │  (or stub)   │                             └─────┘
      └──────┬───────┘
             │ posting available
             ▼
      ┌─────────────┐
      │ AlignResume │  (tailor against this posting's JD)
      └──────┬───────┘
             ▼
      ┌─────────────┐
      │ Human Gate  │  (review before send — see ADR-6 / CND-EDGE cat. 6)
      └──────┬───────┘
             ▼
      ┌─────────────┐
      │  Overture   │  (compose + send)
      └──────┬───────┘
             ▼
      ┌───────────────────┐
      │ Persist + Log      │──► Memory Module (interface only, v1)
      └────────────────────┘
```

## 5. Architecture Decision Records

### ADR-1: Resolving the AlignResume / Harvester Ordering

**Context:** The candidate's own answer correctly flagged that resume-tailoring and job-discovery order "sometimes" invert. Investigating why: AlignResume needs a specific job description to tailor against, which only Harvester (or a manual substitute) can supply. The two are not actually interchangeable within a single job's processing — the apparent flexibility comes from conflating two different kinds of tailoring pass.

**Decision:** Split into two tiers.
- **Tier 0 — Baseline pass** (order-flexible, runs independently, low frequency): AlignResume periodically re-optimizes the master resume against a general target-role profile, with no specific JD. This can run before, after, or independent of any discovery activity.
- **Tier 1 — Per-job loop** (strict order, runs per opportunity): Harvester (or a manually supplied posting) → AlignResume (tailor against that specific JD) → Overture (send). Order is fixed here because the dependency is real.

**Status:** Accepted. This preserves the candidate's original observation as correct for Tier 0 while resolving the real constraint in Tier 1.

### ADR-2: Memory Module as a Pluggable Interface, Not a Blocking Dependency

**Context:** Memory Module is unbuilt. Conductor's MVP cannot wait for it.

**Decision:** Define a `MemoryStore` interface now (`write(record)`, `query(filters)`, `get_history(job_id)`). Ship v1 with a minimal local implementation (append-only JSON or SQLite, matching the pattern already used for Overture's run-history storage) satisfying that interface. Swap in the real Memory Module later without touching Conductor's core graph.

**Status:** Accepted.

### ADR-3: Cross-Stack Agent Invocation via MCP

**Context:** Harvester and Sentiment Classifier are same-repo Python and can be called as native LangGraph tool nodes. AlignResume is a separate Next.js/Vercel deployment.

**Decision:** Same-repo Python agents are invoked as direct LangGraph tool nodes. Cross-stack agents (starting with AlignResume) are wrapped behind a small MCP server exposing a `tailor_resume(jd, resume_ref)` tool. This is not new scope invented for Conductor — it is exactly the "custom MCP server exposing [an agent] as a callable tool" checkpoint already named in the umbrella Mission Plan's Stage 03 curriculum. One build satisfies both.

**Status:** Accepted.

### ADR-4: No-Silent-Drop Principle

**Context:** Sentiment Classifier's `ClassifiedSignal` guarantee — every input produces an output, nothing is dropped — is a project-wide value, not a one-component rule.

**Decision:** Every `AgentAdapter.invoke()` call returns an `AgentResult` even on failure. A failed node writes a `status: "error"` record to the state and to the persisted log; it never simply skips silently. The graph continues to the next resumable point rather than crashing the whole run.

**Status:** Accepted.

### ADR-5: Observability via Extended Prometheus, Not a New Stack

**Context:** Overture already exposes a Prometheus metrics server. Building a second, separate observability system for Conductor duplicates effort the DevOps roadmap (Phase 10) already plans to extend with Grafana.

**Decision:** Conductor emits its own metrics (run duration, node success/failure counts, cost per run) to the same Prometheus instance Overture already uses, with a distinct metric namespace (`conductor_*`). Dashboards are unified later in DevOps roadmap Phase 10, not duplicated now.

**Status:** Accepted.

### ADR-6: Human Approval Gate Before Outreach Sends

**Context:** Overture sends real email, to real people, from a real Gmail account, on the candidate's behalf. AlignResume already embeds a truthfulness guardrail specifically because unreviewed LLM output carries reputational risk. Fully autonomous send (discover → tailor → send, zero review) applies that same risk to outbound communication with actual recruiters, with no equivalent guardrail.

**Decision:** v1 includes a mandatory human-review checkpoint between AlignResume's tailoring output and Overture's send action. Full autonomy (removing this gate) is an explicit, separately-evaluated decision for a later phase — not a default.

**Status:** Accepted. See CND-EDGE category 6 for the full scenario treatment.

## 6. Deployment View

- **v1:** Single local/scriptable process (LangGraph app run directly). No containerization required.
- **Target (Phase 5):** Each agent adapter containerized, Conductor scheduling them as Kubernetes Jobs/Deployments, per the umbrella Mission Plan's own stated direction (§9). Explicitly not a v1 requirement — the Minikube fundamentals already in hand inform this target without gating the MVP on it.

## 7. Trade-offs Worth Revisiting as the System Grows

- Tier 0/Tier 1 split (ADR-1) adds a small amount of coordination complexity now, in exchange for correctness; revisit if Harvester's real throughput makes Tier 0 unnecessary.
- The local `MemoryStore` (ADR-2) will need a real migration path once Memory Module ships — worth designing the interface with that migration in mind from day one, not as an afterthought.
- MCP wrapping (ADR-3) adds a network hop for AlignResume calls; acceptable at current scale, worth profiling once volume increases.
