"""Focused offline tests for fail-closed skill/REA change evidence."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "scripts/check_component_skill_gate.py"
spec = importlib.util.spec_from_file_location("component_skill_gate", SRC)
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

RECEIPT = "docs/skills/receipts/20261118-ci-test.json"
CHANGED = [
    "AGENTS.md", "Dockerfile", "web/src/sp-v4-card-surfaces.css",
    "tests/test_component_skill_gate.py", RECEIPT
]


def evidence():
    names = {
        "governance": "AGENTS.md",
        "delivery": "Dockerfile",
        "ui": "web/src/sp-v4-card-surfaces.css",
        "qa": "tests/test_component_skill_gate.py",
    }
    return {
        "schema": "smartploy-component-skill-evidence-v1",
        "baseline_sha": "1" * 40,
        "user_outcome": "Trace each changed component to a genuinely inspected skill and test.",
        "components": [{
            "name": name,
            "paths": [source],
            "applied_method": "Inspected exact skill guidance and checked changed source behavior.",
            "skills": [{
                "name": "verified component design and reuse skill",
                "repository": "https://github.com/docker/skills",
                "commit": "a" * 40,
                "path": "skills/docker-build-strategies/SKILL.md",
                "mode": "GUIDANCE_APPLIED",
                "applied": "Validated changed source against pinned guidance.",
            }],
            "rea_status": "REA_NOT_APPLICABLE",
            "rea_reason": "This change adapts readable first-party code without an opaque target.",
            "reuse_provenance": "Adapted the current first-party implementation, copied none.",
            "tests": "Synthetic source and exact CI tests, not live user acceptance.",
            "measured_seconds": "NOT_MEASURED",
        } for name, source in names.items()]
    }


def write(root, data):
    path = root / RECEIPT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_skill_gate_accepts_complete_component_receipt(tmp_path):
    write(tmp_path, evidence())
    assert gate.check(CHANGED, tmp_path) == []


def test_skill_gate_rejects_missing_receipt_and_uncovered_components(tmp_path):
    missing = gate.check(CHANGED, tmp_path)
    assert any("unreadable JSON" in message or "Missing component receipts" in message
               for message in missing)
    sample = evidence()
    sample["components"] = sample["components"][:-1]
    write(tmp_path, sample)
    assert "qa" in " ".join(gate.check(CHANGED, tmp_path))


def test_skill_gate_rejects_fictitious_skill_or_rea_decision(tmp_path):
    for property_name, bad in [
        ("commit", "not-an-immutable-sha"),
        ("path", "README.md"),
        ("mode", "SAID_TO_HAVE_USED"),
    ]:
        data = evidence()
        data["components"][0]["skills"][0][property_name] = bad
        write(tmp_path, data)
        assert gate.check(CHANGED, tmp_path)
    data = evidence()
    data["components"][0]["rea_status"] = "REA_APPLIED_AUTOMATICALLY"
    write(tmp_path, data)
    assert gate.check(CHANGED, tmp_path)


def test_skill_gate_rejects_wrong_source_coverage_and_fabricated_speed(tmp_path):
    data = evidence()
    data["components"][0]["paths"] = ["not/in/diff.py"]
    write(tmp_path, data)
    assert gate.check(CHANGED, tmp_path)
    data = evidence()
    data["components"][0]["measured_seconds"] = "10x faster"
    write(tmp_path, data)
    assert gate.check(CHANGED, tmp_path)


def test_skill_gate_requires_every_changed_path_not_just_component_label(tmp_path):
    changed = [*CHANGED, "web/src/another-card.tsx"]
    data = evidence()
    write(tmp_path, data)
    failures = gate.check(changed, tmp_path)
    assert any("web/src/another-card.tsx" in message for message in failures)


def test_skill_gate_requires_actual_evidence_for_claimed_execution(tmp_path):
    data = evidence()
    skill = data["components"][0]["skills"][0]
    skill["mode"] = "EXECUTED"
    write(tmp_path, data)
    assert any("actual tool evidence" in message
               for message in gate.check(CHANGED, tmp_path))
    skill["execution_evidence"] = "Runner log proves this pinned skill command executed."
    write(tmp_path, data)
    assert gate.check(CHANGED, tmp_path) == []


def test_non_code_receipt_change_does_not_recurse(tmp_path):
    assert gate.check([RECEIPT], tmp_path) == []


def test_native_woodpecker_enforces_changed_component_receipts():
    pipeline = (Path(__file__).resolve().parents[1] /
                ".woodpecker/smartploy.yaml").read_text(encoding="utf-8")
    assert "scripts/check_component_skill_gate.py --base" in pipeline
    assert "git rev-parse FETCH_HEAD" in pipeline
    assert "git cat-file -p HEAD" in pipeline
    assert 'git fetch --no-tags origin "$base"' in pipeline
    assert 'git cat-file -e "$base^{tree}"' in pipeline
    assert "scripts/obumdelivery_ci_gate.py validate" in pipeline
    assert "scripts/obumdelivery_ci_gate.py final" in pipeline


def test_smartploy_v3_adopts_skills_without_importing_obumai_interfaces():
    root = Path(__file__).resolve().parents[1]
    governance = (root / "AGENTS.md").read_text(encoding="utf-8")
    adapted = (root / "docs/v4/SMARTPLOY_2027_V3_APPLICABILITY_20261118.md").read_text(encoding="utf-8")
    assert "SMARTPLOY-2027-V3-APPLICABLE-001" in governance
    for requirement in ["REA_NOT_APPLICABLE", "USER_VERIFIED",
                        "Woodpecker", "AutoApply", "Cop", "one-use"]:
        assert requirement.lower() in adapted.lower()
    assert "P01–P16" in adapted
    assert "not a new product blueprint" in adapted.lower()
