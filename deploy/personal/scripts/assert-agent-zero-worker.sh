#!/usr/bin/env bash
# SP36 read-only Agent Zero runtime gate. No secrets, CVs or applicant cases
# are emitted. This checks a real worker task, not /healthz's generic count.
set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${COMPOSE_DIR}/env"
POLICY_FILE="$(bash "${SCRIPT_DIR}/select-runtime-policy.sh")"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"

[[ $# -eq 0 ]] || { echo "Usage: assert-agent-zero-worker.sh" >&2; exit 2; }
[[ -f "${ENV_FILE}" && ! -L "${ENV_FILE}" ]] || {
  echo "SmartPloy Agent Zero runtime: private env is unavailable" >&2
  exit 1
}
# Old private production env files remain compatible and OFF by default.
COUNT="$(grep -c '^SMARTPLOY_WORKER_AGENT_ZERO_ENABLED=' "${ENV_FILE}" || true)"
[[ "${COUNT}" =~ ^[01]$ ]] || {
  echo "SmartPloy Agent Zero runtime: duplicate host opt-in is forbidden" >&2
  exit 1
}
FLAG="false"
if [[ "${COUNT}" == "1" ]]; then
  FLAG="$(sed -n 's/^SMARTPLOY_WORKER_AGENT_ZERO_ENABLED=//p' "${ENV_FILE}")"
fi
[[ "${FLAG}" == "true" || "${FLAG}" == "false" ]] || {
  echo "SmartPloy Agent Zero runtime: opt-in must be literal true or false" >&2
  exit 1
}

COMPOSE=(
  docker compose --env-file "${ENV_FILE}" --env-file "${POLICY_FILE}"
  -f "${COMPOSE_FILE}"
)
# Render only to a pipe. It may contain sensitive credentials; NEVER print or
# persist the JSON. Verify that the feature flag goes only to worker.
"${COMPOSE[@]}" config --format json |
  python3 -c '
import json, sys
data = json.load(sys.stdin)["services"]
for name in ("api", "web", "postgres"):
    assert "SMARTPLOY_WORKER_AGENT_ZERO_ENABLED" not in data[name].get("environment", {}), (
        "Agent Zero scheduler toggle leaked outside worker"
    )
worker = data["worker"].get("environment", {})
assert worker.get("SMARTPLOY_WORKER_AGENT_ZERO_ENABLED") == sys.argv[1], (
    "Agent Zero host and running Compose opt-in differ"
)
assert 1 <= int(worker.get("SMARTPLOY_WORKER_AGENT_ZERO_CADENCE_SECONDS", "")) <= 86400
assert 1 <= int(worker.get("SMARTPLOY_WORKER_AGENT_ZERO_BATCH_LIMIT", "")) <= 50
' "${FLAG}"

WORKER_ID="$("${COMPOSE[@]}" ps -q worker)"
[[ "${WORKER_ID}" =~ ^[0-9a-f]{12,64}$ ]] || {
  echo "SmartPloy Agent Zero runtime: worker container is not running" >&2
  exit 1
}
WORKER_STARTED="$(docker inspect --format '{{.State.StartedAt}}' "${WORKER_ID}")"
[[ "${WORKER_STARTED}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T ]] || {
  echo "SmartPloy Agent Zero runtime: worker start timestamp missing" >&2
  exit 1
}

if [[ "${FLAG}" == "true" ]]; then
  # Only a completed task run AFTER the current worker container started is
  # proof of this release's scheduler. Zero candidate events may be due.
  REPORT="$("${COMPOSE[@]}" exec -T worker     python -m smartploy.agent_zero_runtime_acceptance     --require-run --not-before "${WORKER_STARTED}" --wait-seconds 100)"
else
  REPORT="$("${COMPOSE[@]}" exec -T worker     python -m smartploy.agent_zero_runtime_acceptance --wait-seconds 25)"
fi

# Convert the safe short JSON to a bounded, stable release-evidence contract.
# Never echo the configured DB URL or worker task metadata.
printf '%s\n' "${REPORT}" | python3 -c '
import json, sys
result = json.load(sys.stdin)
expected = "healthy_scheduled_run" if sys.argv[1] == "true" else "disabled_by_operator"
assert result["schema"] == "smartploy.agent_zero.runtime.v1"
assert result["status"] == expected
assert result["external_actions_authorized"] is False
assert result["employer_contacts_authorized"] is False
assert result["candidate_reminder_delivered_verified"] is False
print("SmartPloy Agent Zero runtime: PASS")
print("agent_zero_mode=" + result["status"])
print("agent_zero_operator_enabled=" + sys.argv[1])
print("agent_zero_scheduled_run_verified=" +
      ("true" if result["completed_run_verified"] else "false"))
print("agent_zero_candidate_reminder_verified=false")
print("agent_zero_employer_contacts_authorized=false")
' "${FLAG}"
