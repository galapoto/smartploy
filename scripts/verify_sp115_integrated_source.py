"""SP115 read-only integrated SmartPloy source inventory gate.

No GitHub access, credentials, applicant CVs, network calls, file writes,
production commands, browser sessions, or employer actions. This verifies
the exact Git-blob identities of code already tested in PRs #275–#280.
It is NOT a production release authorization or runtime attestation.
"""
from __future__ import annotations

import argparse
from hashlib import sha1
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("docs/SP115_SOURCE_INVENTORY.json")
EXPECTED_SCHEMA = "smartploy.integrated_release_candidate.sp115.v1"
EXPECTED_BASE = "804747bd9f01f999f9e806dcf96459bb215bb8f1"
EXPECTED_HEAD = "d98881296081007c8e70447982cce67e847dcb94"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SOURCE_PR_NUMBERS = [275, 276, 277, 278, 279, 280]
MANDATORY = frozenset({
    "AGENTS.md", ".github/workflows/ci.yml",
    "web/src/App.tsx", "web/src/StartChoices.tsx",
    "web/src/ApplicationJourney.tsx", "web/src/ApplicationStudio.tsx",
    "web/src/AuthorizedAutoApplyBatch.tsx",
    "web/src/LocalPlaywrightAssist.tsx", "web/src/localPlaywrightBridge.ts",
    "web/src/types.ts", "web/browser-tests/onboarding.e2e.ts",
    "smartploy/api.py", "smartploy/browser_handoff.py",
    "browser-playwright/assistant.py", "browser-playwright/bridge.py",
    "web/scripts/package_playwright_assistant.py",
    "browser-companion/logic.mjs", "browser-companion/questions.mjs",
    "browser-companion/page-questions.mjs", "browser-companion/popup.mjs",
    "deploy/personal/scripts/deploy.sh",
    "deploy/personal/scripts/release-evidence.sh",
    "deploy/personal/web.Caddyfile",
    "tests/test_autoapply_e2e_contract.py",
    # SP116 intentional extension: all new private profile and UI sources.
    "smartploy/profile.py", "smartploy/account_erasure.py",
    "smartploy/application_question_memory.py",
    "smartploy/profile_cv_suggestions.py",
    "migrations/030_application_profile_questions.sql",
    "web/src/ApplicationProfilePanel.tsx",
    "web/src/ApplicationProfilePanel.test.tsx",
    "web/src/application-profile.css",
    "web/src/api.ts", "web/src/App.test.tsx",
    "web/src/LocalPlaywrightAssist.test.tsx",
    "tests/test_application_question_memory.py",
    "tests/test_application_question_memory_oidc.py",
    "docs/SP116_PERSISTENT_APPLICATION_PROFILE.md",
    # SP117 original Chrome classifier and OIDC-only companion sync.
    "browser-companion/popup.html",
    "browser-companion/manifest.json",
    "browser-companion/question-sync.mjs",
    "browser-companion/page-question-sync.mjs",
    "browser-companion/tests/question-sync.test.mjs",
    "browser-companion/tests/page-question-sync.test.mjs",
    "web/scripts/package_companion.py",
    "docs/SP117_CHROME_QUESTION_SYNC.md",
    # SP118 exact ATS assistance; no applicant data or remote final action.
    "browser-playwright/INSTALL.txt",
    "browser-companion/upload.mjs",
    "browser-companion/tests/logic.test.mjs",
    "browser-companion/tests/upload.test.mjs",
    "tests/test_browser_handoff.py",
    "tests/test_playwright_assistant.py",
    "tests/test_playwright_assistant_chromium.py",
    "docs/SP118_TALENTADORE_ASSISTED_DEMO.md",
})


class CandidateGateError(ValueError):
    """Unreviewed or altered application-release candidate; do not deploy."""


def git_blob_sha1(data: bytes) -> str:
    """Match Git's exact blob content identity without invoking Git."""
    prefix = b"blob " + str(len(data)).encode("ascii") + b"\x00"
    return sha1(prefix + data).hexdigest()  # noqa: S324 - Git's defined object ID


def verify_source_blob(expected_sha: str, data: bytes) -> None:
    if not isinstance(expected_sha, str) or not SHA40.fullmatch(expected_sha):
        raise CandidateGateError("Invalid pinned source blob identity")
    if git_blob_sha1(data) != expected_sha:
        raise CandidateGateError("A reviewed application source blob changed")


