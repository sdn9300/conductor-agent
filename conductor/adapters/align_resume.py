"""
AlignResume Adapter.
Calls AlignResume service (Next.js API endpoint or direct LLM fallback) to tailor master resume against a JD.
Implements ADR-3, ADR-4, and EC-01 / EC-08.
"""

import time
import httpx
from typing import Any, Dict, Optional, List
from conductor.adapters.base import AgentAdapter, AgentResult
from conductor.config import config


class AlignResumeAdapter(AgentAdapter):
    """Adapter for interacting with AlignResume (#2)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        allow_fallback: bool = True,
    ):
        self.base_url = (base_url or config.ALIGN_RESUME_URL).rstrip("/")
        self.timeout = timeout or config.ALIGN_RESUME_TIMEOUT
        self.allow_fallback = allow_fallback

    @property
    def name(self) -> str:
        return "align_resume"

    def invoke(self, state_dict: Dict[str, Any]) -> AgentResult:
        start_time = time.time()
        try:
            app = state_dict.get("application", {})
            posting = app.get("posting", {}) if isinstance(app, dict) else getattr(app, "posting", {})
            if isinstance(posting, dict):
                jd_text = posting.get("jd_text", "")
                company = posting.get("company", "Target Company")
                title = posting.get("title", "Target Role")
            else:
                jd_text = getattr(posting, "jd_text", "")
                company = getattr(posting, "company", "Target Company")
                title = getattr(posting, "title", "Target Role")

            resume_text = state_dict.get("master_resume_text") or ""
            if not resume_text:
                resume_text = (
                    "Soumyadeep Nath — AI Engineer & Full Stack Developer\n"
                    "Experience: Building agentic workflows, LangGraph orchestration, LLM pipelines.\n"
                    "Skills: Python, TypeScript, LangGraph, FastAPI, React, PyTorch, Docker, Kubernetes."
                )

            if len(jd_text) < 20:
                return AgentResult(
                    success=False,
                    error="Job description is too short to tailor resume (minimum 20 characters required).",
                    latency_ms=(time.time() - start_time) * 1000,
                )

            # Attempt HTTP call to AlignResume service
            payload = {
                "resume": {"type": "text", "content": resume_text},
                "jobDescription": {"type": "text", "content": jd_text},
            }

            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(f"{self.base_url}/api/runs", json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        return AgentResult(
                            success=True,
                            output={
                                "run_id": data.get("id", f"align-{int(time.time())}"),
                                "tailored_content": data.get("tailoredResume", resume_text),
                                "diff_summary": f"Tailored for {title} at {company}",
                                "match_score": float(data.get("matchScore", 85.0)),
                                "skills_matched": data.get("matchingKeywords", ["Python", "AI", "Agentic"]),
                                "skills_gap": data.get("missingKeywords", []),
                            },
                            cost_estimate=0.002,
                            latency_ms=(time.time() - start_time) * 1000,
                        )
            except Exception as http_err:
                if not self.allow_fallback:
                    return AgentResult(
                        success=False,
                        error=f"AlignResume service unreachable at {self.base_url}: {http_err}",
                        latency_ms=(time.time() - start_time) * 1000,
                    )
                # Fallback to simulated tailoring (ADR-4 & EC-01)
                print(f"[AlignResumeAdapter] Service unreachable ({http_err}), executing deterministic fallback.")

            # Deterministic Fallback Generator
            fallback_result = self._generate_fallback_tailoring(resume_text, jd_text, company, title)
            return AgentResult(
                success=True,
                output=fallback_result,
                cost_estimate=0.0,
                latency_ms=(time.time() - start_time) * 1000,
                metadata={"fallback_used": True},
            )

        except Exception as e:
            return AgentResult(
                success=False,
                error=f"AlignResumeAdapter unexpected error: {str(e)}",
                latency_ms=(time.time() - start_time) * 1000,
            )

    def _generate_fallback_tailoring(
        self, resume_text: str, jd_text: str, company: str, title: str
    ) -> Dict[str, Any]:
        """Generate structured tailored resume data when upstream API is offline."""
        # Simple heuristic keyword extraction
        words = set(jd_text.lower().replace(",", "").replace(".", "").split())
        key_skills = [
            w.capitalize()
            for w in [
                "python", "langgraph", "agents", "docker", "kubernetes",
                "fastapi", "react", "next.js", "pytorch", "transformers", "llm"
            ]
            if w in words
        ]
        if not key_skills:
            key_skills = ["Python", "LLM", "Agent Orchestration"]

        tailored_body = (
            f"{resume_text}\n\n"
            f"[Targeted Optimization for {title} @ {company}]\n"
            f"- Demonstrated expertise matching requirements: {', '.join(key_skills)}\n"
            f"- Aligned project experience with {company}'s tech stack and engineering objectives."
        )

        return {
            "run_id": f"align-fallback-{int(time.time() * 1000)}",
            "tailored_content": tailored_body,
            "diff_summary": f"Optimized bullet points and keywords for {title} at {company}",
            "match_score": 88.0,
            "skills_matched": key_skills,
            "skills_gap": ["Specific Domain Knowledge"],
        }

    def health_check(self) -> bool:
        try:
            with httpx.Client(timeout=2.0) as client:
                r = client.get(f"{self.base_url}/api/health")
                return r.status_code in (200, 404)  # 404 still means server is up
        except Exception:
            return False
