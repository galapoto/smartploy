"""SP15d: first-party reviewed-packet verification may prepare fields only.

The actual extension has no background runner, host grants or external cookie
authority, and its final employer Submit click remains absent.
"""
from pathlib import Path
import json

EXT=Path(__file__).resolve().parents[1]/"browser-companion"


def test_exact_existing_mv3_capabilities_and_no_final_employer_click():
    manifest=json.loads((EXT/"manifest.json").read_text())
    popup=(EXT/"popup.mjs").read_text()
    markup=(EXT/"popup.html").read_text()
    assert manifest["manifest_version"]==3
    assert set(manifest["permissions"])=={"activeTab","scripting","storage"}
    for forbidden in ("host_permissions","background","content_scripts","externally_connectable"):
        assert forbidden not in manifest
    assert "func: submitOnce" not in popup
    assert "live[0].click()" not in popup
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
    assert "https://smartploy.obumai.com" in page
    assert 'location.origin !== origin' in page
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
