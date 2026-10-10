"""Auditable Smartploy application CRM domain."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any
import hashlib

from .domain import canonical_json, utc_now_iso
from .preparations import ApplicationPreparation


PREPARATION_APPLICATION_STATES = {
    "preparing",
    "ready_for_review",
    "needs_review",
    "preparation_blocked",
}
EXTERNAL_APPLICATION_STATES = {
    "submitted",
    "acknowledged",
    "recruiter_contact",
    "assessment",
    "interview",
    "offer",
    "rejected",
    "withdrawn",
}
APPLICATION_STATES = PREPARATION_APPLICATION_STATES | EXTERNAL_APPLICATION_STATES

PREPARATION_STATE_MAP = {
    "created": "preparing",
    "queued": "preparing",
    "running": "preparing",
    "completed": "ready_for_review",
    "completed_unparsed": "needs_review",
    "blocked": "preparation_blocked",
    "failed": "preparation_blocked",
    "cancelled": "preparation_blocked",
}


def stable_application_id(canonical_key: str) -> str:
    digest = hashlib.sha256(str(canonical_key).encode("utf-8")).hexdigest()[:24]
    return f"app-{digest}"


def stable_event_id(
    application_id: str,
    *,
    event_type: str,
    source_type: str,
    source_id: str,
    to_state: str,
) -> str:
    material = canonical_json(
        {
            "application_id": application_id,
            "event_type": event_type,
            "source_type": source_type,
            "source_id": source_id,
            "to_state": to_state,
        }
    )
    return f"appevt-{hashlib.sha256(material.encode('utf-8')).hexdigest()[:28]}"


@dataclass(frozen=True)
class ApplicationRecord:
    application_id: str
    canonical_key: str
    package_id: str
    state: str
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    submitted_at: str = ""
    external_confirmation_id: str = ""
    external_reference: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> "ApplicationRecord":
        if not self.application_id or not self.canonical_key:
            raise ValueError("application identity is incomplete")
        if self.state not in APPLICATION_STATES:
            raise ValueError("unsupported application state")
        if self.state in PREPARATION_APPLICATION_STATES and self.submitted_at:
            raise ValueError("preparation state cannot carry a submitted_at timestamp")
        return replace(
            self,
            package_id=str(self.package_id or ""),
            external_confirmation_id=str(self.external_confirmation_id or ""),
            external_reference=str(self.external_reference or ""),
            metadata=dict(self.metadata or {}),
        )

    @property
    def has_been_submitted(self) -> bool:
        return bool(self.submitted_at)

    def to_dict(self) -> dict[str, Any]:
        item = self.normalized()
        return {
            "application_id": item.application_id,
            "canonical_key": item.canonical_key,
            "package_id": item.package_id,
            "state": item.state,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "submitted_at": item.submitted_at,
            "has_been_submitted": item.has_been_submitted,
            "external_confirmation_id": item.external_confirmation_id,
            "external_reference": item.external_reference,
            "metadata": dict(item.metadata),
        }


@dataclass(frozen=True)
class ApplicationEvent:
    event_id: str
    application_id: str
    event_type: str
    from_state: str
    to_state: str
    source_type: str
    source_id: str
    occurred_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> "ApplicationEvent":
        if self.to_state not in APPLICATION_STATES:
            raise ValueError("event target state is unsupported")
        if self.from_state and self.from_state not in APPLICATION_STATES:
            raise ValueError("event source state is unsupported")
        if not self.event_id or not self.application_id or not self.source_type or not self.source_id:
            raise ValueError("application event identity is incomplete")
        return replace(self, metadata=dict(self.metadata or {}))

    def to_dict(self) -> dict[str, Any]:
        item = self.normalized()
        return {
            "event_id": item.event_id,
            "application_id": item.application_id,
            "event_type": item.event_type,
            "from_state": item.from_state,
            "to_state": item.to_state,
            "source_type": item.source_type,
            "source_id": item.source_id,
            "occurred_at": item.occurred_at,
            "metadata": dict(item.metadata),
        }


def application_state_for_preparation(preparation: ApplicationPreparation) -> str:
    try:
        return PREPARATION_STATE_MAP[preparation.status]
    except KeyError as exc:
        raise ValueError(f"preparation state cannot be mapped to CRM: {preparation.status}") from exc


def initial_application_for_preparation(preparation: ApplicationPreparation) -> ApplicationRecord:
    state = application_state_for_preparation(preparation)
    return ApplicationRecord(
        application_id=stable_application_id(preparation.canonical_key),
        canonical_key=preparation.canonical_key,
        package_id=preparation.package_id,
        state=state,
        created_at=preparation.requested_at,
        updated_at=preparation.updated_at,
        metadata={
            "preparation_contract": preparation.preparation_contract,
            "fit_score": preparation.score_snapshot.get("fit_score"),
            "priority_score": preparation.score_snapshot.get("priority_score"),
        },
    ).normalized()


def apply_preparation_to_application(
    record: ApplicationRecord,
    preparation: ApplicationPreparation,
) -> ApplicationRecord:
    current = record.normalized()
    if current.canonical_key != preparation.canonical_key:
        raise ValueError("preparation belongs to a different canonical job")

    # A preparation refresh may update the linked package, but it can never
    # regress or invent externally evidenced submission/outcome state.
    if current.state in EXTERNAL_APPLICATION_STATES:
        return replace(
            current,
            package_id=preparation.package_id,
            updated_at=max(current.updated_at, preparation.updated_at),
        ).normalized()

    return replace(
        current,
        package_id=preparation.package_id,
        state=application_state_for_preparation(preparation),
        updated_at=max(current.updated_at, preparation.updated_at),
        submitted_at="",
        metadata={
            **dict(current.metadata),
            "preparation_contract": preparation.preparation_contract,
            "fit_score": preparation.score_snapshot.get("fit_score"),
            "priority_score": preparation.score_snapshot.get("priority_score"),
        },
    ).normalized()


def preparation_event(
    before: ApplicationRecord | None,
    after: ApplicationRecord,
    preparation: ApplicationPreparation,
) -> ApplicationEvent:
    from_state = before.state if before is not None else ""
    event_type = "preparation_synced"
    return ApplicationEvent(
        event_id=stable_event_id(
            after.application_id,
            event_type=event_type,
            source_type="preparation",
            source_id=f"{preparation.package_id}:{preparation.status}",
            to_state=after.state,
        ),
        application_id=after.application_id,
        event_type=event_type,
        from_state=from_state,
        to_state=after.state,
        source_type="preparation",
        source_id=f"{preparation.package_id}:{preparation.status}",
        occurred_at=preparation.updated_at,
        metadata={
            "created_record": before is None,
            "package_id": preparation.package_id,
            "preparation_status": preparation.status,
            "obum_job_id": preparation.obum_job_id,
        },
    ).normalized()
