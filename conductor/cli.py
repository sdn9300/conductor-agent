"""
Command Line Interface for Conductor Agent.
Provides commands for running single or batch job orchestrations, live harvesting,
daemon scheduling, Tier-0 baseline optimization, ingesting inbound responses, inspecting history, and metrics.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, List
from uuid import uuid4

from conductor.adapters.harvester import HarvesterAdapter
from conductor.adapters.sentiment import SentimentClassifierAdapter
from conductor.config import config
from conductor.graph.nodes import NodeContext, execute_tier0_baseline
from conductor.graph.workflow import build_conductor_graph
from conductor.metrics import start_conductor_metrics_server
from conductor.state import ApplicationRecord, ConductorState, PostingRef
from conductor.storage.local_store import SQLiteMemoryStore, JSONMemoryStore


def get_store():
    """Retrieve configured MemoryStore."""
    if config.STORAGE_TYPE == "json":
        return JSONMemoryStore(config.JSON_LOG_PATH)
    return SQLiteMemoryStore(config.SQLITE_DB_PATH)


def load_master_resume(custom_path: Optional[str] = None) -> str:
    """Load master resume text from custom path or default."""
    path = Path(custom_path or config.DEFAULT_RESUME_PATH)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return (
        "Soumyadeep Nath — AI & Agentic Systems Engineer\n"
        "Specializing in LangGraph multi-agent orchestration, LLM pipelines, and backend Python architectures."
    )


def handle_run(args: argparse.Namespace) -> None:
    """Execute end-to-end orchestration for a single job posting."""
    jd_text = ""
    if args.jd_file:
        path = Path(args.jd_file)
        if not path.exists():
            print(f"[Error] JD file not found: {args.jd_file}")
            sys.exit(1)
        with open(path, "r", encoding="utf-8") as f:
            jd_text = f.read().strip()
    elif args.jd_text:
        jd_text = args.jd_text.strip()
    else:
        print("[Error] Either --jd-file or --jd-text must be provided.")
        sys.exit(1)

    master_resume = load_master_resume(args.resume_file)

    if args.dry_run is not None:
        config.DRY_RUN = args.dry_run

    if config.METRICS_ENABLED:
        start_conductor_metrics_server(config.PROMETHEUS_PORT)

    posting = PostingRef(
        company=args.company,
        title=args.role,
        jd_text=jd_text,
        url=args.url,
        contact_email=args.contact_email,
        contact_name=args.contact_name,
        application_channel=args.channel,
    )

    job_id = str(uuid4())
    app_record = ApplicationRecord(
        job_id=job_id,
        source="manual",
        posting=posting,
        status="discovered",
    )

    initial_state = ConductorState(
        candidate_id=config.CANDIDATE_ID,
        job_id=job_id,
        application=app_record,
        master_resume_text=master_resume,
        target_channel=args.channel,
    )

    if args.auto_approve:
        config.AUTO_APPROVE = True

    print(f"\n=======================================================")
    print(f"  CONDUCTOR ORCHESTRATION PIPELINE")
    print(f"=======================================================")
    print(f"  Job ID:     {job_id}")
    print(f"  Company:    {posting.company}")
    print(f"  Role:       {posting.title}")
    print(f"  Channel:    {args.channel.upper()}")
    print(f"  Dry Run:    {config.DRY_RUN}")
    print(f"  Storage:    {config.STORAGE_TYPE}")
    print(f"=======================================================\n")

    store = get_store()
    ctx = NodeContext(memory_store=store)
    app = build_conductor_graph(ctx)

    final_output = app.invoke(initial_state)
    final_state = (
        final_output
        if isinstance(final_output, ConductorState)
        else ConductorState.model_validate(final_output)
    )

    print("\n=======================================================")
    print(f"  RUN COMPLETED - Status: {final_state.application.status.upper()}")
    print(f"  Trace: {' -> '.join(final_state.node_trace)}")
    if final_state.errors:
        print(f"  Errors: {final_state.errors}")
    print(f"=======================================================\n")


def handle_harvest(args: argparse.Namespace) -> None:
    """Discover opportunities via Harvester and orchestrate them in batch."""
    if args.dry_run is not None:
        config.DRY_RUN = args.dry_run
    if args.auto_approve:
        config.AUTO_APPROVE = True

    if config.METRICS_ENABLED:
        start_conductor_metrics_server(config.PROMETHEUS_PORT)

    boards = [b.strip() for b in args.boards.split(",") if b.strip()] if args.boards else None
    role = args.role or config.HARVESTER_DEFAULT_ROLE
    location = args.location or config.HARVESTER_DEFAULT_LOCATION
    limit = args.limit or config.HARVESTER_MAX_LIMIT

    print(f"\n=======================================================")
    print(f"  CONDUCTOR HARVEST & ORCHESTRATION BATCH")
    print(f"=======================================================")
    print(f"  Search Role:     {role}")
    print(f"  Location:        {location}")
    print(f"  Target Limit:    {limit}")
    print(f"  Boards:          {boards or config.HARVESTER_DEFAULT_BOARDS}")
    print(f"  Channel Mode:    {args.channel.upper()}")
    print(f"  Dry Run:         {config.DRY_RUN}")
    print(f"=======================================================\n")

    harvester = HarvesterAdapter()
    print("  [1/2] Discovering postings across job boards...")
    discovered = harvester.fetch_jobs(role=role, location=location, boards=boards, limit=limit)
    print(f"  Found {len(discovered)} opportunity listing(s).\n")

    if not discovered:
        print("  No job postings discovered. Exiting.")
        return

    store = get_store()
    master_resume = load_master_resume(args.resume_file)
    ctx = NodeContext(memory_store=store)
    graph = build_conductor_graph(ctx)

    results_summary = []

    print("  [2/2] Orchestrating discovered jobs through Conductor pipeline...\n")
    for idx, posting in enumerate(discovered, start=1):
        print(f"  -- Job #{idx}: {posting.company} - {posting.title} --")
        job_id = str(uuid4())
        posting.application_channel = args.channel
        app_record = ApplicationRecord(
            job_id=job_id,
            source=posting.source,
            posting=posting,
            status="discovered",
        )
        state = ConductorState(
            candidate_id=config.CANDIDATE_ID,
            job_id=job_id,
            application=app_record,
            master_resume_text=master_resume,
            target_channel=args.channel,
        )

        res = graph.invoke(state)
        final_state = res if isinstance(res, ConductorState) else ConductorState.model_validate(res)

        status = final_state.application.status
        print(f"     Status: {status.upper()} | Trace: {' -> '.join(final_state.node_trace)}")
        results_summary.append({
            "company": posting.company,
            "title": posting.title,
            "status": status,
            "job_id": job_id,
        })

    # Summary table
    print("\n=======================================================")
    print("  HARVEST BATCH EXECUTION SUMMARY")
    print("=======================================================")
    print(f"{'COMPANY':<22} {'ROLE':<25} {'STATUS':<20} {'JOB ID'}")
    print("-" * 105)
    for item in results_summary:
        print(f"{item['company']:<22} {item['title']:<25} {item['status']:<20} {item['job_id']}")
    print("=======================================================\n")


def handle_baseline(args: argparse.Namespace) -> None:
    """Run Tier-0 Baseline Optimization Pass for target role (ADR-1)."""
    role = args.role or "AI Engineer"
    master_resume = load_master_resume(args.resume_file)
    store = get_store()
    ctx = NodeContext(memory_store=store)

    print(f"\n=======================================================")
    print(f"  CONDUCTOR TIER-0 BASELINE OPTIMIZATION (ADR-1)")
    print(f"=======================================================")
    print(f"  Target Role: {role}")
    print(f"  Candidate:   {config.CANDIDATE_NAME} ({config.CANDIDATE_ID})")
    print(f"=======================================================\n")

    print(f"  Optimizing master resume baseline against standard '{role}' market criteria...")
    res = execute_tier0_baseline(role=role, master_resume_text=master_resume, context=ctx)

    if res.get("success"):
        opt = res["optimization"]
        print(f"\n  [SUCCESS] Baseline profile updated for '{role}'.")
        print(f"  Match Score:    {opt.get('match_score')}%")
        print(f"  Skills Matched: {', '.join(opt.get('skills_matched', []))}")
        print(f"  Timestamp:      {opt.get('updated_at')}")
    else:
        print(f"\n  [FAILURE] Baseline optimization error: {res.get('error')}")
    print()


def handle_daemon(args: argparse.Namespace) -> None:
    """Run Conductor in autonomous scheduled daemon mode (Phase 5)."""
    from conductor.scheduler import ConductorDaemon

    daemon = ConductorDaemon(
        interval_seconds=args.interval_seconds,
        role=args.role,
        location=args.location,
        limit=args.limit,
        channel=args.channel,
        dry_run=args.dry_run if args.dry_run is not None else config.DRY_RUN,
        auto_approve=args.auto_approve or config.AUTO_APPROVE,
        max_iterations=args.max_iterations,
    )
    daemon.start()


def handle_ingest_response(args: argparse.Namespace) -> None:
    """Ingest, classify, and update memory with an inbound recruiter response (Phase 3)."""
    raw_text = ""
    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"[Error] Response file not found: {args.file}")
            sys.exit(1)
        with open(path, "r", encoding="utf-8") as f:
            raw_text = f.read().strip()
    elif args.text:
        raw_text = args.text.strip()
    else:
        print("[Error] Either --text or --file must be provided.")
        sys.exit(1)

    target_id = args.job_id or args.company
    if not target_id:
        print("[Error] Either --job-id or --company must be specified to link response.")
        sys.exit(1)

    store = get_store()
    company = args.company
    role = args.role or "AI Engineer"

    if args.job_id:
        app = store.get_application(args.job_id)
        if app:
            company = company or app.posting.company
            role = role or app.posting.title

    company = company or target_id

    print(f"\n=======================================================")
    print(f"  CONDUCTOR INBOUND RESPONSE CLASSIFIER (PHASE 3)")
    print(f"=======================================================")
    print(f"  Target Company: {company}")
    print(f"  Role:           {role}")
    print(f"  Target Ref:     {target_id}")
    print(f"=======================================================\n")

    adapter = SentimentClassifierAdapter()
    print("  Classifying response with Sentiment Classifier (#9)...")
    signal = adapter.classify_response(
        raw_text=raw_text,
        company=company,
        role=role,
        application_id=args.job_id,
    )

    print(f"\n  [CLASSIFICATION RESULT]")
    print(f"  Macro Sentiment:    {signal.macro_sentiment.upper()}")
    print(f"  Intent Label:       {signal.intent_label}")
    print(f"  Urgency Score:      {signal.urgency_score}/5")
    print(f"  Confidence:         {signal.confidence * 100:.1f}%")
    print(f"  Recommended Action: {signal.recommended_action}")
    if signal.key_phrases:
        print(f"  Key Phrases:        {', '.join(signal.key_phrases)}")

    # Update MemoryStore
    updated_app = store.record_inbound_response(target_id, signal)
    if updated_app:
        print(f"\n  [MEMORY UPDATED]")
        print(f"  Job ID:             {updated_app.job_id}")
        print(f"  New Status:         {updated_app.status.upper()}")
        if updated_app.status == "closed":
            print(f"  [FEEDBACK COOLDOWN] Outreach to '{company}' is now SUPPRESSED for {config.COOLDOWN_DAYS} days.")
    else:
        print(f"\n  [Warning] No existing application found matching '{target_id}'. Record not linked.")

    print("\n=======================================================")


def handle_history(args: argparse.Namespace) -> None:
    """List historical application runs."""
    store = get_store()
    records = store.list_applications(limit=args.limit, status=args.status)
    if not records:
        print("\nNo application runs found in memory store.\n")
        return

    print(f"\n{'JOB ID':<38} {'COMPANY':<20} {'ROLE':<25} {'STATUS':<20} {'LAST UPDATED'}")
    print("-" * 125)
    for r in records:
        ts = r.timestamps.get("last_updated", r.timestamps.get("discovered", "N/A"))
        print(f"{r.job_id:<38} {r.posting.company:<20} {r.posting.title:<25} {r.status:<20} {ts}")
    print()


def handle_inspect(args: argparse.Namespace) -> None:
    """Inspect detailed state of a single job opportunity."""
    store = get_store()
    rec = store.get_application(args.job_id)
    if not rec:
        print(f"\n[Error] Application with job_id '{args.job_id}' not found.\n")
        return

    print(json.dumps(rec.model_dump(mode="json"), indent=2))


def main() -> None:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="conductor",
        description="Conductor Agent — Coordination Layer for AI-Native Job Agent System",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: run
    run_p = subparsers.add_parser("run", help="Orchestrate a single job opportunity")
    run_p.add_argument("--company", required=True, help="Target company name")
    run_p.add_argument("--role", required=True, help="Target job role")
    run_p.add_argument("--jd-file", help="Path to text file containing the job description")
    run_p.add_argument("--jd-text", help="Raw job description text string")
    run_p.add_argument("--url", help="Job posting URL")
    run_p.add_argument("--contact-email", help="Recruiter / contact email")
    run_p.add_argument("--contact-name", help="Recruiter / contact name")
    run_p.add_argument("--channel", choices=["auto", "email", "form"], default="auto", help="Application dispatch channel")
    run_p.add_argument("--resume-file", help="Path to custom master resume text file")
    run_p.add_argument("--dry-run", action="store_true", default=None, help="Force dry run mode")
    run_p.add_argument("--auto-approve", action="store_true", help="Automatically approve human gate")

    # Command: harvest
    harv_p = subparsers.add_parser("harvest", help="Scrape live jobs and orchestrate batch")
    harv_p.add_argument("--role", default="AI Engineer", help="Role search query")
    harv_p.add_argument("--location", default="Remote", help="Location search query")
    harv_p.add_argument("--boards", help="Comma-separated boards (remoteok,indeed,wellfound,naukri)")
    harv_p.add_argument("--limit", type=int, default=5, help="Max jobs to harvest & process")
    harv_p.add_argument("--channel", choices=["auto", "email", "form"], default="auto", help="Application dispatch channel")
    harv_p.add_argument("--resume-file", help="Path to master resume file")
    harv_p.add_argument("--dry-run", action="store_true", default=None, help="Force dry run mode")
    harv_p.add_argument("--auto-approve", action="store_true", help="Automatically approve human gate")

    # Command: daemon (Phase 5)
    daem_p = subparsers.add_parser("daemon", help="Run autonomous scheduled daemon and metrics exporter")
    daem_p.add_argument("--interval-seconds", type=int, default=3600, help="Interval between harvest cycles in seconds")
    daem_p.add_argument("--max-iterations", type=int, default=None, help="Stop after N cycles (for testing)")
    daem_p.add_argument("--role", default="AI Engineer", help="Target role for scheduled harvesting")
    daem_p.add_argument("--location", default="Remote", help="Target location")
    daem_p.add_argument("--limit", type=int, default=5, help="Jobs per harvest cycle")
    daem_p.add_argument("--channel", choices=["auto", "email", "form"], default="auto", help="Channel mode")
    daem_p.add_argument("--dry-run", action="store_true", default=None, help="Force dry run mode")
    daem_p.add_argument("--auto-approve", action="store_true", default=True, help="Auto approve in daemon mode")

    # Command: baseline (Tier-0)
    base_p = subparsers.add_parser("baseline", help="Execute Tier-0 master resume baseline pass (ADR-1)")
    base_p.add_argument("--role", default="AI Engineer", help="Target role to optimize against")
    base_p.add_argument("--resume-file", help="Path to master resume file")

    # Command: ingest-response (Phase 3)
    ingest_p = subparsers.add_parser("ingest-response", help="Ingest and classify inbound recruiter response")
    ingest_p.add_argument("--text", help="Inbound response text string")
    ingest_p.add_argument("--file", help="Path to text file containing inbound response")
    ingest_p.add_argument("--job-id", help="Target application job_id")
    ingest_p.add_argument("--company", help="Target company name")
    ingest_p.add_argument("--role", help="Target role name")

    # Command: history
    hist_p = subparsers.add_parser("history", help="List past application runs")
    hist_p.add_argument("--limit", type=int, default=20, help="Max records to display")
    hist_p.add_argument("--status", help="Filter by application status")

    # Command: inspect
    insp_p = subparsers.add_parser("inspect", help="Inspect detailed JSON state of a job")
    insp_p.add_argument("--job-id", required=True, help="Application job_id")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "run":
        handle_run(args)
    elif args.command == "harvest":
        handle_harvest(args)
    elif args.command == "daemon":
        handle_daemon(args)
    elif args.command == "baseline":
        handle_baseline(args)
    elif args.command == "ingest-response":
        handle_ingest_response(args)
    elif args.command == "history":
        handle_history(args)
    elif args.command == "inspect":
        handle_inspect(args)


if __name__ == "__main__":
    main()
