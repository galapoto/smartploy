"""Review-only MV3 companion: no hidden network or local-only employer submit."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "browser-companion"


def test_companion_runs_only_on_the_user_clicked_active_tab():
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    assert set(manifest["permissions"]) <= {"activeTab", "scripting", "storage"}
    assert "host_permissions" not in manifest
    assert "background" not in manifest
    assert "content_scripts" not in manifest
    assert "web_accessible_resources" not in manifest
    assert (ROOT / "icon128.png").stat().st_size > 100


def test_companion_cannot_automatically_click_submit_before_server_grant_exists():
    source = (ROOT / "popup.mjs").read_text(encoding="utf-8")
    policy = (ROOT / "logic.mjs").read_text(encoding="utf-8")
    html = (ROOT / "popup.html").read_text(encoding="utf-8")
    assert 'if (!window.confirm(' in source
    assert 'window.confirm(' in source  # approved field/PDF transfer still requires click
    assert "browser companion" in source.lower()
    assert 'autoSubmitAllowed: false' in policy
    assert 'onResumeReceipt' in source
    assert 'const stored = await chrome.storage.local.get(key)' in source
    assert 'here.pathname.startsWith("/" + account + "/")' in source
    assert 'smartploy.browser_receipt.v1' in source
    assert 'confirmed_visible: true' in source
    assert 'confirmation_page_sha256:' in source
    assert 'async function onSubmit()' in source
    assert 'Automatic final submission is unavailable until cross-device server authorization' in source
    assert "func: submitOnce" not in source
    assert "live[0].click()" not in source
    assert 'disabled aria-disabled="true"' in html
    for unsafe in ("eval(", "innerHTML", "chrome.runtime.onMessage", "chrome.webRequest",
                   'fetch(', "XMLHttpRequest(", "document.cookie"):
        assert unsafe not in source + policy
    assert "target: { tabId: tab.id }" in source or "target: {tabId: tab.id}" in source
