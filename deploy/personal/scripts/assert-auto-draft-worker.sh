#!/usr/bin/env bash
# SP59: read-only proof that the ORIGINAL private AutoDraft scheduler is active
# on the just-started worker. No CVs, job URLs, profile IDs or secrets in stdout.
set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${COMPOSE_DIR}/env"
POLICY_FILE="$(bash "${SCRIPT_DIR}/select-runtime-policy.sh")"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"

[[ $# -eq 0 ]] || { echo "Usage: assert-auto-draft-worker.sh" >&2; exit 2; }
[[ -f "${ENV_FILE}" && ! -L "${ENV_FILE}" ]] || {
  echo "SmartPloy AutoDraft runtime: private env is unavailable" >&2
  exit 1
}
bash "${SCRIPT_DIR}/validate-runtime-policy.sh" "${POLICY_FILE}" >/dev/null

# Keep omitted host opt-ins OFF, consistent with the original Python worker.
# A duplicate or ambiguous host value is never permission to prepare CVs.
COUNT="$(grep -c '^SMARTPLOY_WORKER_AUTO_DRAFT_ENABLED=' "${ENV_FILE}" || true)"
[[ "${COUNT}" == "0" || "${COUNT}" == "1" ]] || {
  echo "SmartPloy AutoDraft runtime: duplicate opt-in is forbidden" >&2
  exit 1
}
FLAG="false"
if [[ "${COUNT}" == "1" ]]; then
  FLAG="$(sed -n 's/^SMARTPLOY_WORKER_AUTO_DRAFT_ENABLED=//p' "${ENV_FILE}")"
fi
[[ "${FLAG}" == "true" || "${FLAG}" == "false" ]] || {
  echo "SmartPloy AutoDraft runtime: opt-in must be literal true or false" >&2
  exit 1
}

COMPOSE=(
  docker compose --env-file "${ENV_FILE}" --env-file "${POLICY_FILE}"
  -f "${COMPOSE_FILE}"
)
# Compose config may contain credentials: render ONLY to a pipe, never log it.
"${COMPOSE[@]}" config --format json |
  python3 -c '
import json, sys
services = json.load(sys.stdin)["services"]
for name in ("api", "web", "postgres"):
    assert "SMARTPLOY_WORKER_AUTO_DRAFT_ENABLED" not in services[name].get("environment", {}), (
        "private automatic draft opt-in leaked outside worker"
    )
worker = services["worker"].get("environment", {})
assert worker.get("SMARTPLOY_WORKER_AUTO_DRAFT_ENABLED") == sys.argv[1], (
    "worker environment differs from explicit host automatic-draft opt-in"
)
cadence = worker.get("SMARTPLOY_WORKER_AUTO_DRAFT_CADENCE_SECONDS", "")
assert str(cadence).isdigit() and 1 <= int(cadence) <= 86400, (
    "AutoDraft worker cadence invalid"
)
' "${FLAG}"

WORKER_ID="$("${COMPOSE[@]}" ps -q worker)"
[[ "${WORKER_ID}" =~ ^[0-9a-f]{12,64}$ ]] || {
  echo "SmartPloy AutoDraft runtime: worker container is not running" >&2
  exit 1
}
WORKER_STARTED="$(docker inspect --format '{{.State.StartedAt}}' "${WORKER_ID}")"
[[ "${WORKER_STARTED}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T ]] || {
  echo "SmartPloy AutoDraft runtime: worker start timestamp missing" >&2
  exit 1
}

if [[ "${FLAG}" == "true" ]]; then
  # A persisted healthy result must be newer than THIS container's start.
  # Even zero matching opted-in profiles can complete a genuine safe cycle.
  REPORT="$("${COMPOSE[@]}" exec -T worker \
    python -m smartploy.auto_draft_runtime_acceptance \
    --require-run --not-before "${WORKER_STARTED}" --wait-seconds 110)"
else
  REPORT="$("${COMPOSE[@]}" exec -T worker \
    python -m smartploy.auto_draft_runtime_acceptance --wait-seconds 25)"
fi

printf '%s\n' "${REPORT}" | python3 -c '
import json, sys
result = json.load(sys.stdin)
expected = "healthy_scheduled_run" if sys.argv[1] == "true" else "disabled_by_operator"
assert result["schema"] == "smartploy.auto_draft.runtime.v1"
assert result["status"] == expected
assert result["task_enabled"] is (sys.argv[1] == "true")
assert result["employer_contacts_authorized"] is False
assert result["candidate_drafts_created_verified"] is False
assert result["external_actions_authorized"] is False
print("SmartPloy AutoDraft runtime: PASS")
print("auto_draft_mode=" + result["status"])
print("auto_draft_operator_enabled=" + sys.argv[1])
print("auto_draft_scheduled_run_verified=" +
      ("true" if result["completed_run_verified"] else "false"))
print("auto_draft_candidate_drafts_verified=false")
print("auto_draft_employer_contacts_authorized=false")
' "${FLAG}"
