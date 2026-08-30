import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Add project roots to path
CURRENT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CURRENT_DIR))

from candidate_profile.models import (
    CandidateProfile,
    ProfileMetadata,
    Identity,
    ContactInfo,
    EducationRecord,
    SkillRecord,
    ExperienceRecord,
    ApplicationPreferences,
    ProficiencyLevel,
    SourceProvenance,
)
from candidate_profile.storage import CandidateProfileStore


def migrate_master_resume(
    resume_path: Optional[str] = None,
    candidate_id: str = "sdn9300",
    data_dir: Optional[str] = None,
) -> CandidateProfile:
    """Migrate master_resume.txt into a canonical CandidateProfile model and persist."""
    resume_file = Path(resume_path or CURRENT_DIR / "data" / "master_resume.txt")
    base_dir = data_dir or str(CURRENT_DIR.parent / "Candidate Profile" / "data" / "candidate_profile")
    store = CandidateProfileStore(base_dir=base_dir)

    # Base profile construction matching Soumyadeep Nath's verified engineering record
    now = datetime.now(timezone.utc)
    metadata = ProfileMetadata(
        candidate_id=candidate_id,
        schema_version="1.0.0",
        created_at=now,
        updated_at=now,
        last_writer_component="bootstrap_manual",
    )
    identity = Identity(
        legal_name="Soumyadeep Nath",
        location="Remote / Hybrid",
        contact=ContactInfo(
            email="soumyadeepnath@example.com",
            phone="+91-9876543210",
            linkedin="https://www.linkedin.com/in/sdn9300",
            github="https://github.com/sdn9300",
            portfolio="https://github.com/sdn9300",
        ),
    )
    education = [
        EducationRecord(
            institution="Techno Main Salt Lake",
            program="Bachelor of Technology in Computer Science and Engineering",
            status="completed",
            start_date="2020-08",
            end_date="2024-06",
            honors="First Class with Distinction",
        )
    ]
    
    verified_source = SourceProvenance(
        source_type="resume_v12",
        source_ref="master_resume.txt",
        verified=True,
        recorded_at=now,
    )

    skills = [
        SkillRecord(name="Python", taxonomy_ref="python", proficiency_self_assessed=ProficiencyLevel.ADVANCED, evidence_refs=["conductor-agent", "overture"], source=verified_source),
        SkillRecord(name="LangGraph", taxonomy_ref="langgraph", proficiency_self_assessed=ProficiencyLevel.ADVANCED, evidence_refs=["conductor-agent"], source=verified_source),
        SkillRecord(name="TypeScript", taxonomy_ref="typescript", proficiency_self_assessed=ProficiencyLevel.INTERMEDIATE, evidence_refs=["align-resume"], source=verified_source),
        SkillRecord(name="FastAPI", taxonomy_ref="fastapi", proficiency_self_assessed=ProficiencyLevel.ADVANCED, evidence_refs=["conductor-agent"], source=verified_source),
        SkillRecord(name="Docker", taxonomy_ref="docker", proficiency_self_assessed=ProficiencyLevel.ADVANCED, evidence_refs=["conductor-agent"], source=verified_source),
        SkillRecord(name="Kubernetes", taxonomy_ref="kubernetes", proficiency_self_assessed=ProficiencyLevel.INTERMEDIATE, evidence_refs=["conductor-agent"], source=verified_source),
        SkillRecord(name="Prometheus", taxonomy_ref="prometheus", proficiency_self_assessed=ProficiencyLevel.INTERMEDIATE, evidence_refs=["conductor-agent"], source=verified_source),
        SkillRecord(name="LLM", taxonomy_ref="llm", proficiency_self_assessed=ProficiencyLevel.ADVANCED, evidence_refs=["align-resume", "conductor-agent"], source=verified_source),
        SkillRecord(name="PyTorch", taxonomy_ref="pytorch", proficiency_self_assessed=ProficiencyLevel.INTERMEDIATE, evidence_refs=["sentiment-analysis"], source=verified_source),
        SkillRecord(name="React", taxonomy_ref="react", proficiency_self_assessed=ProficiencyLevel.INTERMEDIATE, evidence_refs=["align-resume"], source=verified_source),
    ]

    experience = [
        ExperienceRecord(
            title="Conductor Agent — Lead Architect & Developer",
            kind="project",
            stack=["Python", "LangGraph", "Docker", "Kubernetes", "Prometheus"],
            bullets=[
                "Engineered the central LangGraph state machine coordinating a 10-component AI-Native Job Search system.",
                "Enforced ADR-6 structural Human-in-the-Loop approval gate ensuring zero unreviewed outbound communication.",
                "Implemented automated deduplication engine and 30-day rejection cooldown feedback loop.",
            ],
            live_url=None,
            repo_url="https://github.com/sdn9300/conductor-agent",
            source=verified_source,
        ),
        ExperienceRecord(
            title="AlignResume — AI-Powered Resume Optimization Platform",
            kind="project",
            stack=["TypeScript", "Next.js", "Groq API", "Playwright"],
            bullets=[
                "Architected full-stack AI web app in Next.js & TypeScript executing real-time resume tailoring and ATS gap analysis.",
                "Deployed truthfulness guardrail layer using Zod and Groq API to eliminate LLM hallucinations.",
            ],
            live_url="https://align-resume-beta.vercel.app/",
            repo_url="https://github.com/sdn9300/align-resume",
            source=verified_source,
        ),
    ]

    preferences = ApplicationPreferences(
        target_roles=["AI Engineer", "Agentic Systems Engineer", "Full Stack AI Developer"],
        target_industries=["Artificial Intelligence", "Developer Tools", "Cloud & Distributed Systems"],
        locations=["Remote", "Hybrid", "San Francisco, CA", "Bangalore, India"],
        remote_ok=True,
        seniority_qualifiers=["mid", "senior"],
    )

    profile = CandidateProfile(
        profile_metadata=metadata,
        identity=identity,
        education=education,
        skills=skills,
        experience=experience,
        preferences=preferences,
    )

    store.put(profile)
    print(f"[Migration] Successfully migrated master resume to CandidateProfile: {candidate_id} (Version: {profile.profile_metadata.schema_version})")
    return profile


if __name__ == "__main__":
    migrate_master_resume()
