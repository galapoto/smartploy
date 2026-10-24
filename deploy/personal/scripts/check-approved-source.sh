#!/usr/bin/env bash
# SP30: verify an immutable approved SmartPloy source commit before a production
# checkout. Only Git metadata is read/fetched; no containers or secrets touched.
set -Eeuo pipefail

SHA="${1:-}"
if [[ "$#" -ne 1 || ! "$SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "SmartPloy release source: provide one reviewed full 40-character Git SHA; branch names and main are refused" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
if [[ ! -d "${REPO_ROOT}/.git" && ! -f "${REPO_ROOT}/.git" ]]; then
  echo "SmartPloy release source: expected a Git checkout" >&2
  exit 2
fi

# Deploy must never use a force checkout to erase local edits. Intentional
# private/untracked deploy/personal/env stays untouched and is not printed.
TRACKED_CHANGES="$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
if [[ -n "$TRACKED_CHANGES" ]]; then
  echo "SmartPloy release source: tracked files changed; reconcile before deployment" >&2
  exit 3
fi

# Refresh only the trusted main line, not arbitrary mutable release branches.
# The reviewed exact SHA remains valid even if main advanced after approval.
GIT_TERMINAL_PROMPT=0 git -C "${REPO_ROOT}" fetch --no-tags origin main >&2
if ! git -C "${REPO_ROOT}" rev-parse --verify --quiet "refs/remotes/origin/main^{commit}" >/dev/null; then
  echo "SmartPloy release source: origin/main is unavailable" >&2
  exit 3
fi
if ! git -C "${REPO_ROOT}" cat-file -e "${SHA}^{commit}" 2>/dev/null; then
  echo "SmartPloy release source: reviewed commit is not present in local Git objects" >&2
  exit 3
fi
if ! git -C "${REPO_ROOT}" merge-base --is-ancestor "$SHA" refs/remotes/origin/main; then
  echo "SmartPloy release source: candidate is not contained in remote main history" >&2
  exit 3
fi

printf 'reviewed_release_sha=%s\n' "$SHA"
printf 'release_source_gate=PASS\n'