def _safe_relative_path(path: Any) -> PurePosixPath:
    if not isinstance(path, str) or not path or "\\" in path or "\x00" in path:
        raise CandidateGateError("Unsafe source inventory entry")
    pure = PurePosixPath(path)
    if (pure.is_absolute() or path != pure.as_posix() or
            any(piece in {".", "..", ""} for piece in path.split("/"))):
        raise CandidateGateError("Unsafe source inventory entry")
    return pure


def verify_inventory(root: Path, manifest: dict[str, Any]) -> int:
    if not isinstance(manifest, dict) or manifest.get("schema") != EXPECTED_SCHEMA:
        raise CandidateGateError("Source inventory schema is unknown")
    if (manifest.get("base_main_sha") != EXPECTED_BASE or
            manifest.get("source_head_sha") != EXPECTED_HEAD):
        raise CandidateGateError("Source baseline or integrated head changed")
    prs = manifest.get("source_dependency_prs")
    if (not isinstance(prs, list) or
            [item.get("pr") for item in prs if isinstance(item, dict)] != SOURCE_PR_NUMBERS or
            len(prs) != len(SOURCE_PR_NUMBERS) or
            [item.get("head") for item in prs if isinstance(item, dict)][-1] != EXPECTED_HEAD or
            any(not isinstance(item.get("head"), str) or
                not SHA40.fullmatch(item["head"]) for item in prs)):
        raise CandidateGateError("Integrated dependency PR identities changed")
    scope = manifest.get("scope")
    release = manifest.get("release")
    if (not isinstance(scope, dict) or not isinstance(release, dict) or
            scope.get("automatic_unattended_employer_submission_authorized") is not False or
            scope.get("local_browser_employer_submit_automatic") is not False or
            scope.get("browser_observation_counts_as_provider_acknowledgement") is not False or
            scope.get("production_verified") is not False or
            release.get("state") != "INTEGRATION_SOURCE_REVIEW_HOLD" or
            release.get("approval_required") is not True or
            release.get("independent_code_privacy_review_required") is not True or
            release.get("native_delivery_ci_required") is not True or
            release.get("production_deployment_approved") is not False or
            release.get("real_employer_acceptance_verified") is not False):
        raise CandidateGateError("Unsafe or falsely approved production status")
    rea = manifest.get("rea")
    if (not isinstance(rea, dict) or rea.get("status") != "REA_BLOCKED" or
            rea.get("savings") != "unknown"):
        raise CandidateGateError("REA evidence must be stated accurately")
    artifacts = manifest.get("source_artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != len(MANDATORY):
        raise CandidateGateError("Source inventory is missing critical files")
    observed: set[str] = set()
    for item in artifacts:
        if not isinstance(item, dict) or set(item) != {"path", "git_blob_sha1"}:
            raise CandidateGateError("Unexpected source inventory object")
        pure = _safe_relative_path(item["path"])
        path = pure.as_posix()
        if path not in MANDATORY or path in observed:
            raise CandidateGateError("Unreviewed or duplicate source inventory path")
        observed.add(path)
        target = root.joinpath(*pure.parts)
        if not target.is_file() or target.is_symlink():
            raise CandidateGateError("Missing or linked reviewed source file")
        verify_source_blob(item["git_blob_sha1"], target.read_bytes())
    if observed != MANDATORY:
        raise CandidateGateError("An essential application file was omitted")
    return len(observed)


def main() -> int:
    parser = argparse.ArgumentParser(description=(
        "Verify the pinned source identity of the SP115 review candidate. "
        "Source only; does not authorize or deploy to production."
    ))
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        source = (args.root / MANIFEST).read_text(encoding="utf-8")
        count = verify_inventory(args.root, json.loads(source))
    except (OSError, ValueError, TypeError) as exc:
        print("sp115_integrated_source_verified=false")
        print("sp115_release_approved=false")
        print("sp115_check=" + type(exc).__name__)
        return 1
    print("sp115_integrated_source_verified=true")
    print("sp115_source_files=" + str(count))
    print("sp115_release_approved=false")
    print("sp115_production_verified=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
