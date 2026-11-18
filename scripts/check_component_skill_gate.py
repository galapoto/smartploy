"""CI component-skill and REA evidence gate, no dependencies or network.

For PR synthetic merge and normal main merge, HEAD^..HEAD covers all
current changes. Fail closed on missing receipts or unsupported evidence.
A machine-readable receipt documents skill application; it cannot prove that
an agent executed an external skill runtime, or that a UI looks good.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

RECEIPTS = "docs/skills/receipts/"
SHA = re.compile(r"^[0-9a-f]{40}$")
SKILL_MODES = {"GUIDANCE_APPLIED", "EXECUTED"}
REA_STATUSES = {"REA_APPLIED", "REA_NOT_APPLICABLE", "REA_BLOCKED"}


def component(path: str) -> str | None:
    if path.startswith(RECEIPTS):
        return None
    if path in {"AGENTS.md"}:
        return "governance"
    if path.startswith(".github/") or path.startswith(".woodpecker"):
        return "ci"
    if path in {"Dockerfile", "web/Dockerfile"} or path.startswith("deploy/"):
        return "delivery"
    if path.startswith("web/src/") or path.startswith("web/public/"):
        return "ui"
    if path.startswith("web/browser-tests/") or path.startswith("tests/"):
        return "qa"
    if path.startswith(("browser-companion/", "browser-playwright/")):
        return "browser"
    if path.startswith("smartploy/"):
        return "backend"
    if path.startswith("migrations/"):
        return "data"
    if path.startswith(("web/scripts/", "scripts/")) or path.startswith("web/package"):
        return "build"
    if path.startswith("docs/") or path in {"README.md", "pyproject.toml"}:
        return "docs"
    return "support"


def changed_between(base: str, head: str) -> list[str]:
    for ref in (base, head):
        if not ref or ref.startswith("-"):
            raise ValueError("Base and head revisions must be explicit git references")
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", base, head, "--"],
        check=True, capture_output=True, text=True,
    )
    return sorted(set(result.stdout.splitlines()))


def _text(value: object) -> bool:
    return isinstance(value, str) and 8 <= len(value.strip()) <= 2000


def check(changed: list[str], root: Path) -> list[str]:
    needed = {component(path) for path in changed}
    needed.discard(None)
    if not needed:
        return []
    candidates = sorted(path for path in changed
                        if path.startswith(RECEIPTS) and path.endswith(".json"))
    if not candidates:
        return ["Changed components require a new/updated docs/skills/receipts/*.json"]
    errors: list[str] = []
    covered: set[str] = set()
    covered_paths: set[str] = set()
    for path in candidates:
        if ".." in Path(path).parts or (root / path).is_symlink():
            errors.append(f"{path}: invalid receipt path")
            continue
        try:
            receipt = json.loads((root / path).read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            errors.append(f"{path}: unreadable JSON ({type(exc).__name__})")
            continue
        if receipt.get("schema") != "smartploy-component-skill-evidence-v1":
            errors.append(f"{path}: invalid evidence schema")
        if not SHA.fullmatch(str(receipt.get("baseline_sha", ""))):
            errors.append(f"{path}: a pinned baseline_sha is required")
        if not _text(receipt.get("user_outcome")):
            errors.append(f"{path}: a specific outcome is required")
        records = receipt.get("components")
        if not isinstance(records, list) or not records:
            errors.append(f"{path}: missing components array")
            continue
        for record in records:
            if not isinstance(record, dict):
                errors.append(f"{path}: component record must be an object")
                continue
            group = record.get("name")
            if group not in needed:
                errors.append(f"{path}: unexpected component {group!r}")
                continue
            touched = record.get("paths")
            if not isinstance(touched, list) or not touched or not all(
                isinstance(p, str) and p in changed and component(p) == group
                for p in touched
            ):
                errors.append(f"{path}:{group}: paths must be exact changed files")
                continue
            covered_paths.update(touched)
            if not _text(record.get("applied_method")):
                errors.append(f"{path}:{group}: actual skill application is required")
            skills = record.get("skills")
            if not isinstance(skills, list) or not skills:
                errors.append(f"{path}:{group}: at least one actual skill is required")
            else:
                for skill in skills:
                    if not isinstance(skill, dict) or skill.get("mode") not in SKILL_MODES:
                        errors.append(f"{path}:{group}: invalid skill usage mode")
                        continue
                    if skill.get("mode") == "EXECUTED" and not _text(
                        skill.get("execution_evidence")
                    ):
                        errors.append(f"{path}:{group}: executed skill requires actual tool evidence")
                    upstream = skill.get("repository")
                    uri = skill.get("installed_uri")
                    if not _text(skill.get("name")) or not _text(skill.get("applied")):
                        errors.append(f"{path}:{group}: identify the skill and specific use")
                    if uri:
                        if not isinstance(uri, str) or not uri.startswith("skills://"):
                            errors.append(f"{path}:{group}: invalid installed skill URI")
                    elif not (isinstance(upstream, str)
                              and upstream.startswith("https://github.com/")
                              and SHA.fullmatch(str(skill.get("commit", "")))
                              and isinstance(skill.get("path"), str)
                              and skill["path"].endswith("SKILL.md")):
                        errors.append(f"{path}:{group}: skill needs installed URI or pinned GitHub SKILL.md")
            if record.get("rea_status") not in REA_STATUSES:
                errors.append(f"{path}:{group}: REA decision missing")
            if not _text(record.get("rea_reason")):
                errors.append(f"{path}:{group}: explain REA decision and scope")
            if not _text(record.get("reuse_provenance")) or not _text(record.get("tests")):
                errors.append(f"{path}:{group}: reuse and test evidence required")
            if record.get("measured_seconds") not in {"NOT_MEASURED"} and not (
                isinstance(record.get("measured_seconds"), (int, float))
                and record["measured_seconds"] >= 0
            ):
                errors.append(f"{path}:{group}: measured_seconds or NOT_MEASURED required")
            covered.add(group)
    if needed - covered:
        errors.append("Missing component receipts: " + ", ".join(sorted(needed - covered)))
    uncovered_paths = sorted(
        p for p in changed if component(p) is not None and p not in covered_paths
    )
    if uncovered_paths:
        errors.append("Changed files without skill adoption evidence: " +
                      ", ".join(uncovered_paths))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="HEAD^")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    try:
        changed = changed_between(args.base, args.head)
        failures = check(changed, Path("."))
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(f"COMPONENT_SKILLS_GATE=FAIL git_diff={exc}")
        return 1
    if failures:
        print("COMPONENT_SKILLS_GATE=FAIL")
        for problem in failures:
            print(" - " + problem)
        return 1
    print(f"COMPONENT_SKILLS_GATE=PASS changed_files={len(changed)} "
          f"components={len({component(p) for p in changed if component(p)})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
