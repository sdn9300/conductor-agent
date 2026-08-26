"""
Base MemoryStore interface for Conductor Agent.
Implements ADR-2 from CND-ARCH: pluggable store interface that provides
durable persistence, deduplication, and sentiment feedback loop updates.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from conductor.state import ApplicationRecord, CandidateProfile, SentimentSignal


class MemoryStore(ABC):
    """Abstract interface for storing and retrieving Conductor run and candidate records."""

    @abstractmethod
    def save_application(self, record: ApplicationRecord) -> bool:
        """
        Persist or update an application run record.
        Must never drop errors silently — return True on success, raise or return False on failure.
        """
        pass

    @abstractmethod
    def get_application(self, job_id: str) -> Optional[ApplicationRecord]:
        """Retrieve an application record by its job_id."""
        pass

    @abstractmethod
    def find_latest_application_by_company(self, company: str) -> Optional[ApplicationRecord]:
        """Retrieve the most recent application record for a given company name."""
        pass

    @abstractmethod
    def list_applications(self, limit: int = 50, status: Optional[str] = None) -> List[ApplicationRecord]:
        """List application records, optionally filtered by status."""
        pass

    @abstractmethod
    def is_duplicate_posting(
        self,
        link: Optional[str] = None,
        company: Optional[str] = None,
        title: Optional[str] = None,
    ) -> bool:
        """
        Check if a posting was already ingested or processed (EC-06 & Task 2.4).
        Matches on URL/link or (company + title) combination.
        """
        pass

    @abstractmethod
    def is_company_in_cooldown(self, company: str, cooldown_days: int = 30) -> bool:
        """
        Check if outreach to this company was recently rejected or sent (EC-07 & Task 3.3).
        Suppresses outreach if a soft/hard rejection or negative signal occurred within cooldown.
        """
        pass

    @abstractmethod
    def record_inbound_response(
        self,
        target_id_or_company: str,
        signal: SentimentSignal,
    ) -> Optional[ApplicationRecord]:
        """
        Ingest sentiment signal from inbound response, attach to application, and update status.
        """
        pass

    @abstractmethod
    def save_candidate_profile(self, profile: CandidateProfile) -> bool:
        """Persist canonical candidate profile."""
        pass

    @abstractmethod
    def get_candidate_profile(self, candidate_id: str = "sdn9300") -> Optional[CandidateProfile]:
        """Retrieve candidate profile."""
        pass
