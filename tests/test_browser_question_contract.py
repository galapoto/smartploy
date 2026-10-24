"""Review-only question-fill guarantees, no unattended submit or external calls."""
from pathlib import Path
import json

EXT = Path(__file__).resolve().parents[1] / "browser-companion"


def test_question_assistant_never_extends_extension_authority():
    manifest = json.loads((EXT / "manifest.json").read_text())
    assert set(manifest["permissions"]) == {"activeTab", "scripting", "storage"}
    for disallowed in ("host_permissions", "content_scripts", "background"):
        assert disallowed not in manifest


def test_only_user_approved_text_field_values_enter_employer_form():
    popup = (EXT / "popup.mjs").read_text()
    question = (EXT / "questions.mjs").read_text()
    page = (EXT / "page-questions.mjs").read_text()
    html = (EXT / "popup.html").read_text()
    assert 'id="reviewQuestions"' in html
    assert 'id="fillQuestions"' in html
    assert 'onReviewQuestions' in popup and 'onFillQuestions' in popup
    assert 'validatePacket(currentPacketToJSON(), tab.url)' in popup
    assert '"FILL " + actions.length + " REVIEWED EMPLOYER ANSWERS?' in popup
    assert popup.index('"FILL " + actions.length') < popup.index('func: fillReviewedAnswers')
    assert 'chrome.storage.local.get(key)' in popup
    assert 'validateReviewedAnswers(currentQuestionPlan, values)' in popup
    assert 'questionPanel").hidden = true' in popup
    assert 'el.dispatchEvent(new Event("input"' in page
    assert 'el.dispatchEvent(new Event("change"' in page
    assert 'live[a.index] !== el' in page
    assert 'location.href !== inspectedUrl' in page
    assert 'getClientRects().length === 0' in page
    assert 'salary' in question and 'työlupa' in question and 'lön' in page
    assert 'MAX_QUESTION_ITEMS = 12' in question
    for bad in ("fetch(", "XMLHttpRequest(", "document.cookie", "innerHTML",
                "eval(", "chrome.webRequest", "chrome.runtime.onMessage"):
        assert bad not in question + page


def test_answers_are_ephemeral_and_submit_remains_separately_approved():
    source = (EXT / "popup.mjs").read_text()
    beginning = source.index("async function onFillQuestions()")
    end = source.index("async function onPreflight()")
    function_body = source[beginning:end]
    assert 'chrome.storage.local.set(' not in function_body
    assert 'submitOnce' not in function_body
    assert 'func: fillReviewedAnswers' in function_body
    assert '"submit").disabled = true' in function_body
    assert 'currentQuestionPlan = null' in function_body
    assert '"questionList").replaceChildren()' in function_body
    # SP26: question filling NEVER grants employer-submit authority; only a
    # separate, signed-in final-click decision with independently approved
    # employer rights can consume a cross-device sticky claim.
    assert 'func: submitOnce' not in source
    assert 'live[0].click()' not in source
    assert 'func: reserveFinalClickOnSmartPloy' in source
    assert 'func: submitReviewedLeverOnce' in source
    assert 'requireOneUseFinalAttempt(chrome.storage.session, packet)' in source
    assert source.index('async function onPreflight()') < source.index(
        'async function onSubmit()')
