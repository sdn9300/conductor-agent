"""
Configuration management for Conductor Agent.
Loads settings from environment variables or .env file.
"""

import os
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

# Load local or workspace .env if present
load_dotenv()


class ConductorConfig:
    """Runtime configuration for Conductor Agent."""

    def __init__(self, env_path: Optional[str] = None):
        if env_path:
            load_dotenv(env_path, override=True)

        # Candidate Defaults
        self.CANDIDATE_ID: str = os.getenv("CANDIDATE_ID", "sdn9300")
        self.CANDIDATE_NAME: str = os.getenv("CANDIDATE_NAME", "Soumyadeep Nath")
        self.CANDIDATE_EMAIL: str = os.getenv("CANDIDATE_EMAIL", "soumyadeepnath@example.com")
        self.CANDIDATE_PHONE: str = os.getenv("CANDIDATE_PHONE", "+1 (555) 019-2834")
        self.CANDIDATE_PORTFOLIO: str = os.getenv("CANDIDATE_PORTFOLIO", "https://github.com/sdn9300")
        self.DEFAULT_RESUME_PATH: str = os.getenv(
            "DEFAULT_RESUME_PATH",
            str(Path(__file__).resolve().parent.parent / "data" / "master_resume.txt"),
        )

        # Storage
        self.STORAGE_TYPE: str = os.getenv("STORAGE_TYPE", "sqlite")  # "sqlite" or "json"
        self.MEMORY_BACKEND: str = os.getenv("MEMORY_BACKEND", "event_sourced")  # "event_sourced" or "legacy"
        self.SQLITE_DB_PATH: str = os.getenv(
            "SQLITE_DB_PATH",
            str(Path(__file__).resolve().parent.parent / "data" / "conductor_memory.db"),
        )
        self.JSON_LOG_PATH: str = os.getenv(
            "JSON_LOG_PATH",
            str(Path(__file__).resolve().parent.parent / "data" / "conductor_run_log.json"),
        )
        self.MEMORY_MODULE_DIR: str = os.getenv(
            "MEMORY_MODULE_DIR",
            str(Path(__file__).resolve().parent.parent.parent / "Memory Module"),
        )
        self.MEMORY_MODULE_DB_PATH: str = os.getenv(
            "MEMORY_MODULE_DB_PATH",
            str(Path(__file__).resolve().parent.parent / "data" / "memory_module.db"),
        )

        # Gleaner Adapter (Job Scraping #1)
        self.HARVESTER_DIR: str = os.getenv(
            "HARVESTER_DIR",
            str(Path(__file__).resolve().parent.parent.parent / "Job Scraping"),
        )
        self.HARVESTER_DEFAULT_BOARDS: str = os.getenv(
            "HARVESTER_DEFAULT_BOARDS", "remoteok,indeed,wellfound,naukri"
        )
        self.HARVESTER_DEFAULT_ROLE: str = os.getenv("HARVESTER_DEFAULT_ROLE", "AI Engineer")
        self.HARVESTER_DEFAULT_LOCATION: str = os.getenv("HARVESTER_DEFAULT_LOCATION", "Remote")
        self.HARVESTER_MAX_LIMIT: int = int(os.getenv("HARVESTER_MAX_LIMIT", "20"))

        # Research Agent Adapter (Research-Agent #4)
        self.RESEARCH_AGENT_DIR: str = os.getenv(
            "RESEARCH_AGENT_DIR",
            str(Path(__file__).resolve().parent.parent.parent / "Research-Agent"),
        )

        # AlignResume Adapter (#2)
        self.ALIGN_RESUME_URL: str = os.getenv("ALIGN_RESUME_URL", "http://localhost:3000")
        self.ALIGN_RESUME_TIMEOUT: float = float(os.getenv("ALIGN_RESUME_TIMEOUT", "30.0"))
        self.ALIGN_RESUME_MAX_RETRIES: int = int(os.getenv("ALIGN_RESUME_MAX_RETRIES", "2"))
        self.GROQ_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY")

        # Overture Adapter (Cold Email Agent #3)
        self.OVERTURE_DIR: str = os.getenv(
            "OVERTURE_DIR",
            str(Path(__file__).resolve().parent.parent.parent / "cold-email-agent"),
        )
        self.DRY_RUN: bool = os.getenv("DRY_RUN", "true").lower() in ("true", "1", "yes")
        self.EMAIL_METHOD: str = os.getenv("EMAIL_METHOD", "gmail_api")  # "gmail_api" or "smtp"

        # PDF Auto-Apply Adapter (#5 / Usher #7)
        self.PDF_OUTPUT_DIR: str = os.getenv(
            "PDF_OUTPUT_DIR",
            str(Path(__file__).resolve().parent.parent / "data" / "pdf_resumes"),
        )
        self.USHER_DIR: str = os.getenv(
            "USHER_DIR",
            str(Path(__file__).resolve().parent.parent.parent / "PDF Auto Apply Agent"),
        )
        self.DEFAULT_CHANNEL: str = os.getenv("DEFAULT_CHANNEL", "auto")  # "auto" | "email" | "form"

        # Sentiment Classifier Adapter (Sentiment-Analysis #9)
        self.SENTIMENT_CLASSIFIER_DIR: str = os.getenv(
            "SENTIMENT_CLASSIFIER_DIR",
            str(Path(__file__).resolve().parent.parent.parent / "Sentiment-Analysis"),
        )
        self.COOLDOWN_DAYS: int = int(os.getenv("COOLDOWN_DAYS", "30"))

        # Human-in-the-loop Gate
        self.AUTO_APPROVE: bool = os.getenv("AUTO_APPROVE", "false").lower() in ("true", "1", "yes")

        # Metrics / Prometheus
        self.METRICS_ENABLED: bool = os.getenv("METRICS_ENABLED", "true").lower() in ("true", "1", "yes")
        self.PROMETHEUS_PORT: int = int(os.getenv("PROMETHEUS_PORT", "8001"))


# Global default configuration instance
config = ConductorConfig()
