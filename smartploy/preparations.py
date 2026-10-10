"""Immutable Smartploy application-draft package contracts."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any
import hashlib
import json

from .domain import JobCandidate, canonical_json, utc_now_iso
from .profile import CandidateProfile
from .scoring import ScoreResult


PREPARATION_CONTRACT_V1 = "smartploy.application.package.v1"
PREPARATION_CONTRACT = "smartploy.application.package.v2"
DRAFT_RESULT_SCHEMA_V1 = "smartploy.application.draft.v1"
DRAFT_RESULT_SCHEMA_V2 = "smartploy.application.draft.v2"
DRAFT_RESULT_SCHEMA = DRAFT_RESULT_SCHEMA_V2
PREPARATION_ACTION_V1 = "application_package_v1"
PREPARATION_ACTION = "application_package_v2"
TERMINAL_PREPARATION_STATES = {
    "blocked",
    "completed",
    "completed_unparsed",
    "failed",
    "cancelled",
}
PREPARATION_STATES = {
    "created",
    "queued",
    "running",
    *TERMINAL_PREPARATION_STATES,
}


class PreparationNotEligible(RuntimeError):
    pass


class PreparationResultError(ValueError):
    pass


APPLICATION_DRAFT_INSTRUCTIONS_V1 = f"""Return JSON only, with no Markdown fence, using exactly this top-level schema:
{{
  "schema": "{DRAFT_RESULT_SCHEMA_V1}",
  "fit_summary": {{
    "summary": "string",
    "strengths": ["string"],
    "gaps": ["string"]
  }},
  "cv_tailoring": {{
    "headline": "string",
    "summary": "string",
    "skills_to_emphasize": ["string"],
    "experience_edits": [
      {{"evidence_fact_ids": ["fact-id"], "rewrite": "string"}}
    ],
    "do_not_claim": ["string"]
  }},
  "cover_letter": "string",
  "application_answers": [
    {{"question": "string", "answer": "string", "evidence_fact_ids": ["fact-id"]}}
  ],
  "gap_framing": ["string"],
  "risks": ["string"],
  "review_checklist": ["string"]
}}

Rules:
- Use only approved candidate facts supplied in candidate_evidence.
- Never invent employers, dates, years of experience, degrees, certifications, skills, languages, or results.
- Every experience rewrite or application answer that makes a candidate claim must cite supplied evidence_fact_ids.
- Keep mandatory gaps visible; do not disguise them as matches.
- Tailor wording and emphasis, not factual truth.
- Do not browse, upload, submit, send, email, click, or claim any external action.
- This is a draft package for human review; final application authority is false.
"""

APPLICATION_DRAFT_INSTRUCTIONS = f"""Return JSON only, with no Markdown fence, using exactly this top-level schema:
{{
  "schema": "{DRAFT_RESULT_SCHEMA_V2}",
  "fit_summary": {{
    "summary": "string",
    "strengths": ["string"],
    "gaps": ["string"]
  }},
  "tailored_cv": {{
    "header_evidence_fact_ids": ["approved identity/contact/location fact ids only"],
    "headline": {{"text": "string", "evidence_fact_ids": ["fact-id"]}},
    "professional_summary": {{"text": "string", "evidence_fact_ids": ["fact-id"]}},
    "skills": [{{"text": "string", "evidence_fact_ids": ["fact-id"]}}],
    "experience": [{{"text": "string", "evidence_fact_ids": ["fact-id"]}}],
    "education": [{{"text": "string", "evidence_fact_ids": ["fact-id"]}}],
    "certifications": [{{"text": "string", "evidence_fact_ids": ["fact-id"]}}],
    "projects": [{{"text": "string", "evidence_fact_ids": ["fact-id"]}}],
    "languages": [{{"text": "string", "evidence_fact_ids": ["fact-id"]}}],
    "do_not_claim": ["string"]
  }},
  "cover_letter": {{
    "header_evidence_fact_ids": ["approved identity/contact/location fact ids only"],
    "salutation": "string",
    "paragraphs": [{{"text": "string", "evidence_fact_ids": ["fact-id"]}}],
    "closing": "string"
  }},
  "application_answers": [
    {{"question": "string", "answer": "string", "evidence_fact_ids": ["fact-id"]}}
  ],
  "gap_framing": ["string"],
  "risks": ["string"],
  "review_checklist": ["string"]
}}

