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

The integration is **off by default**. In the OVH
`obumai/obumellm` release/ovh-local-intelligence deployment, Ollama
binds port 11434 **inside ObumAI's Docker bridge**; it is not published to
the host. Therefore the former
`http://host.docker.internal:11434` endpoint cannot be assumed reachable.

Use a **dedicated internal Docker bridge** for Ollama consumers. It connects
only the existing `obumai-personal/ollama` service to the
`smartploy/api` service. The two databases and the SmartPloy worker/web
stay on their existing networks. It does not publish port 11434 or mount
Ollama model storage into SmartPloy.

### Diagnose first (read-only)

On `obum-core-01`, after deploying a release containing the helper:

```bash
cd /srv/obum/stacks/smartploy
sudo bash deploy/personal/scripts/bridge-local-ollama.sh --status
```

This prints only safe diagnostics, not Docker secrets or private application
content. The expected initial result is that the bridge is absent.
Check the installed model names without changing the model container:

```bash
sudo docker exec obumai-personal-ollama-1 ollama list
```

If your chosen model is **not** installed, check memory/disk resources and
then deliberately pull the matching name inside the *existing* model service
(e.g. `sudo docker exec obumai-personal-ollama-1 ollama pull qwen3:4b`).
Do not pull models unnecessarily or install a separate Ollama daemon.

### Explicit model-only bridge commissioning

```bash
sudo bash deploy/personal/scripts/bridge-local-ollama.sh --connect
```

This validates each container's exact Compose project/service labels and
image types, requires healthy containers, creates
`smartploy-ollama-private` with Docker's `--internal` flag and a
strict identifying label, connects **only** the two containers, then
queries the Ollama model catalog from inside SmartPloy's API container.
The command fails if the selected model is unavailable. It does not
enable local AI by itself, does not modify private env values, and
does not contact employers or other model providers.

### Activate only after bridge/model readiness passes

Edit `/srv/obum/stacks/smartploy/deploy/personal/env` with
`sudoedit`, keeping file mode `0600` and every other variable.
Replace any existing entries rather than appending duplicates:

```text
SMARTPLOY_LOCAL_AI_ENABLED=true
SMARTPLOY_LOCAL_AI_BASE_URL=http://ollama:11434
SMARTPLOY_LOCAL_AI_MODEL=qwen3:4b
SMARTPLOY_LOCAL_AI_TIMEOUT_SECONDS=75
```

Then run the existing guarded SmartPloy deployment:

```bash
cd /srv/obum/stacks/smartploy
sudo bash deploy/personal/scripts/preflight.sh
sudo bash deploy/personal/scripts/deploy.sh main
sudo docker exec smartploy-api-1 python scripts/check_application_runtime.py --require-local-ai
```

For opted-in releases, the deploy script restores the model bridge
automatically after SmartPloy's API container recreation. If a separate
ObumAI Core deployment *recreates its Ollama container*, a trusted operator
must re-run the `--connect` script; normal Docker container restarts retain
the membership, but Compose recreation may not.

Rollback is to set `SMARTPLOY_LOCAL_AI_ENABLED=false` in the private env
and redeploy SmartPloy. The document editor continues working. A trusted
operator can additionally disconnect SmartPloy's API from the model-only
Docker network when revoking the integration.

The adapter refuses non-local model hostnames, HTTPS external providers,
alternative ports, URL credentials, query strings and redirects. An
unreachable model or missing model name is displayed as a bounded
non-secret failure category, never as raw HTTP response text.

Do not publish the Ollama port, attach SmartPloy to ObumAI's entire
`obum-private` network, paste private env contents, or change Cloudflare
authentication to make this integration work.

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
