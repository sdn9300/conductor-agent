"""
Autonomous Scheduler and Daemon Runner for Conductor Agent (#6).
Provides continuous scheduled harvesting, baseline maintenance, and Prometheus metrics hosting.
Satisfies Phase 5 production hardening and Kubernetes / container deployments.
"""

import argparse
import logging
import signal
import sys
import time
from typing import Optional

from conductor.config import config
from conductor.metrics import start_conductor_metrics_server
from conductor.storage.local_store import SQLiteMemoryStore, JSONMemoryStore

logger = logging.getLogger("conductor.scheduler")


class ConductorDaemon:
    """Autonomous scheduler daemon executing periodic pipeline cycles."""

    def __init__(
        self,
        interval_seconds: int = 3600,
        role: str = "AI Engineer",
        location: str = "Remote",
        limit: int = 5,
        channel: str = "auto",
        dry_run: bool = True,
        auto_approve: bool = True,
        max_iterations: Optional[int] = None,
    ):
        self.interval_seconds = interval_seconds
        self.role = role
        self.location = location
        self.limit = limit
        self.channel = channel
        self.dry_run = dry_run
        self.auto_approve = auto_approve
        self.max_iterations = max_iterations
        self._running = True
        self._iteration_count = 0

        # Setup graceful signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        print("\n[Daemon] Graceful shutdown signal received. Stopping scheduler...")
        self._running = False

    def run_tick(self) -> None:
        """Execute a single harvest and pipeline orchestration tick."""
        from conductor.cli import handle_harvest

        self._iteration_count += 1
        print(f"\n{'='*65}")
        print(f"  CONDUCTOR DAEMON TICK #{self._iteration_count}")
        print(f"  Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
        print(f"  Role:      {self.role} | Location: {self.location} | Limit: {self.limit}")
        print(f"{'='*65}\n")

        # Mock CLI args namespace for handle_harvest
        args = argparse.Namespace(
            role=self.role,
            location=self.location,
            boards=None,
            limit=self.limit,
            channel=self.channel,
            resume_file=None,
            dry_run=self.dry_run,
            auto_approve=self.auto_approve,
        )

        try:
            handle_harvest(args)
        except Exception as e:
            print(f"[Daemon Error] Exception during harvest tick: {e}")

    def start(self) -> None:
        """Start the long-running daemon loop and metrics server."""
        if config.METRICS_ENABLED:
            start_conductor_metrics_server(config.PROMETHEUS_PORT)

        print(f"\n=======================================================")
        print(f"  CONDUCTOR AGENT DAEMON INITIALIZED")
        print(f"=======================================================")
        print(f"  Interval:       {self.interval_seconds}s")
        print(f"  Prometheus:     http://0.0.0.0:{config.PROMETHEUS_PORT}/metrics")
        print(f"  Storage:        {config.STORAGE_TYPE} ({config.SQLITE_DB_PATH})")
        print(f"  Role / Target:  {self.role} ({self.location})")
        print(f"  Max Iterations: {self.max_iterations or 'Infinite'}")
        print(f"=======================================================\n")

        while self._running:
            self.run_tick()

            if self.max_iterations and self._iteration_count >= self.max_iterations:
                print(f"[Daemon] Reached max iterations ({self.max_iterations}). Exiting cleanly.")
                break

            print(f"[Daemon] Sleeping for {self.interval_seconds} seconds until next cycle...\n")
            # Sleep in 1-second slices for immediate SIGINT response
            for _ in range(self.interval_seconds):
                if not self._running:
                    break
                time.sleep(1)

        print("[Daemon] Conductor daemon stopped.")
