"""SP15a real PostgreSQL race/ownership/erasure tests. Synthetic only.

No browser or employer requests are sent by these tests.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
import os
from uuid import uuid4

import pytest
from psycopg import connect
from psycopg.types.json import Jsonb

from smartploy.account_erasure import (
    PostgresAccountErasureRepository, inspect_quarantined_account,
)
from smartploy.employer_submit_claim_storage import (
    EmployerSubmitClaimDenied, PostgresEmployerSubmitClaimRepository,
)
from smartploy.identity import AuthenticatedPrincipal, PostgresIdentityRepository
from smartploy.storage import PostgresJobRepository


DSN = os.getenv("SMARTPLOY_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="SMARTPLOY_TEST_DATABASE_URL not configured")


@pytest.fixture
def scoped():
    PostgresJobRepository(DSN).migrate()
    nonce = uuid4().hex
    job_key = "employer-job-" + nonce
    url = "https://jobs.lever.co/testorg/" + nonce
    fingerprint = sha256(("job:" + nonce).encode()).hexdigest()
    letter = "Dear hiring team, I am applying for the advertised role. " + (
        "All statements and contact details must be checked by the applicant."
    )
    ids = PostgresIdentityRepository(DSN)
    a = ids.resolve_or_create(AuthenticatedPrincipal(
        issuer="https://sso.example.invalid", subject="claim-a-" + nonce,
        email="same@example.invalid", auth_source="oidc",
    ))
    b = ids.resolve_or_create(AuthenticatedPrincipal(
        issuer="https://sso.example.invalid", subject="claim-b-" + nonce,
        email="same@example.invalid", auth_source="oidc",
    ))
    wa, wb = "workspace-claim-a-" + nonce, "workspace-claim-b-" + nonce
    with connect(DSN) as conn:
        conn.execute(
            """INSERT INTO smartploy_jobs (
                 canonical_key,job_id,company,role_title,candidate,
                 first_seen_at,last_seen_at,source_current
               ) VALUES (%s,%s,'Test Ltd','Engineer',%s,now(),now(),true)""",
            (job_key, "job-" + nonce, Jsonb({
                "description_fingerprint": fingerprint,
                "job": {"application_url": url},
            })),
        )
        for profile_id, workspace_id in ((a.profile_id, wa), (b.profile_id, wb)):
            conn.execute(
                """INSERT INTO smartploy_application_workspaces (
                     workspace_id,profile_id,canonical_key,role_title,company,
                     application_url,cv_text,cover_letter_text,job_fingerprint
                   ) VALUES (%s,%s,%s,'Engineer','Test Ltd',%s,%s,%s,%s)""",
                (
                    workspace_id, profile_id, job_key, url,
                    "Reviewed synthetic resume with sufficient content", letter, fingerprint,
                ),
            )
    ledger = PostgresEmployerSubmitClaimRepository(DSN)

    def reserve(binding=a, workspace_id=wa, revision=1, approved=True, rights=True):
        return PostgresEmployerSubmitClaimRepository(DSN).reserve(
            binding,
            workspace_id=workspace_id,
            expected_revision=revision,
            expected_application_url=url,
            expected_job_fingerprint=fingerprint,
            explicit_final_user_approval=approved,
            employer_submission_permitted=rights,
        )

    yield a, b, wa, wb, job_key, url, fingerprint, letter, ledger, reserve

    with connect(DSN) as conn:
        conn.execute(
            "DELETE FROM smartploy_employer_submit_claims WHERE user_id IN (%s,%s)",
            (a.user_id, b.user_id),
        )
        conn.execute(
            """DELETE FROM smartploy_obumai_erasure_obligations
               WHERE request_id IN (
                  SELECT request_id FROM smartploy_account_erasure_requests
                  WHERE user_id IN (%s,%s)
               )""", (a.user_id, b.user_id),
        )
        conn.execute(
            "DELETE FROM smartploy_account_erasure_requests WHERE user_id IN (%s,%s)",
            (a.user_id, b.user_id),
        )
        conn.execute(
            "DELETE FROM smartploy_browser_receipts WHERE profile_id IN (%s,%s)",
            (a.profile_id, b.profile_id),
        )
        conn.execute(
            "DELETE FROM smartploy_application_workspaces WHERE profile_id IN (%s,%s)",
            (a.profile_id, b.profile_id),
        )
        conn.execute("DELETE FROM smartploy_jobs WHERE canonical_key=%s", (job_key,))
        for table in ("smartploy_user_identities", "smartploy_user_profiles", "smartploy_users"):
            conn.execute(f"DELETE FROM {table} WHERE user_id IN (%s,%s)", (a.user_id, b.user_id))


def test_8_competing_workers_create_exactly_one_durable_marker(scoped):
    a, b, wa, wb, job_key, url, fp, letter, ledger, reserve = scoped
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: reserve(), range(8)))
    assert sum(int(inserted) for _, inserted in results) == 1
    assert len({claim.claim_id for claim, _ in results}) == 1
    claim = results[0][0]
    assert claim.state == "reserved_unverified"
    assert claim.document_sha256 == sha256(
        ("Reviewed synthetic resume with sufficient content" + "\0" + letter).encode()
    ).hexdigest()
    assert PostgresEmployerSubmitClaimRepository(DSN).get(a, job_key).claim_id == claim.claim_id
    assert ledger.get(b, job_key) is None
    public = claim.to_review_dict()
    assert public["employer_submission_verified"] is False
    assert public["automatic_retry_authorized"] is False
    assert a.user_id not in str(public) and url not in str(public)


def test_revision_and_workspace_recreation_do_not_issue_second_attempt(scoped):
    a, _, wa, _, job_key, url, fp, letter, ledger, reserve = scoped
    first, created = reserve()
    assert created
    with connect(DSN) as conn:
        conn.execute(
            """UPDATE smartploy_application_workspaces
               SET revision=2, cv_text='New reviewed CV', updated_at=now()
               WHERE workspace_id=%s""", (wa,),
        )
    with pytest.raises(EmployerSubmitClaimDenied, match="changed"):
        reserve(revision=1)
    second, new = reserve(revision=2)
    assert not new and second.claim_id == first.claim_id
    assert second.document_revision == 1
    with connect(DSN) as conn:
        conn.execute("DELETE FROM smartploy_application_workspaces WHERE workspace_id=%s", (wa,))
        replacement_id = "workspace-replacement-" + uuid4().hex
        conn.execute(
            """INSERT INTO smartploy_application_workspaces (
                 workspace_id,profile_id,canonical_key,role_title,company,
                 application_url,cv_text,cover_letter_text,job_fingerprint
               ) VALUES (%s,%s,%s,'Engineer','Test Ltd',%s,%s,%s,%s)""",
            (replacement_id, a.profile_id, job_key, url, "Recreated reviewed CV", letter, fp),
        )
    again, created = reserve(workspace_id=replacement_id)
    assert not created and again.claim_id == first.claim_id


def test_owner_approval_and_employer_policy_gates(scoped):
    a, b, wa, wb, key, _, _, _, ledger, reserve = scoped
    with pytest.raises(EmployerSubmitClaimDenied, match="approval"):
        reserve(approved=False)
    with pytest.raises(EmployerSubmitClaimDenied, match="approval"):
        reserve(rights=False)
    with pytest.raises(EmployerSubmitClaimDenied, match="workspace"):
        reserve(binding=b, workspace_id=wa)
    with pytest.raises(EmployerSubmitClaimDenied, match="owner|binding|disabled"):
        reserve(binding=replace(a, user_id=b.user_id))
    assert ledger.get(a, key) is None
    own_b, created = reserve(binding=b, workspace_id=wb)
    assert created and own_b.user_id == b.user_id
    assert ledger.get(a, key) is None
    assert ledger.get(b, key).claim_id == own_b.claim_id


def test_stale_posting_document_and_previous_receipt_refused(scoped):
    a, _, wa, _, key, url, fp, _, ledger, reserve = scoped
    with connect(DSN) as conn:
        conn.execute("UPDATE smartploy_jobs SET source_current=false WHERE canonical_key=%s", (key,))
    with pytest.raises(EmployerSubmitClaimDenied, match="no longer current"):
        reserve()
    with connect(DSN) as conn:
        conn.execute("UPDATE smartploy_jobs SET source_current=true WHERE canonical_key=%s", (key,))
        conn.execute(
            "UPDATE smartploy_application_workspaces SET job_fingerprint='changed' WHERE workspace_id=%s",
            (wa,),
        )
    with pytest.raises(EmployerSubmitClaimDenied, match="changed"):
        reserve()
    with connect(DSN) as conn:
        conn.execute(
            "UPDATE smartploy_application_workspaces SET job_fingerprint=%s WHERE workspace_id=%s",
            (fp, wa),
        )
        conn.execute(
            """INSERT INTO smartploy_browser_receipts (
                 profile_id,workspace_id,document_revision,document_sha256,
                 reference,confirmation_page_url,confirmation_page_sha256,
                 observed_at,evidence_digest
               ) VALUES (%s,%s,1,%s,'TST-1234',
                         'https://jobs.lever.co/testorg/confirmation',%s,now(),%s)""",
            (a.profile_id, wa, "b" * 64, "c" * 64, "d" * 64),
        )
    with pytest.raises(EmployerSubmitClaimDenied, match="receipt"):
        reserve()
    assert ledger.get(a, key) is None


def test_uncertain_is_sticky_owner_scoped_and_never_an_automatic_retry(scoped):
    a, b, _, _, key, _, _, _, ledger, reserve = scoped
    item, created = reserve()
    assert created
    with pytest.raises(EmployerSubmitClaimDenied, match="owner"):
        ledger.mark_uncertain(b, item.claim_id, code="timeout")
    with pytest.raises(EmployerSubmitClaimDenied, match="sanitized"):
        ledger.mark_uncertain(a, item.claim_id, code="leak_private_reason")
    uncertain = ledger.mark_uncertain(a, item.claim_id, code="timeout")
    assert uncertain.state == "uncertain"
    assert ledger.mark_uncertain(a, item.claim_id, code="timeout") == uncertain
    with pytest.raises(EmployerSubmitClaimDenied, match="reset|relabeled"):
        ledger.mark_uncertain(a, item.claim_id, code="browser_error")
    again, new = reserve()
    assert not new and again.state == "uncertain"
    assert ledger.get(a, key).claim_id == item.claim_id


def test_quarantine_blocks_new_claim_and_inventories_existing_marker(scoped):
    a, b, _, _, key, _, _, _, ledger, reserve = scoped
    claim, new = reserve()
    assert new
    erasure = PostgresAccountErasureRepository(DSN)
    status = erasure.quarantine(a.user_id, a.profile_id)
    assert status.status == "quarantined"
    inventory = inspect_quarantined_account(DSN, a.user_id, a.profile_id)
    assert inventory.counts["employer_submit_claims"] == 1
    assert inventory.unknown_owner_tables == ()
    with pytest.raises(EmployerSubmitClaimDenied, match="disabled|binding"):
        reserve()
    assert ledger.get(a, key).claim_id == claim.claim_id
    assert ledger.get(b, key) is None
