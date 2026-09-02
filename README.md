# 🎭 Conductor Agent — Coordination & Orchestration Layer

[![Python](https://img.shields.io/badge/Python-3.10%2B%20%7C%203.12%20%7C%203.14-blue.svg?logo=python&logoColor=white)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-StateGraph-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![Pydantic](https://img.shields.io/badge/Pydantic-v2.0-e92063.svg?logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![Prometheus](https://img.shields.io/badge/Prometheus-Port%208001-E6522C.svg?logo=prometheus&logoColor=white)](https://prometheus.io/)
[![Docker](https://img.shields.io/badge/Docker-Multi--Stage-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-CronJobs%20%26%20Deployments-326CE5.svg?logo=kubernetes&logoColor=white)](https://kubernetes.io/)
[![Tests](https://img.shields.io/badge/Tests-63%20Passed-brightgreen.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **Conductor Agent (#6)** is the central orchestration brain and state coordinator for the **10-Component AI-Native Job Agent Architecture**. Built on **LangGraph**, **Pydantic v2**, and **Prometheus**, Conductor unifies multi-board job discovery, deep company intelligence, resume tailoring, human approval gating, dynamic multi-channel application dispatch, durable memory checkpointing, and sentiment feedback loops into a resilient, production-hardened system.

---

## 📑 Table of Contents

- [Architectural Topology](#-architectural-topology)
- [Key Features & Design Decisions](#-key-features--design-decisions)
- [Component Integration Map](#-component-integration-map)
- [Project Structure](#-project-structure)
- [Quickstart Guide](#-quickstart-guide)
- [CLI Reference](#-cli-reference)
- [Production Deployment](#-production-deployment)
  - [Docker Compose (Local Cluster)](#docker-compose-local-cluster)
  - [Kubernetes Manifests (Production)](#kubernetes-manifests-production)
- [Testing & Quality Assurance](#-testing--quality-assurance)
- [Observability & Monitoring](#-observability--monitoring)
- [Architecture Decision Records (ADRs)](#-architecture-decision-records-adrs)
- [Author & License](#-author--license)

---

## 🏛 Architectural Topology

Conductor separates orchestration into a decoupled **Tier-0 Baseline Pass** and a high-throughput **Tier-1 Per-Job Execution Loop**:

```
                    ┌────────────────────────────────────────────────────────┐
                    │               Tier-0: Baseline Pass (ADR-1)             │
                    │      (General Target-Role Master Resume Optimization)  │
                    └───────────────────────────┬────────────────────────────┘
                                                │
┌───────────────────────────────────────────────┴───────────────────────────────────────────────┐
│ Tier-1: Per-Job Execution Loop (LangGraph StateGraph)                                          │
│                                                                                               │
│   [Gleaner Adapter] ──► Discovers opportunities across RemoteOK, Indeed, Wellfound, Naukri  │
│            │                                                                                  │
│            ▼                                                                                  │
│   [Deduplication Check] ──────(Duplicate URL/Title)──────► [Bypass to Persist: skipped_dupe]  │
│            │ (New Posting)                                                                    │
│            ▼                                                                                  │
│   [Cooldown Check] ───────────(In 30-Day Cooldown)───────► [Bypass to Persist: skipped_cool]  │
│            │ (Active & Cleared)                                                               │
│            ▼                                                                                  │
│   [Research Agent] ──► Synthesizes CompanyBrief (tech signals, culture notes, news items)     │
│            │                                                                                  │
│            ▼                                                                                  │
│   [AlignResume]    ──► Tailors resume & computes ATS score against JD + Company Intelligence  │
│            │                                                                                  │
│            ▼                                                                                  │
│   [Human Approval Gate] ──► Candidate review (Approve / Edit / Reject / Abort) [ADR-6]        │
│            │ (Approved)                                                                       │
│            ▼                                                                                  │
│   [Dynamic Channel Routing]                                                                   │
│          /            \                                                                       │
│   (Recruiter Email)    \ (Careers Portal / Web Form)                                          │
│         ▼               ▼                                                                     │
│   [Overture Outreach]   [PDF Auto-Apply]                                                      │
│   (Customized Cold      (Compiles Tailored PDF                                                │
│    Email Dispatch)       Resume & Form Payload)                                               │
│         \               /                                                                     │
│          \             /                                                                      │
│           ▼           ▼                                                                       │
│   [MemoryStore SQLite/JSON] ──► Durable state checkpoint with Zero Silent Drops [ADR-4]       │
│            │                                                                                  │
│            ▼                                                                                  │
│   [Prometheus Metrics] ──► Emits latency, status, errors, gate decisions, and costs (:8001)   │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## ✨ Key Features & Design Decisions

### 1. Multi-Agent Orchestration with LangGraph
Every agent in the ecosystem is integrated via the uniform `AgentAdapter` interface, translating calls across in-process Python modules, HTTP REST endpoints, and background workers with strict error boundaries.

### 2. Human-in-the-Loop Approval Gate (ADR-6 & EC-13)
Outbound communication directly impacts candidate reputation. Conductor enforces a **hard structural gate** ensuring no cold email or form submission can execute without explicit candidate approval.

### 3. Intelligent Deduplication (EC-06)
Prevents duplicate processing by cross-referencing incoming postings against URL hashes and normalized `(company + title)` records in `MemoryStore`, saving unnecessary LLM token consumption.

### 4. Sentiment Feedback & Rejection Cooldown (Task 3.3 & EC-07)
When an inbound rejection response (`hard_rejection`, `soft_rejection`, or negative macro sentiment) is classified by the Sentiment Classifier, Conductor flags the company and enforces a **30-day outreach cooldown**, automatically suppressing future outreach.

### 5. Dynamic Multi-Channel Routing (Task 4.3)
Intelligently inspects job postings to determine the optimal application path:
- **Email Channel**: Direct recruiter contact $\rightarrow$ routes to **Overture** for personalized cold email dispatch.
- **Form / Portal Channel**: Careers links (Greenhouse, Lever, Workday, Ashby, etc.) $\rightarrow$ routes to **PDF Auto-Apply** for tailored PDF compilation and form packaging.

### 6. Tier-0 Baseline Optimization Pass (ADR-1)
Allows candidates to periodically optimize their master resume against broad market role criteria (`AI Engineer`, `Data Scientist`, `GenAI Architect`) decoupled from any specific job posting.

### 7. Zero-Silent-Drop Durable Persistence (ADR-4)
All lifecycle milestones, error traces, and state transitions are durably checkpointed to `SQLiteMemoryStore` or `JSONMemoryStore`.

---

## 🧩 Component Integration Map

| Component | Role in Architecture | Integration Mechanism |
|---|---|---|
| **#1 Gleaner** | Multi-Board Job Discovery | `HarvesterAdapter` (RemoteOK, Indeed, Wellfound, Naukri) |
| **#2 AlignResume** | Resume Tailoring & ATS Scoring | `AlignResumeAdapter` (HTTP REST API with deterministic fallback, provenance-gated via Candidate Profile) |
| **#3 Overture** | Cold Outreach Automation | `OvertureAdapter` (Email draft generation & Gmail/SMTP dispatch) |
| **#4 Research Agent** | Company Intelligence Gathering | `ResearchAgentAdapter` (Synthesizes `CompanyBriefRef` tech signals & culture) |
| **#5/#7 Usher (PDF Auto-Apply)** | Real ATS Portal Form Submission | `PDFAutoApplyAdapter` → `usher.conductor.run_auto_apply_pipeline()` (4-tier field resolution, Playwright browser automation, DRY_RUN→SubmissionMode.DRAFT mapping) |
| **#6 Conductor** | Coordination & State Machine | LangGraph `StateGraph` + Pydantic v2 `ConductorState` |
| **#8 Memory Module** | Event-Sourced Durable Checkpointing | `EventSourcedMemoryStore` wrapping `memory_module.store.MemoryStore` (deterministic event IDs, domain cooldown registry, ADR-5 idempotency) |
| **#9 Sentiment Classifier** | Inbound Response Categorization | `SentimentClassifierAdapter` (Macro sentiment, intent, urgency & cooldown) |
| **#10 Candidate Profile** | Canonical Candidate Data Layer | `CandidateProfileAdapter` with `CandidateProfileStore` (anti-fabrication provenance gate IG-6, per-component projections: `to_resume_profile()`, `to_usher_profile()`, `to_gleaner_query()`, `to_outreach_context()`) |
| **Observability** | Telemetry & Health Monitoring | Prometheus Exporter (Port 8001) + Grafana Dashboard (profile patches, IG-6 rejections, subsystem health) |

---

## 📂 Project Structure

```
Conductor Agent/
├── conductor/
│   ├── __init__.py
│   ├── config.py                 # Environment configuration & defaults
│   ├── state.py                  # Pydantic v2 State & Canonical Data Models
│   ├── metrics.py                # Prometheus metric definitions & exporter server
│   ├── scheduler.py              # Autonomous scheduler daemon runner
│   ├── cli.py                    # Unified CLI (run, harvest, daemon, baseline, etc.)
│   ├── adapters/                 # Specialist Agent Adapters
│   │   ├── __init__.py
│   │   ├── base.py               # Abstract AgentAdapter & AgentResult contracts
│   │   ├── gleaner.py          # Gleaner Multi-Board Scraper Adapter (#1)
│   │   ├── harvester_stub.py     # Manual Seed Posting Stub Adapter
│   │   ├── research.py           # Research Agent Company Intelligence Adapter (#4)
│   │   ├── align_resume.py       # AlignResume Tailoring & ATS Gap Adapter (#2)
│   │   ├── overture.py           # Overture Cold Email Outreach Adapter (#3)
│   │   ├── auto_apply.py         # PDF Auto-Apply Portal Application Adapter (#5)
│   │   └── sentiment.py          # Sentiment Classifier Adapter (#9)
│   ├── graph/                    # LangGraph State Machine
│   │   ├── __init__.py
│   │   ├── nodes.py              # Execution nodes & human approval gate
│   │   └── workflow.py           # Graph assembly & dynamic channel routing
│   └── storage/                  # MemoryStore Implementations
│       ├── __init__.py
│       ├── base.py               # Abstract MemoryStore interface
│       └── local_store.py        # SQLite & Append-Only JSON implementations
├── data/
│   ├── master_resume.txt         # Candidate master resume text
│   └── conductor_memory.db       # SQLite database (auto-created)
├── deploy/
│   ├── prometheus/
│   │   ├── prometheus.yml        # Prometheus scrape configuration
│   │   └── alerts.yml            # Alerting rules (errors, latency, gate stalls)
│   ├── grafana/
│   │   ├── provisioning/         # Datasource & dashboard provisioning
│   │   └── dashboards/
│   │       └── conductor_dashboard.json # Comprehensive Grafana visualization
│   └── k8s/                      # Kubernetes Manifests
│       ├── conductor-pvc.yaml    # Persistent Volume Claim
│       ├── conductor-configmap.yaml # Environment ConfigMap
│       ├── conductor-deployment.yaml # Daemon Deployment & Service
│       └── conductor-cronjob.yaml   # Daily Harvest & Weekly Baseline CronJobs
├── tests/                        # 47 Unit, Integration & Structural Tests
│   ├── test_adapters.py
│   ├── test_harvester_adapter.py
│   ├── test_research_adapter.py
│   ├── test_auto_apply_adapter.py
│   ├── test_sentiment_adapter.py
│   ├── test_deduplication.py
│   ├── test_feedback_loop.py
│   ├── test_channel_routing.py
│   ├── test_human_gate.py
│   ├── test_tier0.py
│   ├── test_storage.py
│   ├── test_state.py
│   ├── test_failure_injection.py
│   ├── test_integration.py
│   ├── test_three_agent_integration.py
│   ├── test_observability.py
│   └── test_manifests.py
├── Dockerfile                    # Multi-Stage Production Containerfile
├── docker-compose.yml            # Local Conductor + Prometheus + Grafana stack
├── requirements.txt              # Production & development dependencies
└── README.md
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- **Python 3.10+** (Python 3.12 or 3.14 recommended)
- **Git**

### 2. Installation
```bash
# Clone repository
git clone https://github.com/sdn9300/conductor-agent.git
cd conductor-agent

# Create virtual environment
python -m venv venv
# Linux/macOS:
source venv/bin/activate
# Windows:
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment
Create a `.env` file in the root directory (optional, defaults provided in `config.py`):
```ini
CANDIDATE_NAME="Soumyadeep Nath"
CANDIDATE_EMAIL="soumyadeepnath@example.com"
STORAGE_TYPE="sqlite"
DRY_RUN=true
AUTO_APPROVE=false
METRICS_ENABLED=true
PROMETHEUS_PORT=8001
COOLDOWN_DAYS=30
```

---

## 💻 CLI Reference

Conductor provides a comprehensive CLI for single runs, batch harvesting, daemon scheduling, baseline maintenance, response ingestion, and inspection.

### 1. Single Job Orchestration (`conductor run`)
```bash
# Direct Recruiter Outreach (Email Channel)
python -m conductor.cli run \
  --company "Anthropic" \
  --role "Research Engineer" \
  --contact-email "talent@anthropic.com" \
  --jd-text "We are hiring an AI Engineer experienced in LangGraph and LLM evaluations." \
  --channel email \
  --dry-run

# Careers Portal Application (Form / PDF Auto-Apply Channel)
python -m conductor.cli run \
  --company "Google DeepMind" \
  --role "Staff AI Engineer" \
  --url "https://careers.google.com/jobs/123" \
  --jd-text "Senior distributed systems and LLM engineer for agent coordination." \
  --channel form \
  --dry-run
```

### 2. Multi-Board Batch Discovery & Orchestration (`conductor harvest`)
```bash
python -m conductor.cli harvest \
  --role "AI Engineer" \
  --location "Remote" \
  --boards "remoteok,indeed,wellfound,naukri" \
  --limit 5 \
  --dry-run \
  --auto-approve
```

### 3. Tier-0 Baseline Optimization Pass (`conductor baseline`)
```bash
python -m conductor.cli baseline --role "AI Engineer"
```

### 4. Recruiter Response Ingestion & Sentiment Feedback (`conductor ingest-response`)
```bash
python -m conductor.cli ingest-response \
  --company "VentureCorp" \
  --text "Thank you for applying. Unfortunately, we have decided to pursue other candidates."
```
*Automatically marks the application `CLOSED` and activates the **30-day cooldown suppression**.*

### 5. Autonomous Scheduler Daemon (`conductor daemon`)
```bash
python -m conductor.cli daemon \
  --interval-seconds 3600 \
  --role "AI Engineer" \
  --location "Remote" \
  --limit 10 \
  --dry-run \
  --auto-approve
```

### 6. History & State Inspection
```bash
# View recent applications in SQLite
python -m conductor.cli history --limit 20

# Inspect full JSON state of a specific job_id
python -m conductor.cli inspect --job-id <JOB_UUID>
```

---

## 🚢 Production Deployment

### Docker Compose (Local Cluster)
Start the complete stack (Conductor + Prometheus + Grafana) with a single command:

```bash
docker-compose up -d --build
```
- **Conductor Metrics**: `http://localhost:8001/metrics`
- **Prometheus Dashboard**: `http://localhost:9090`
- **Grafana Visualization**: `http://localhost:3001` *(Credentials: `admin` / `conductor`)*

### Kubernetes Manifests (Production)
Deploy to Kubernetes / Minikube:

```bash
# 1. Apply Storage & Config
kubectl apply -f deploy/k8s/conductor-pvc.yaml
kubectl apply -f deploy/k8s/conductor-configmap.yaml

# 2. Deploy Autonomous Daemon & Service
kubectl apply -f deploy/k8s/conductor-deployment.yaml

# 3. Schedule Recurring CronJobs
kubectl apply -f deploy/k8s/conductor-cronjob.yaml
```

---

## 🧪 Testing & Quality Assurance

Conductor is tested with a rigorous `pytest` test suite covering:
- **Specialist Adapters** (Gleaner, Research Agent, AlignResume, Overture, Auto-Apply, Sentiment Classifier)
- **LangGraph State Transitions & Dynamic Routing**
- **Deduplication Engine & Feedback Loop Cooldowns**
- **Human Gate Structural Bypass Prevention**
- **Failure Injection & Graceful Degradation**
- **Container & Kubernetes Manifest Validations**

```bash
# Run all 47 automated tests
pytest -v tests/
```

---

## 📊 Observability & Monitoring

Conductor natively instruments the following Prometheus metrics on port `8001` (`/metrics`):

| Metric Name | Type | Description |
|---|---|---|
| `conductor_runs_total` | Counter | Total job runs partitioned by status (`completed`, `skipped_duplicate`, `skipped_cooldown`, `error`, `rejected`, `aborted`) |
| `conductor_node_duration_seconds` | Histogram | Execution latency percentiles across nodes (`discover`, `research`, `tailor`, `human_gate`, `outreach`, `auto_apply`, `persist`) |
| `conductor_node_errors_total` | Counter | Total error count per graph node |
| `conductor_human_gate_actions_total` | Counter | Total human review decisions (`approve`, `edit`, `reject`, `abort`) |
| `conductor_token_cost_total` | Counter | Cumulative estimated LLM token expenditure by component |

---

## 📋 Architecture Decision Records (ADRs)

- **ADR-1: Tier-0 vs. Tier-1 Pass Decoupling**: Decoupled general role resume optimization (Tier-0) from the per-job opportunity loop (Tier-1).
- **ADR-2: Pluggable Storage Layer**: Local `SQLiteMemoryStore` and flat-file `JSONMemoryStore` implement the canonical `MemoryStore` interface.
- **ADR-4: Zero Silent Drops Policy**: Failure at any node boundary commits state checkpoints with descriptive error traces.
- **ADR-6: Human-in-the-Loop Gate Enforcement**: Structural prevention of outbound email or application submission without candidate authorization.

---

## 👤 Author & License

- **Author**: Soumyadeep Nath ([@sdn9300](https://github.com/sdn9300))
- **Architecture**: #6 — Coordination Layer, AI-Native Job Agent System
- **License**: [MIT License](LICENSE)
