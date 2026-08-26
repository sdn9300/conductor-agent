"""
Local MemoryStore implementations (SQLite & JSON append-only).
Satisfies ADR-2 (local pluggable storage), ADR-4 (no-silent-drop),
EC-06 (deduplication), and EC-07 (sentiment rejection cooldown).
"""

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional

from conductor.state import ApplicationRecord, CandidateProfile, SentimentSignal
from conductor.storage.base import MemoryStore


class SQLiteMemoryStore(MemoryStore):
    """SQLite-backed persistent store for Conductor applications and profiles."""

    def __init__(self, db_path: str = "data/conductor_memory.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _execute(self, func):
        """Execute a callable with a freshly managed connection that is always closed."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                return func(conn)
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Initialize tables for applications and profiles with migration checks."""
        def init_fn(conn: sqlite3.Connection):
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS applications (
                    job_id TEXT PRIMARY KEY,
                    company TEXT NOT NULL,
                    title TEXT NOT NULL,
                    link TEXT,
                    status TEXT NOT NULL,
                    data JSON NOT NULL,
                    created_at TEXT NOT NULL,
                    last_updated TEXT NOT NULL
                )
            """)
            # Migration check: ensure 'link' column exists if upgrading from v0.1
            cursor.execute("PRAGMA table_info(applications)")
            columns = [col["name"] for col in cursor.fetchall()]
            if "link" not in columns:
                cursor.execute("ALTER TABLE applications ADD COLUMN link TEXT")

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_company ON applications(company);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON applications(status);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_link ON applications(link);
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS candidate_profiles (
                    candidate_id TEXT PRIMARY KEY,
                    data JSON NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
        self._execute(init_fn)

    def save_application(self, record: ApplicationRecord) -> bool:
        """Persist application record as JSON document with indexed columns."""
        def save_fn(conn: sqlite3.Connection):
            raw_json = record.model_dump_json()
            created_at = record.timestamps.get("discovered", datetime.now(timezone.utc).isoformat())
            last_updated = record.timestamps.get("last_updated", datetime.now(timezone.utc).isoformat())
            link = record.posting.url or ""

            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO applications (job_id, company, title, link, status, data, created_at, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    company = excluded.company,
                    title = excluded.title,
                    link = excluded.link,
                    status = excluded.status,
                    data = excluded.data,
                    last_updated = excluded.last_updated
            """, (
                record.job_id,
                record.posting.company,
                record.posting.title,
                link,
                record.status,
                raw_json,
                created_at,
                last_updated,
            ))
            return True

        try:
            return self._execute(save_fn)
        except Exception as e:
            print(f"[SQLiteMemoryStore ERROR] Failed to save application {record.job_id}: {e}")
            raise e

    def get_application(self, job_id: str) -> Optional[ApplicationRecord]:
        """Retrieve single application record by job_id."""
        def get_fn(conn: sqlite3.Connection):
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM applications WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            if row:
                data_dict = json.loads(row["data"])
                return ApplicationRecord.model_validate(data_dict)
            return None

        return self._execute(get_fn)

    def find_latest_application_by_company(self, company: str) -> Optional[ApplicationRecord]:
        """Retrieve the most recent application record for a given company name."""
        def find_fn(conn: sqlite3.Connection):
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data FROM applications WHERE LOWER(company) = LOWER(?) ORDER BY last_updated DESC LIMIT 1",
                (company.strip(),)
            )
            row = cursor.fetchone()
            if row:
                return ApplicationRecord.model_validate(json.loads(row["data"]))
            return None

        return self._execute(find_fn)

    def list_applications(self, limit: int = 50, status: Optional[str] = None) -> List[ApplicationRecord]:
        """List application records ordered by last_updated desc."""
        def list_fn(conn: sqlite3.Connection):
            cursor = conn.cursor()
            if status:
                cursor.execute(
                    "SELECT data FROM applications WHERE status = ? ORDER BY last_updated DESC LIMIT ?",
                    (status, limit)
                )
            else:
                cursor.execute(
                    "SELECT data FROM applications ORDER BY last_updated DESC LIMIT ?",
                    (limit,)
                )
            rows = cursor.fetchall()
            return [ApplicationRecord.model_validate(json.loads(r["data"])) for r in rows]

        return self._execute(list_fn)

    def is_duplicate_posting(
        self,
        link: Optional[str] = None,
        company: Optional[str] = None,
        title: Optional[str] = None,
    ) -> bool:
        """Check if posting URL or (company + title) already exists in store."""
        def check_fn(conn: sqlite3.Connection):
            cursor = conn.cursor()
            if link and link.strip():
                cursor.execute(
                    "SELECT COUNT(*) as cnt FROM applications WHERE link = ? AND status NOT IN ('skipped_duplicate', 'skipped_cooldown')",
                    (link.strip(),)
                )
                if cursor.fetchone()["cnt"] > 0:
                    return True

            if company and title:
                cursor.execute("""
                    SELECT COUNT(*) as cnt FROM applications 
                    WHERE LOWER(company) = LOWER(?) 
                    AND LOWER(title) = LOWER(?)
                    AND status NOT IN ('skipped_duplicate', 'skipped_cooldown')
                """, (company.strip(), title.strip()))
                if cursor.fetchone()["cnt"] > 0:
                    return True

            return False

        return self._execute(check_fn)

    def is_company_in_cooldown(self, company: str, cooldown_days: int = 30) -> bool:
        """
        Check if company was recently reached out to or closed/rejected within cooldown days.
        (Task 3.3 & EC-07).
        """
        def cooldown_fn(conn: sqlite3.Connection):
            cutoff = (datetime.now(timezone.utc) - timedelta(days=cooldown_days)).isoformat()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT data FROM applications 
                WHERE LOWER(company) = LOWER(?) 
                AND last_updated >= ?
            """, (company.strip(), cutoff))
            rows = cursor.fetchall()

            for row in rows:
                app_data = json.loads(row["data"])
                status = app_data.get("status", "")
                sentiment = app_data.get("sentiment_signal") or {}

                # Suppression triggers:
                # 1. Outreach already sent within cooldown window
                if status in ("outreach_sent", "outreach_approved"):
                    return True
                # 2. Hard or soft rejection
                if sentiment.get("intent_label") in ("hard_rejection", "soft_rejection"):
                    return True
                # 3. Negative sentiment or closed
                if sentiment.get("macro_sentiment") == "negative" or status == "closed":
                    return True

            return False

        return self._execute(cooldown_fn)

    def record_inbound_response(
        self,
        target_id_or_company: str,
        signal: SentimentSignal,
    ) -> Optional[ApplicationRecord]:
        """Attach inbound sentiment signal to application and transition status."""
        app = self.get_application(target_id_or_company)
        if not app:
            app = self.find_latest_application_by_company(target_id_or_company)

        if not app:
            return None

        app.sentiment_signal = signal
        if signal.intent_label in ("hard_rejection", "soft_rejection"):
            app.status = "closed"
        elif signal.intent_label in ("interview_invite", "scheduling_link"):
            app.status = "interview_scheduled"
        else:
            app.status = "responded"

        app.update_timestamp("responded")
        self.save_application(app)
        return app

    def save_candidate_profile(self, profile: CandidateProfile) -> bool:
        """Persist candidate profile."""
        def save_profile_fn(conn: sqlite3.Connection):
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO candidate_profiles (candidate_id, data, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                    data = excluded.data,
                    updated_at = excluded.updated_at
            """, (
                profile.candidate_id,
                profile.model_dump_json(),
                datetime.now(timezone.utc).isoformat()
            ))
            return True

        return self._execute(save_profile_fn)

    def get_candidate_profile(self, candidate_id: str = "sdn9300") -> Optional[CandidateProfile]:
        """Retrieve candidate profile."""
        def get_profile_fn(conn: sqlite3.Connection):
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM candidate_profiles WHERE candidate_id = ?", (candidate_id,))
            row = cursor.fetchone()
            if row:
                return CandidateProfile.model_validate(json.loads(row["data"]))
            return None

        return self._execute(get_profile_fn)


