"""SP130: negative controls on the production GitHub→host trust boundary."""
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/feature-first-production.yml"
REMOTE = ROOT / "deploy/personal/scripts/feature-first-remote-promotion.sh"
GATE = ROOT / "deploy/personal/scripts/feature-first-ssh-gate.sh"


def test_production_script_syntax_and_bounded_sha_only_ssh_gate():
    for path in (REMOTE, GATE):
        subprocess.run(["bash", "-n", str(path)], check=True, timeout=6)
    script = GATE.read_text(encoding="utf-8")
    assert "SSH_ORIGINAL_COMMAND" in script
    assert "^[0-9a-f]{40}" not in script  # exact prefixed form, not arbitrary text
    assert "^feature-first-deploy" in script
    assert "exec sudo -n /usr/local/sbin/smartploy-feature-first-dispatch" in script
    for invalid in (
        "sudo bash -i",
        "feature-first-deploy main",
        "feature-first-deploy " + "a" * 39,
        "feature-first-deploy " + "a" * 40 + " ; id",
    ):
        result = subprocess.run(
            ["bash", str(GATE)], env={"SSH_ORIGINAL_COMMAND": invalid},
            capture_output=True, text=True, timeout=6, check=False,
        )
        assert result.returncode == 41
        assert "FEATURE_FIRST_DENIED" in result.stderr


def test_secrets_never_reach_pr_build_or_arbitrary_root_shell():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_run:" in workflow
    assert 'head_branch == \'main\'' in workflow
    assert "pull_request:" not in workflow.split("jobs:", 1)[0]
    assert "needs.qualify.outputs.qualified == 'true'" in workflow
    assert "vars.SMARTPLOY_FEATURE_FIRST_AUTO_DEPLOY == 'true'" in workflow
    assert "environment:" in workflow and "smartploy-production" in workflow
    assert "StrictHostKeyChecking=yes" in workflow
    assert "UserKnownHostsFile=" in workflow
    assert '"feature-first-deploy $SHA"' in workflow
    assert "sudo -n bash" not in workflow
    assert "ssh-keyscan" not in workflow
    assert "continue-on-error" not in workflow
    assert "actions/checkout@v4" in workflow
    assert workflow.count("actions/checkout@v4") == 1


def test_native_and_explicit_release_policy_are_required_separately():
    dispatcher = REMOTE.read_text(encoding="utf-8")
    assert 'native-ci-qualified-sha' in dispatcher
    assert 'feature-first-auto-eligible-sha' in dispatcher
    assert 'feature-first-approved-sha' in dispatcher
    assert 'stat -c' in dispatcher
    assert 'git merge-base --is-ancestor' in dispatcher
    assert 'SMARTPLOY_RELEASE_APPROVED_SHA="$SHA"' in dispatcher
    assert 'deploy/personal/scripts/deploy.sh' in dispatcher
    assert 'release-evidence.sh' in dispatcher
    assert 'FEATURE_FIRST_STATE=RELEASED_PENDING_SIGNED_IN_UX' in dispatcher
    assert 'USER_VERIFIED' in dispatcher


def test_release_docs_do_not_claim_prod_is_commissioned():
    docs = (ROOT / "docs/SP130_FEATURE_FIRST_CONTINUOUS_PRODUCTION.md").read_text(
        encoding="utf-8"
    )
    assert "not commissioned or live" in docs
    assert "SMARTPLOY_FEATURE_FIRST_AUTO_DEPLOY=true" in docs
    assert "rea" in docs.casefold()


def test_manual_replay_is_exact_sha_and_does_not_grant_approval():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "release_sha:" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "id: source" in workflow
    assert "sha=$SHA" in workflow
    assert "ref: ${{ steps.source.outputs.sha }}" in workflow
    assert "SMARTPLOY_REQUESTED_SHA: ${{ steps.source.outputs.sha }}" in workflow
    assert "github.event.workflow_run.conclusion == 'success'" in workflow
    assert "needs.qualify.outputs.qualified == 'true'" in workflow
    assert "SMARTPLOY_FEATURE_FIRST_AUTO_DEPLOY" in workflow
    docs = (ROOT / "docs/SP130_FEATURE_FIRST_CONTINUOUS_PRODUCTION.md").read_text(
        encoding="utf-8"
    )
    assert "Safe replay after commissioning" in docs
    assert "independently looks up an actual successful main-push" in docs
    assert "authorized_keys" in docs and "root-owned" in docs
    assert "independent release" in docs
