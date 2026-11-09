"""Real Chromium HTTPS first-party -> local helper round trip.

One isolated synthetic packet, intercepted first-party HTML, fake employer
actor, no user data and no employer network or final submission. This tests
actual browser local-network/CORS behavior, not mocked fetch() calls.
"""
from __future__ import annotations

import pytest
from test_playwright_local_bridge import (
    SAFE_ORIGIN, PAIR_CODE, FakeActor, fake_local_http_server, packet, state
)

sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright


def test_real_https_chromium_pairs_inspects_fills_and_stops_without_send():
    bridge_state = state()
    with fake_local_http_server(bridge_state) as port, sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route(SAFE_ORIGIN + "/**", lambda route: route.fulfill(
                status=200, content_type="text/html",
                body="<!doctype html><html><head><meta charset='utf-8'></head>"
                     "<body><h1>SmartPloy synthetic signed-in test</h1></body></html>"
            ))
            page.goto(SAFE_ORIGIN + "/signed-in-review-fixture")
            result = page.evaluate(
                """async ({port,packet,pairCode}) => {
                    const origin = 'http://127.0.0.1:' + port;
                    async function post(path, value, token) {
                        const headers = {'Content-Type': 'application/json'};
                        if (token) headers.Authorization = 'Bearer ' + token;
                        const response = await fetch(origin + path, {
                            method: 'POST', credentials: 'omit',
                            referrerPolicy: 'no-referrer', mode: 'cors',
                            headers, body: JSON.stringify(value),
                        });
                        return {status: response.status, value: await response.json()};
                    }
                    const opened = await post('/v1/prepare', {
                        pairing_code: pairCode, packet,
                    });
                    if (!opened.value.token) return {opened};
                    const token = opened.value.token;
                    const inspected = await post('/v1/inspect', {}, token);
                    const filled = await post('/v1/fill', {
                        plan_id: inspected.value.plan_id,
                        confirmation: 'FILL REVIEWED FIELDS',
                    }, token);
                    const stopped = await post('/v1/stop', {}, token);
                    return {
                        opened: {status: opened.status, stage: opened.value.stage},
                        inspected: {status: inspected.status,
                                    stage: inspected.value.stage},
                        filled: {status: filled.status, stage: filled.value.stage,
                                 filled: filled.value.filled,
                                 submitted: filled.value.submitted,
                                 uploaded: filled.value.uploaded},
                        stopped: {status: stopped.status, stage: stopped.value.stage},
                    };
                }""",
                {"port": port, "packet": packet(), "pairCode": PAIR_CODE},
            )
            assert result == {
                "opened": {"status": 200, "stage": "opened"},
                "inspected": {"status": 200, "stage": "inspected"},
                "filled": {"status": 200, "stage": "filled", "filled": 3,
                           "submitted": False, "uploaded": False},
                "stopped": {"status": 200, "stage": "stopped"},
            }
            assert FakeActor.instances[-1].page.filled == [
                ("full", "Applicant Example"),
                ("mail", "person@example.invalid"),
                ("letter", "Synthetic, reviewed, factual cover letter."),
            ]
            assert FakeActor.instances[-1].closed is True
        finally:
            browser.close()
