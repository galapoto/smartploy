# SmartPloy application readiness and live acceptance

This report is a **read-only production diagnostic**, not a claim that
SmartPloy has submitted any real employer application.

After reviewing and installing the merged SmartPloy release on
`obum-core-01`, run:

```bash
sudo docker exec smartploy-api-1 python scripts/check_application_runtime.py
```

This prints only application-database table presence, active job count,
identity mode classification, local model readiness and the available
review/download/receipt boundaries.

The diagnostic does not print passwords, Access tokens, private CV contents,
profile facts, individual jobs, receipt contents or employer request bodies.
It does not browse or contact any employer. If locally configured, it makes
one read-only request to the **private** Ollama `/api/tags` endpoint.

### Optional stricter checks

```bash
sudo docker exec smartploy-api-1 python scripts/check_application_runtime.py --require-browser-backend
sudo docker exec smartploy-api-1 python scripts/check_application_runtime.py --require-local-ai
```

The first requires every application storage migration to be installed and
at least one current job in the database. The second additionally requires
an explicitly enabled and reachable private local model. A failed second
command is expected until the operator activates private model access.

The separate automatic Finnish job worker checks remain:

```bash
sudo docker exec smartploy-worker-1 python scripts/check_ats_readiness.py
```

### Actual browser acceptance required

The server cannot know whether a real employer has accepted a candidate.
A complete end-to-end acceptance requires these user-driven steps:

1. Sign in to `https://smartploy.obumai.com` with the first-party or
   Cloudflare Access identity currently assigned to the account.
2. Upload/review an actual private CV and approve full name, email,
   relevant skills, work history, and optionally phone/link URLs.
3. Open a current Lever job → **Prepare documents**.
4. Confirm generated CV and cover letter have no invented qualifications,
   edit/save each and download PDF/DOCX files.
5. If the local AI gateway was separately commissioned, request one
   evidence-bound draft, inspect citations/risks, insert suggestions only
   after reviewing, and manually save.
6. Install the first-party Chrome `browser-companion` from the reviewed
   repository revision.
7. Copy a fresh 15-minute approved packet from SmartPloy, open the exact
   Lever posting, inspect the form, explicitly fill known fields, attach
   documents and answer/consent manually.
8. Only when intending to send that single application, approve the
   companion's final one-shot submit. Never automate CAPTCHA/MFA.
9. If the employer displays a reference-bearing confirmation, reopen the
   companion with the same packet after navigation and copy the observed
   receipt. Import it into the matching SmartPloy draft.
10. Confirm the receipt remains marked
    **browser-observed, not independently employer-verified**, and that
    the application documents become immutable. The
    `actually_submitted` metric does not increase just because of an
    attempt or browser confirmation.
11. If the employer provides a separate confirmation email/reference,
    keep it for independent audit. Complete any self-reported tracking
    deliberately.

**No real employer application should be sent solely as a test without the
applicant's explicit authorization.** If employer terms prohibit automation,
use the documents and manually submit on the employer's original site.

## Host safety

The SmartPloy release script backs up its own PostgreSQL volume, migrates,
recreates only SmartPloy API/web/worker, verifies actual image IDs, and checks
Cloudflare edge/access. Do not use `docker compose down -v` or change
ObumAI core services, Cloudflare policies, or public Ollama exposure for
this milestone.

## What full functional acceptance means

`ready_for_authenticated_browser_acceptance=true` only proves the server
is ready for manual UI/browser tests. Even with all API and CI tests green,
`browser_form_test_completed=false`,
`real_employer_receipt_verified=false`, and
`server_automatic_employer_submit_authorized=false` are intentional.
The first two require separate real-world evidence and the third stays
false because employer submissions are triggered only in the owner's
extension after explicit per-job approval.
