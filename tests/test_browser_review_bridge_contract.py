"""SP26: first-party reviewed-packet and one-shot final claim remain isolated.

The extension has no background runner, wildcard host grants or cookie
exfiltration. Only an authenticated sticky server claim plus applicant click
can lead to a final employer action.
"""
from pathlib import Path
import json

EXT=Path(__file__).resolve().parents[1]/"browser-companion"


def test_exact_existing_mv3_capabilities_and_first_party_claim_gate():
    manifest=json.loads((EXT/"manifest.json").read_text())
    popup=(EXT/"popup.mjs").read_text()
    markup=(EXT/"popup.html").read_text()
    assert manifest["manifest_version"]==3
    assert set(manifest["permissions"])=={"activeTab","scripting","storage"}
    for forbidden in ("host_permissions","background","content_scripts","externally_connectable"):
        assert forbidden not in manifest
    assert "func: submitOnce" not in popup
    assert "live[0].click()" not in popup
    assert "await requireOneUseFinalAttempt(chrome.storage.session, packet)" in popup
    assert "func: reserveFinalClickOnSmartPloy" in popup
    assert "func: submitReviewedLeverOnce" in popup
    assert 'disabled aria-disabled="true"' in markup
    assert "func: verifyReviewOnSmartPloy" in popup
    assert 'world: "ISOLATED"' in popup
    assert "chrome.storage.session" in popup
    assert 'verifyReview").addEventListener' in popup
    assert 'id="verifyReview"' in markup
    assert "Only a short-lived review fingerprint" in popup
    assert popup.count("await requireVerifiedReview(")>=5


def test_existing_employer_autofill_requires_prior_signed_in_verified_packet():
    popup=(EXT/"popup.mjs").read_text()
    def handler(start,finish):
        return popup.split(start,1)[1].split(finish,1)[0]
    assert handler("async function onInspect()", "async function onFill()").index(
        "await requireVerifiedReview") < handler(
        "async function onInspect()", "async function onFill()"
        ).index("func: inspectForm")
    for start,end in (
        ("async function onFill()","async function onAttach()"),
        ("async function onAttach()","function currentPacketToJSON()"),
        ("async function onReviewQuestions()","async function onFillQuestions()"),
        ("async function onFillQuestions()","async function onPreflight()"),
    ):
        body=handler(start,end)
        assert "await requireVerifiedReview" in body


def test_only_first_party_injected_page_may_make_browser_review_network_calls():
    popup=(EXT/"popup.mjs").read_text()
    page=(EXT/"page-review.mjs").read_text()
    policy=(EXT/"review-bridge.mjs").read_text()
    assert "fetch(" not in popup
    assert "document.cookie" not in popup+page+policy
    assert "XMLHttpRequest(" not in popup+page+policy
    assert "innerHTML" not in page+policy
    assert page.count("fetch(")==2
    assert "https://smartploy.komplyint.fi" in page
    assert "https://smartploy.obumai.com" in page
    assert "allowedOrigins.includes(location.origin)" in page
    assert 'redirect: "error"' in page
    assert "window.top !== window.self" in page
    assert 'credentials: "same-origin"' in page
    assert '"/api/v1/session"' in page
    assert '"/verify-reviewed-packet"' in page
    assert "user_id: session.user_id" not in page
    assert "token:" not in page
    assert "Authorization" not in page
    assert "review_verified: true" in page
    assert "browser_grant_issued: false" in page
    assert "reviewSessionKey" in policy
    assert "storage.set({ [key]:" in policy
    assert "chrome.storage.local" not in page+policy

def test_new_browser_claim_stays_on_first_party_and_employer_click_has_no_server_session():
    page=(EXT/"page-final-claim.mjs").read_text()
    employer=(EXT/"page-final-submit.mjs").read_text()
    popup=(EXT/"popup.mjs").read_text()
    assert "allowedOrigins.includes(location.origin)" in page
    assert 'redirect: "error"' in page
    assert page.count("fetch(")==2
    assert "document.cookie" not in page+employer+popup
    assert "fetch(" not in employer+popup
    assert "XMLHttpRequest(" not in employer
    assert "chrome.runtime" not in employer
    assert "chrome.storage.local.set" in popup
    assert "finalButton.click()" in employer
    assert "provider_acknowledged: false" in employer
    assert "cv.arrayBuffer()" in employer
    assert "crypto.subtle.digest" in employer
    assert "captcha" in employer
