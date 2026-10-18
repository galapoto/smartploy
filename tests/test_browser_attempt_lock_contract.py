"""SP15 browser one-attempt helper is reusable, but final click fails closed."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "browser-companion"


def test_existing_lock_helper_is_retained_without_bypassing_server_claim():
    module = (ROOT / "attempt-lock.mjs").read_text()
    popup = (ROOT / "popup.mjs").read_text()
    html = (ROOT / "popup.html").read_text()

    # Keep first-party future-ready browser-profile locking and job identity
    # without inventing a new popup runner or authorizing its local-only click.
    assert "packet.workspace_id" in module
    assert "url.origin, job" in module
    assert "packet.revision" not in module
    assert "packet.document_sha256" not in module
    assert '"smartploy.submit."' in module
    assert 'lockManager.request(key, { mode: "exclusive" }' in module
    assert "Exclusive application lock unavailable." in module

    # SP15b: no user checkbox/preflight can unlock a final click while the
    # authenticated cross-device server-grant/consume protocol is missing.
    assert "preflightPassed = false; // A local preflight" in popup
    assert '"submit").disabled = true; // Requires an authenticated one-time server grant.' in popup
    assert '  $("submit").disabled = true; // User approval alone is not a server-issued claim.' in popup
    assert "func: submitOnce" not in popup
    assert "live[0].click()" not in popup
    assert "withSubmissionLock(key, navigator.locks" not in popup
    assert 'id="submit" class="danger" disabled aria-disabled="true"' in html
    assert "click the employer's own Submit button yourself" in html


def test_lock_helper_has_no_hidden_site_or_employer_network_authority():
    module = (ROOT / "attempt-lock.mjs").read_text()
    for banned in ("fetch(", "XMLHttpRequest(", "document.cookie", "innerHTML",
                   "chrome.tabs.", "chrome.webRequest", "eval("):
        assert banned not in module