class JSONMemoryStore(MemoryStore):
    """Append-only JSON flat-file storage for lightweight or portable runs."""

    def __init__(self, file_path: str = "data/conductor_run_log.json"):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self._write_records([])

    def _read_records(self) -> List[dict]:
        try:
            if not self.file_path.exists():
                return []
            with open(self.file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return []
                return json.loads(content)
        except Exception:
            return []

    def _write_records(self, records: List[dict]) -> None:
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)

    def save_application(self, record: ApplicationRecord) -> bool:
        records = self._read_records()
        if "last_updated" not in record.timestamps:
            record.update_timestamp("last_updated")
        record_dict = record.model_dump(mode="json")
        idx = next((i for i, r in enumerate(records) if r.get("job_id") == record.job_id), None)
        if idx is not None:
            records[idx] = record_dict
        else:
            records.append(record_dict)
        self._write_records(records)
        return True

    def get_application(self, job_id: str) -> Optional[ApplicationRecord]:
        records = self._read_records()
        match = next((r for r in records if r.get("job_id") == job_id), None)
        if match:
            return ApplicationRecord.model_validate(match)
        return None

    def find_latest_application_by_company(self, company: str) -> Optional[ApplicationRecord]:
        records = self._read_records()
        norm_co = company.strip().lower()
        for r in reversed(records):
            if r.get("posting", {}).get("company", "").strip().lower() == norm_co:
                return ApplicationRecord.model_validate(r)
        return None

    def list_applications(self, limit: int = 50, status: Optional[str] = None) -> List[ApplicationRecord]:
        records = self._read_records()
        if status:
            records = [r for r in records if r.get("status") == status]
        return [ApplicationRecord.model_validate(r) for r in records[-limit:]]

    def is_duplicate_posting(
        self,
        link: Optional[str] = None,
        company: Optional[str] = None,
        title: Optional[str] = None,
    ) -> bool:
        records = self._read_records()
        norm_link = (link or "").strip()
        norm_co = (company or "").strip().lower()
        norm_title = (title or "").strip().lower()

        for r in records:
            if r.get("status") in ("skipped_duplicate", "skipped_cooldown"):
                continue
            posting = r.get("posting", {})
            p_url = (posting.get("url") or "").strip()
            p_co = (posting.get("company") or "").strip().lower()
            p_title = (posting.get("title") or "").strip().lower()

            if norm_link and norm_link == p_url:
                return True
            if norm_co and norm_title and norm_co == p_co and norm_title == p_title:
                return True
        return False

    def is_company_in_cooldown(self, company: str, cooldown_days: int = 30) -> bool:
        records = self._read_records()
        cutoff = datetime.now(timezone.utc) - timedelta(days=cooldown_days)
        norm_co = company.strip().lower()

        for r in records:
            posting = r.get("posting", {})
            if posting.get("company", "").strip().lower() == norm_co:
                timestamps = r.get("timestamps", {})
                ts_str = timestamps.get("last_updated") or timestamps.get("discovered")
                if ts_str:
                    try:
                        ts = datetime.fromisoformat(ts_str)
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                        if ts >= cutoff:
                            status = r.get("status", "")
                            sentiment = r.get("sentiment_signal") or {}
                            if status in ("outreach_sent", "outreach_approved", "closed"):
                                return True
                            if sentiment.get("intent_label") in ("hard_rejection", "soft_rejection"):
                                return True
                            if sentiment.get("macro_sentiment") == "negative":
                                return True
                    except Exception:
                        pass
        return False

    def record_inbound_response(
        self,
        target_id_or_company: str,
        signal: SentimentSignal,
    ) -> Optional[ApplicationRecord]:
        app = self.get_application(target_id_or_company)
        if not app:
            app = self.find_latest_application_by_company(target_id_or_company)

        if not app:
            return None

        app.sentiment_signal = signal
        if signal.intent_label in ("hard_rejection", "soft_rejection"):
            app.status = "closed"
        elif signal.intent_label in ("interview_invite", "scheduling_link"):
            app.status = "interview_scheduled"
        else:
            app.status = "responded"

        app.update_timestamp("responded")
        self.save_application(app)
        return app

    def save_candidate_profile(self, profile: CandidateProfile) -> bool:
        profile_path = self.file_path.parent / f"profile_{profile.candidate_id}.json"
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(profile.model_dump_json(indent=2))
        return True

    def get_candidate_profile(self, candidate_id: str = "sdn9300") -> Optional[CandidateProfile]:
        profile_path = self.file_path.parent / f"profile_{candidate_id}.json"
        if profile_path.exists():
            with open(profile_path, "r", encoding="utf-8") as f:
                return CandidateProfile.model_validate_json(f.read())
        return None