Rules:
- Use only approved candidate facts supplied in candidate_evidence.
- Never invent identity, contact details, employers, dates, years of experience, degrees, certifications, skills, languages, projects, metrics, or results.
- header_evidence_fact_ids may reference only supplied identity/contact/location facts. Do not rewrite those values; SmartPloy renders the exact approved evidence values.
- Every CV claim item and every candidate claim in the cover letter or application answers must cite the supporting supplied evidence_fact_ids.
- It is valid for a section to be an empty list when approved evidence does not support it.
- Keep mandatory gaps visible; do not disguise them as matches.
- Tailor wording, ordering and emphasis, not factual truth.
- do_not_claim must explicitly list material tempting claims the evidence does not support.
- Do not browse, upload, submit, send, email, click, or claim any external action.
- This is a draft package for human review; final application authority is false.
"""


def draft_schema_for_contract(contract: str) -> str:
    return DRAFT_RESULT_SCHEMA_V1 if contract == PREPARATION_CONTRACT_V1 else DRAFT_RESULT_SCHEMA_V2


def action_for_contract(contract: str) -> str:
    return PREPARATION_ACTION_V1 if contract == PREPARATION_CONTRACT_V1 else PREPARATION_ACTION


def instructions_for_contract(contract: str) -> str:
    return (
        APPLICATION_DRAFT_INSTRUCTIONS_V1
        if contract == PREPARATION_CONTRACT_V1
        else APPLICATION_DRAFT_INSTRUCTIONS
    )

def _sha(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def preparation_job_snapshot(candidate: JobCandidate) -> dict[str, Any]:
    """Return content that can change the application draft.

    Discovery timestamps/source occurrences are intentionally excluded so
    freshness changes do not mint a new application package.
    """

    job = candidate.job.normalized()
    return {
        "canonical_key": candidate.canonical_key,
        "company": job.company,
        "role_title": job.role_title,
        "description": job.description,
        "location": job.location,
        "work_mode": job.work_mode,
        "deadline": job.deadline,
        "language": job.language,
        "requirements": list(job.requirements),
        "nice_to_have": list(job.nice_to_have),
        "application_url": job.application_url,
        "required_documents": list(job.required_documents),
        "questions": list(job.questions),
        "description_fingerprint": candidate.description_fingerprint,
    }


def approved_evidence_snapshot(profile: CandidateProfile) -> dict[str, Any]:
    return profile.approved_evidence()


@dataclass(frozen=True)
class ApplicationPreparation:
    package_id: str
    canonical_key: str
    profile_id: str
    preparation_contract: str
    job_snapshot_sha256: str
    evidence_sha256: str
    job_snapshot: dict[str, Any]
    evidence_snapshot: dict[str, Any]
    score_snapshot: dict[str, Any]
    status: str = "created"
    obum_job_id: str = ""
    obum_client_request_id: str = ""
    requested_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    completed_at: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    raw_output: str = ""
    error: str = ""

    def normalized(self) -> "ApplicationPreparation":
        if self.status not in PREPARATION_STATES:
            raise ValueError("unsupported preparation status")
        if not self.package_id or not self.canonical_key or not self.profile_id:
            raise ValueError("preparation identity is incomplete")
        if len(self.job_snapshot_sha256) != 64 or len(self.evidence_sha256) != 64:
            raise ValueError("preparation snapshot hashes must be SHA-256")
        job_snapshot = dict(self.job_snapshot or {})
        evidence_snapshot = dict(self.evidence_snapshot or {})
        if _sha(job_snapshot) != self.job_snapshot_sha256:
            raise ValueError("job snapshot hash does not match package contents")
        if _sha(evidence_snapshot) != self.evidence_sha256:
            raise ValueError("evidence snapshot hash does not match package contents")
        return replace(
            self,
            preparation_contract=self.preparation_contract or PREPARATION_CONTRACT,
            job_snapshot=job_snapshot,
            evidence_snapshot=evidence_snapshot,
            score_snapshot=dict(self.score_snapshot or {}),
            result=dict(self.result or {}),
            raw_output=str(self.raw_output or ""),
            error=str(self.error or "")[:4000],
        )

    def to_dict(self) -> dict[str, Any]:
        item = self.normalized()
        return {
            "package_id": item.package_id,
            "canonical_key": item.canonical_key,
            "profile_id": item.profile_id,
            "preparation_contract": item.preparation_contract,
            "job_snapshot_sha256": item.job_snapshot_sha256,
            "evidence_sha256": item.evidence_sha256,
            "score_snapshot": dict(item.score_snapshot),
            "evidence_fact_ids": sorted(approved_evidence_ids(item.evidence_snapshot)),
            "status": item.status,
            "obum_job_id": item.obum_job_id,
            "obum_client_request_id": item.obum_client_request_id,
            "requested_at": item.requested_at,
            "updated_at": item.updated_at,
            "completed_at": item.completed_at,
            "result": dict(item.result),
            "raw_output": item.raw_output,
            "error": item.error,
            "authority": {
                "may_prepare_drafts": True,
                "may_upload": False,
                "may_submit": False,
                "external_action_authorized": False,
            },
        }


def build_preparation(
    candidate: JobCandidate,
    profile: CandidateProfile,
    score: ScoreResult,
    *,
    requested_at: str | None = None,
) -> ApplicationPreparation:
    job_snapshot = preparation_job_snapshot(candidate)
    job_hash = _sha(job_snapshot)
    evidence = approved_evidence_snapshot(profile)
    evidence_hash = _sha(evidence)
    material = {
        "contract": PREPARATION_CONTRACT,
        "canonical_key": candidate.canonical_key,
        "job_snapshot_sha256": job_hash,
        "evidence_sha256": evidence_hash,
    }
    package_id = f"prep-{_sha(material)[:28]}"
    timestamp = requested_at or utc_now_iso()
    return ApplicationPreparation(
        package_id=package_id,
        canonical_key=candidate.canonical_key,
        profile_id=profile.profile_id,
        preparation_contract=PREPARATION_CONTRACT,
        job_snapshot_sha256=job_hash,
        evidence_sha256=evidence_hash,
        job_snapshot=job_snapshot,
        evidence_snapshot=evidence,
        score_snapshot=score.to_dict(),
        requested_at=timestamp,
        updated_at=timestamp,
    )


def ensure_preparation_eligible(
    candidate: JobCandidate,
    profile: CandidateProfile,
    score: ScoreResult,
    *,
    minimum_fit: int = 82,
    minimum_priority: int = 82,
) -> None:
    if not candidate.source_current:
        raise PreparationNotEligible("job source is no longer current")
    if not profile.approved_facts:
        raise PreparationNotEligible("no approved Smartploy profile evidence is available")
    if score.mandatory_gaps:
        raise PreparationNotEligible("mandatory requirement gaps block automatic preparation")
    if score.fit_score < minimum_fit:
        raise PreparationNotEligible(f"Fit Score {score.fit_score} is below {minimum_fit}")
    if score.priority_score < minimum_priority:
        raise PreparationNotEligible(f"Priority Score {score.priority_score} is below {minimum_priority}")


def approved_evidence_ids(evidence_snapshot: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    facts = evidence_snapshot.get("facts") if isinstance(evidence_snapshot, dict) else None
    if not isinstance(facts, dict):
        return ids
    for rows in facts.values():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and row.get("fact_id"):
                ids.add(str(row["fact_id"]))
    return ids


def _referenced_evidence_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "evidence_fact_ids":
                if not isinstance(child, list) or not all(isinstance(item, str) for item in child):
                    raise PreparationResultError("evidence_fact_ids must be a list of strings")
                found.update(child)
            else:
                found.update(_referenced_evidence_ids(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_referenced_evidence_ids(child))
    return found


def parse_draft_output(
    output_text: str,
    *,
    allowed_evidence_ids: set[str] | None = None,
) -> dict[str, Any]:
    text = str(output_text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PreparationResultError("ObumAI draft output is not valid JSON") from exc
    if not isinstance(value, dict):
        raise PreparationResultError("ObumAI draft output must be a JSON object")
    if value.get("schema") != DRAFT_RESULT_SCHEMA:
        raise PreparationResultError("ObumAI draft output has the wrong schema")

    required = {
        "fit_summary": dict,
        "cv_tailoring": dict,
        "cover_letter": str,
        "application_answers": list,
        "gap_framing": list,
        "risks": list,
        "review_checklist": list,
    }
    for key, expected_type in required.items():
        if not isinstance(value.get(key), expected_type):
            raise PreparationResultError(f"ObumAI draft output field {key} has the wrong type")

    referenced_ids = _referenced_evidence_ids(value)
    if allowed_evidence_ids is not None:
        unknown = sorted(referenced_ids - allowed_evidence_ids)
        if unknown:
            raise PreparationResultError(
                "ObumAI draft output referenced evidence IDs outside the immutable package snapshot"
            )
    return value
