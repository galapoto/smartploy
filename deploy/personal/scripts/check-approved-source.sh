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
# Git status deliberately ignores assume-unchanged and skip-worktree entries.
# Reject both hints before admitting the exact source as production-safe.
if git -C "${REPO_ROOT}" ls-files -v |
    awk 'substr($0,1,1) ~ /[a-zS]/ { hidden=1 } END { exit !hidden }'; then
  echo "SmartPloy release source: tracked files hidden by Git index flags" >&2
  exit 3
fi
TRACKED_CHANGES="$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
if [[ -n "$TRACKED_CHANGES" ]]; then
  echo "SmartPloy release source: tracked files changed; reconcile before deployment" >&2
  exit 3
fi
# Dockerfile COPY . also includes untracked nonignored files, which are not
# identified by the approved SHA (e.g. a root-level sitecustomize.py).
# Honor ONLY tracked .gitignore patterns: --exclude-standard would also
# accept unreviewed .git/info/exclude or global core.excludesFile escapes.
# Keep legitimate private env ignored and Docker-excluded; reject all other
# untracked source before checkout, image build, backup or migration.
UNTRACKED_FILES="$(git -C "${REPO_ROOT}" ls-files --others --exclude-per-directory=.gitignore)"
if [[ -n "$UNTRACKED_FILES" ]]; then
  echo "SmartPloy release source: untracked build-context files present; reconcile before deployment" >&2
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
