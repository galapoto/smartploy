"""Single-job, two-popup submission claim must not be revision-bypassable."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "browser-companion"


def test_exact_job_identity_is_stable_and_lock_is_mandatory():
    module = (ROOT / "attempt-lock.mjs").read_text()
    popup = (ROOT / "popup.mjs").read_text()
    assert 'packet.workspace_id' in module
    assert 'url.origin, job' in module
    assert 'packet.revision' not in module
    assert 'packet.document_sha256' not in module
    assert '"smartploy.submit."' in module
    assert 'lockManager.request(key, { mode: "exclusive" }' in module
    assert 'navigator.locks' in popup
    assert 'withSubmissionLock(key, navigator.locks' in popup
    # A lockless browser must fail closed; never fall back to an unguarded click.
    assert 'Exclusive application lock unavailable.' in module
    assert 'attempted_at: new Date().toISOString()' in popup
    assert popup.index('chrome.storage.local.set({[key]:') < popup.index('func: submitOnce')
    assert popup.index('withSubmissionLock(key, navigator.locks') < popup.index('chrome.storage.local.set({[key]:')


def test_attempt_helper_has_no_hidden_site_or_employer_network_authority():
    module = (ROOT / "attempt-lock.mjs").read_text()
    for banned in ("fetch(", "XMLHttpRequest(", "document.cookie", "innerHTML",
                   "chrome.tabs.", "chrome.webRequest", "eval("):
        assert banned not in module
