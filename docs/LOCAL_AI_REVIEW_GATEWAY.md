# SmartPloy local ObumAI drafting — operator-gated, review-only

SmartPloy can optionally request tailored writing suggestions from an existing
**local Ollama model** used by the ObumAI ecosystem. It never impersonates
ObumAI agent-job authorization or activates the disabled production ObumAI
agent runtime. No external model API is called.

## Why this interface exists

ObumAI's current `deploy/personal/docker-compose.yml` forces
`OBUM_AGENT_EXECUTION_ENABLED=false` and
`OBUM_AGENT_WORKER_ENABLED=false`. Calling
`POST /api/v1/agent-jobs` does not yield a working generation job while
those flags and a trusted machine identity are unavailable.

This SmartPloy integration uses *only* a local Ollama endpoint, requires a
manual user click and consent, and produces suggestions. It does not grant
browser, employer, file-upload, or account-writing capabilities.

## Activation requirements on obum-core-01

The integration is **off by default**. The SmartPloy API container must be
able to connect to a local, authenticated/trusted host-network Ollama listener
at `http://host.docker.internal:11434`, and the requested model must
already be installed. Do not expose Ollama publicly to achieve this.
Do not copy any model API credentials to SmartPloy. Only explicitly
operator-reviewed network paths are allowed.

Before activation, confirm internal network reachability using a
*non-sensitive* host test. An operator can query the model list and
the API container's `/api/v1/local-ai/status` endpoint after enabling.

Edit only the untracked `0600` SmartPloy private env, preserving all other
entries:

```text
SMARTPLOY_LOCAL_AI_ENABLED=true
SMARTPLOY_LOCAL_AI_BASE_URL=http://host.docker.internal:11434
SMARTPLOY_LOCAL_AI_MODEL=qwen3:4b
SMARTPLOY_LOCAL_AI_TIMEOUT_SECONDS=75
```

The adapter refuses any non-local hostname, HTTPS third-party API,
alternative port, URL userinfo/query string, or redirect. It accepts only
`localhost`, `127.0.0.1`, `host.docker.internal` or `ollama`
on HTTP port 11434.

Use the normal SmartPloy preflight, safeguarded deployment with backup,
image identity checks, and acceptance. Never print the entire env.

## User workflow

1. Upload CV and approve individual skills, education, experience, name
   and contact facts.
2. Open a current job, choose Prepare documents and save any edits.
3. In My applications, the AI card shows model reachability.
4. Click Suggest tailored wording and approve the prompt describing
   **local processing of the job text and approved facts**.
5. SmartPloy requests one bounded response and validates the expected
   JSON schema and referenced evidence fact IDs. Unapproved facts and
   raw uploaded CV bytes/text are **not sent to the model**.
6. The suggestion is shown separately and **not saved automatically**.
   The applicant chooses Insert into editor, reviews the generated claims,
   and manually clicks Save changes. PDF/DOCX exports remain unchanged
   until that explicit save.
7. No employer contact, upload, submission, approval grant, or browsing
   can occur as a result of local generation.

The model can still make inaccurate statements. The draft must never be
called an independently verified finished application before the applicant
reviews it; the applicant must confirm every claim. Long local CPU inference
may exceed the 75-second timeout, and fail safely without modifying drafts.

## Still required for full autonomous job applications

- ObumAI first-party OIDC service-to-service authentication and a live
  audited job-execution runtime rather than the currently disabled one.
- A browser/apply connector authorized for the *specific* employer and job.
- Strong form-state/readiness checks, manual answers to employer-specific
  required questions, scoped upload permission, and MFA/CAPTCHA handoff.
- Per-job exact submission preview and explicit one-use approval.
- Submission receipt and deduplication/ambiguity handling. Never
  equate a request attempt with a confirmed application.
- An independent revocation/stop control, source-terms policy, and
  production browser tests on permitted employers.

This release never authorizes external application submission.
