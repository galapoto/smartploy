"""No hidden browser authority, no persistent sensitive extension data."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "browser-companion"


def test_browser_companion_only_runs_on_user_clicked_active_tab():
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    assert set(manifest["permissions"]) <= {"activeTab", "scripting", "storage"}
    assert "host_permissions" not in manifest
    assert "background" not in manifest
    assert "content_scripts" not in manifest
    assert "web_accessible_resources" not in manifest
    assert (ROOT / "icon128.png").stat().st_size > 100


def test_extension_never_exfiltrates_packets_or_actuates_submit_without_user_click():
    source = (ROOT / "popup.mjs").read_text(encoding="utf-8")
    policy = (ROOT / "logic.mjs").read_text(encoding="utf-8")
    assert 'chrome.storage.local.set({[key]:' in source
    assert source.index('chrome.storage.local.set({[key]:') < source.index('func: submitOnce')
    assert 'if (!window.confirm(' in source
    assert '$("approve").checked' in source
    assert 'window.confirm(' in source
    assert 'browser companion' in source.lower()
    assert 'attemptReserved = true' in source
    assert 'autoSubmitAllowed: false' in policy
    assert 'onResumeReceipt' in source
    assert 'const stored = await chrome.storage.local.get(key)' in source
    assert 'here.pathname.startsWith("/" + account + "/")' in source
    assert 'smartploy.browser_receipt.v1' in source
    assert 'confirmed_visible: true' in source
    assert 'confirmation_page_sha256:' in source
    for unsafe in ("eval(", "innerHTML", "chrome.runtime.onMessage", "chrome.webRequest",
                   'fetch(', "XMLHttpRequest(", "document.cookie"):
        assert unsafe not in source + policy
    assert "target: { tabId: tab.id }" in source or "target: {tabId: tab.id}" in source
