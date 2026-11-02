"""SP111: applicant-local, explicit-pairing SmartPloy -> ObumAI Playwright bridge.

Reuses assistant.py's original SP110 packet validation, exact ATS URL policy,
field planner and _fill_one runtime. Reuses Python's stdlib HTTPServer; no
new browser engine, backend integration, account store or service dependency.

Run on the applicant's desktop only: python bridge.py
Binds ONLY 127.0.0.1:48741; no GET, cookies, automatic employer submit,
remote browser API, hidden automation, PII logs or background employer actions.
SP112 permits a ONE-USE, explicitly reviewed, exact-SHA CV PDF FileList attachment.
"""
from __future__ import annotations

import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import secrets
import sys
from time import monotonic
from typing import Any, Callable

import assistant

BRIDGE_PORT = 48741
MAX_BODY = 32_000
PAIR_WINDOW_SECONDS = 30 * 60
MAX_BAD_CODES = 5
TRUSTED_ORIGINS = frozenset({
    "https://smartploy.komplyint.fi",
    "https://smartploy.obumai.com",
})
CHALLENGES = (
    "captcha", "verify you are human", "security check", "i am not a robot",
)


class BridgeError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class ChromiumActor:
    """Minimal adapter around ObumAI's adopted, visible Playwright session.

    Playwright sync API is always called from HTTPServer's *one* server thread.
    Each bridge process uses one isolated temporary browser profile.
    """

    def __init__(self, packet: dict[str, Any]):
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
        from tempfile import TemporaryDirectory

        self.profile = TemporaryDirectory(prefix="smartploy-playwright-bridge-")
        self.playwright = None
        self.context = None
        try:
            self.playwright = sync_playwright().start()
            self.context = assistant.start_visible_browser(
                self.playwright, self.profile.name
            )
            page = self.context.pages[0] if self.context.pages else self.context.new_page()
            page.goto(packet["application_url"], wait_until="domcontentloaded",
                      timeout=45000)
        except Exception:
            self.close()
            raise

    def inspect(self, packet: dict[str, Any]) -> tuple[Any, list[dict], list[dict]]:
        assert self.context is not None
        matching = [p for p in self.context.pages
                    if assistant.same_reviewed_form(packet["application_url"], p.url)]
        if len(matching) != 1:
            raise BridgeError(
                "Open exactly one matching supported employer application form "
                "in the visible Playwright browser, then inspect again.", 409
            )
        page = matching[0]
        if any(term in page.locator("body").inner_text(timeout=5000).lower()
               for term in CHALLENGES):
            raise BridgeError(
                "The employer page may contain a security challenge. "
                "Finish it manually; form filling is blocked.", 409
            )
        rows = assistant.inspect_page(page)
        plan = assistant.plan_fields(rows, packet)
        return page, rows, plan

    def fill(self, page: Any, packet: dict[str, Any],
             plan: list[dict], rows: list[dict]) -> dict[str, Any]:
        return assistant.fill_reviewed_page(page, packet, plan, rows)

    def attach(self, page: Any, packet: dict[str, Any], rows: list[dict],
               file_field: dict, raw_pdf: bytes, expected_url: str) -> dict:
        return assistant.attach_reviewed_cv_pdf(
            page, packet, rows, file_field, raw_pdf, expected_url,
        )

    def close(self) -> None:
        try:
            if self.context is not None:
                self.context.close()
        except Exception:
            pass
        try:
            if self.playwright is not None:
                self.playwright.stop()
        except Exception:
            pass
        self.profile.cleanup()


class BridgeState:
    """Single-use, time-limited pairing and single-attempt reviewed form fill."""

    def __init__(self, pairing_code: str | None = None,
                 actor_factory: Callable[[dict[str, Any]], Any] = ChromiumActor):
        self.pairing_code = pairing_code or secrets.token_urlsafe(18)
        self.pair_deadline = monotonic() + PAIR_WINDOW_SECONDS
        self.bad_codes = 0
        self.pairing_used = False
        self.actor_factory = actor_factory
        self.actor: Any | None = None
        self.token = ""
        self.packet: dict[str, Any] | None = None
        self.page: Any | None = None
        self.rows: list[dict] = []
        self.plan: list[dict] = []
        self.plan_id = ""
        self.fill_claimed = False
        self.cv_field: dict[str, Any] | None = None
        self.attach_id = ""
        self.attach_claimed = False
        self.inspected_url = ""

    def prepare(self, pairing_code: Any, raw_packet: Any) -> dict:
        if self.pairing_used or self.actor is not None:
            raise BridgeError("This helper already paired. Stop it before restarting.", 409)
        if self.bad_codes >= MAX_BAD_CODES or monotonic() >= self.pair_deadline:
            raise BridgeError("Pairing expired or locked. Restart the local helper.", 403)
        if (not isinstance(pairing_code, str)
                or not hmac.compare_digest(pairing_code, self.pairing_code)):
            self.bad_codes += 1
            raise BridgeError("Invalid local pairing code.", 403)
        try:
            packet = assistant.validate_packet(raw_packet)
        except assistant.PacketError as exc:
            raise BridgeError(str(exc), 422) from exc
        try:
            actor = self.actor_factory(packet)
        except Exception as exc:
            raise BridgeError(
                "Local Chromium could not start. Check Playwright installation and display.", 503
            ) from exc
        self.actor = actor
        self.packet = packet
        self.token = secrets.token_urlsafe(32)
        self.pairing_used = True
        # Do not retain the code once it has been redeemed.
        self.pairing_code = ""
        return {
            "ok": True,
            "stage": "opened",
            "token": self.token,
            "company": str(packet.get("company") or "")[:150],
            "role_title": str(packet.get("role_title") or "")[:150],
            "submitted": False,
            "uploaded": False,
        }

    def authenticate(self, authorization: Any) -> None:
        if (not self.actor or not self.token
                or not isinstance(authorization, str)
                or not authorization.startswith("Bearer ")
                or not hmac.compare_digest(authorization[7:], self.token)):
            raise BridgeError("Local browser session is not paired.", 403)

    def _current_packet(self) -> dict:
        if self.packet is None:
            raise BridgeError("No reviewed SmartPloy packet.", 409)
        try:
            return assistant.validate_packet(self.packet)
        except assistant.PacketError as exc:
            raise BridgeError(str(exc), 410) from exc

    def inspect(self) -> dict:
        packet = self._current_packet()
        if self.fill_claimed:
            raise BridgeError("This form fill has already been attempted; do not retry.", 409)
        assert self.actor is not None
        self.page = None
        self.rows = []
        self.plan = []
        self.plan_id = ""
        self.cv_field = None
        self.attach_id = ""
        self.inspected_url = ""
        try:
            page, rows, plan = self.actor.inspect(packet)
        except assistant.PacketError as exc:
            raise BridgeError(str(exc), 409) from exc
        except BridgeError:
            raise
        except Exception as exc:
            raise BridgeError(
                "Browser inspection failed. Review the visible form manually.", 409
            ) from exc
        self.page, self.rows, self.plan = page, rows, plan
        self.plan_id = secrets.token_urlsafe(16)
        self.cv_field = assistant.choose_cv_attachment(rows)
        self.attach_id = secrets.token_urlsafe(16) if self.cv_field else ""
        self.inspected_url = page.url
        return {
            "ok": True,
            "stage": "inspected",
            "plan_id": self.plan_id,
            "total_controls": len(rows),
            "cv_attachment": {
                "available": self.cv_field is not None,
                "label": str(self.cv_field.get("label") or "CV")[:100]
                    if self.cv_field else "",
                "attach_id": self.attach_id if self.cv_field else "",
            },
            "approved_fields": [
                {"key": item["key"],
                 "label": str(item["row"].get("label") or item["key"])[:100]}
                for item in plan
            ],
            "submitted": False,
            "uploaded": False,
        }

    def fill(self, plan_id: Any, confirmation: Any) -> dict:
        packet = self._current_packet()
        if self.fill_claimed or self.page is None or not self.plan_id:
            raise BridgeError("Inspect the exact current form. A previous fill cannot be retried.", 409)
        if (not isinstance(plan_id, str)
                or not hmac.compare_digest(plan_id, self.plan_id)
                or confirmation != "FILL REVIEWED FIELDS"):
            raise BridgeError("Fresh reviewed plan and exact approval required.", 403)
        # Burn the attempt *before* any website input. Even uncertain outcomes
        # and client network timeouts cannot cause a second fill.
        self.fill_claimed = True
        try:
            result = self.actor.fill(self.page, packet, self.plan, self.rows)
        except Exception as exc:
            raise BridgeError(
                "Form outcome is uncertain. Inspect the browser manually; never retry.", 409
            ) from exc
        return {
            "ok": True,
            "stage": "filled",
            "filled": result["filled"],
            "planned": result["planned"],
            "stopped_on_change": result["stopped_on_change"],
            "submitted": False,
            "uploaded": False,
        }

    def attach(self, attach_id: Any, approval: Any, raw_pdf: bytes) -> dict:
        packet = self._current_packet()
        if (self.attach_claimed or self.cv_field is None or self.page is None
                or not self.attach_id or not self.inspected_url):
            raise BridgeError("No safe, unattempted reviewed CV attachment. Attach manually.", 409)
        if (not isinstance(attach_id, str)
                or not hmac.compare_digest(attach_id, self.attach_id)
                or approval != "ATTACH REVIEWED CV"):
            raise BridgeError("Fresh CV input plan and exact applicant approval required.", 403)
        try:
            assistant.validate_reviewed_cv_pdf(raw_pdf, packet)
        except assistant.PacketError as exc:
            raise BridgeError(str(exc), 422) from exc
        # IMPORTANT: burn before touching the employer form.
        # Unknown/cancelled network outcomes MUST NOT trigger a blind retry.
        self.attach_claimed = True
        assert self.actor is not None
        try:
            result = self.actor.attach(
                self.page, packet, self.rows, self.cv_field, raw_pdf,
                self.inspected_url,
            )
        except Exception as exc:
            raise BridgeError(
                "CV may have been attached or transferred. Inspect employer browser manually; "
                "do not retry.", 409,
            ) from exc
        if result.get("attached_locally") is not True:
            raise BridgeError(
                "CV attachment was not verified locally. Inspect manually; do not retry.", 409,
            )
        return {
            "ok": True, "stage": "attached", "attached_locally": True,
            "employer_upload_confirmed": False, "submitted": False,
            "uploaded": True,
        }

    def stop(self) -> dict:
        actor = self.actor
        self.actor = None
        self.packet = None
        self.token = ""
        self.page = None
        self.rows, self.plan, self.plan_id = [], [], ""
        self.cv_field, self.attach_id, self.inspected_url = None, "", ""
        self.attach_claimed = True
        self.fill_claimed = True
        if actor is not None:
            try:
                actor.close()
            except Exception:
                pass
        return {
            "ok": True,
            "stage": "stopped",
            "submitted": False,
            "uploaded": False,
        }


def make_handler(state: BridgeState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "SmartPloyLocal/1"
        sys_version = ""

        def setup(self) -> None:
            super().setup()
            # Single-threaded local HTTPServer must not hang on partial reads.
            self.connection.settimeout(10)

        def log_message(self, _format: str, *_args: Any) -> None:
            # NEVER log request paths, headers or private applicant packet.
            pass

        def _origin(self) -> str | None:
            origin = self.headers.get("Origin", "")
            host = self.headers.get("Host", "")
            expected_host = f"127.0.0.1:{self.server.server_address[1]}"
            if host != expected_host or origin not in TRUSTED_ORIGINS:
                return None
            return origin

        def _headers(self, origin: str | None, status: int, length: int,
                     *, preflight: bool = False) -> None:
            self.send_response(status)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Vary", "Origin")
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Private-Network", "true")
            if preflight:
                self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers",
                                 "Content-Type, Authorization, "
                                 "X-Smartploy-Attach-Id, X-Smartploy-Attach-Confirmation")
                self.send_header("Access-Control-Max-Age", "120")
            else:
                self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(length))
            self.end_headers()

        def _reply(self, status: int, data: dict, origin: str | None) -> None:
            payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
            self._headers(origin, status, len(payload))
            self.wfile.write(payload)

        def do_OPTIONS(self) -> None:
            origin = self._origin()
            allowed = (origin is not None and self.path in {
                "/v1/prepare", "/v1/inspect", "/v1/fill", "/v1/attach", "/v1/stop",
            } and self.headers.get("Access-Control-Request-Method") == "POST")
            self._headers(origin if allowed else None,
                          204 if allowed else 403, 0, preflight=allowed)

        def do_GET(self) -> None:
            self._reply(405, {"ok": False, "error": "POST only."}, self._origin())

        def do_POST(self) -> None:
            origin = self._origin()
            if origin is None:
                self._reply(403, {"ok": False, "error": "Untrusted site or host."}, None)
                return
            try:
                if self.path not in {"/v1/prepare", "/v1/inspect", "/v1/fill", "/v1/stop"}:
                    raise BridgeError("Unsupported local action.", 404)
                if self.path == "/v1/attach":
                    state.authenticate(self.headers.get("Authorization"))
                    if self.headers.get("Content-Type", "").strip().lower() != "application/pdf":
                        raise BridgeError("Exact PDF content type required.", 415)
                    try:
                        size = int(self.headers.get("Content-Length", "0"))
                    except ValueError as exc:
                        raise BridgeError("Invalid PDF request length.", 400) from exc
                    if not 12 <= size <= 2 * 1024 * 1024:
                        raise BridgeError("CV PDF request exceeds reviewed size.", 413)
                    if state.packet is None or size != state.packet.get("cv_pdf_size"):
                        raise BridgeError("CV size is not the saved reviewed PDF.", 422)
                    raw = self.rfile.read(size)
                    if len(raw) != size:
                        raise BridgeError("CV transfer incomplete.", 422)
                    result = state.attach(
                        self.headers.get("X-Smartploy-Attach-Id"),
                        self.headers.get("X-Smartploy-Attach-Confirmation"),
                        raw,
                    )
                    self._reply(200, result, origin)
                    return
                if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                    raise BridgeError("JSON requests only.", 415)
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                except ValueError as exc:
                    raise BridgeError("Invalid request length.", 400) from exc
                if not 1 <= size <= MAX_BODY:
                    raise BridgeError("Local request exceeds permitted size.", 413)
                try:
                    body = json.loads(self.rfile.read(size))
                except (ValueError, UnicodeError) as exc:
                    raise BridgeError("Invalid local JSON request.", 400) from exc
                if not isinstance(body, dict):
                    raise BridgeError("JSON object expected.", 400)
                if self.path == "/v1/prepare":
                    if self.headers.get("Authorization"):
                        raise BridgeError("Pairing uses the one-use code, not an existing token.", 403)
                    result = state.prepare(body.get("pairing_code"), body.get("packet"))
                else:
                    state.authenticate(self.headers.get("Authorization"))
                    if self.path == "/v1/inspect":
                        result = state.inspect()
                    elif self.path == "/v1/fill":
                        result = state.fill(body.get("plan_id"), body.get("confirmation"))
                    else:
                        result = state.stop()
                self._reply(200, result, origin)
            except BridgeError as exc:
                self._reply(exc.status, {"ok": False, "error": str(exc)}, origin)
            except Exception:
                self._reply(503, {"ok": False, "error": "Local helper unavailable."}, origin)

    return Handler


def main() -> int:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("Run this helper from your own interactive desktop terminal.")
        return 2
    state = BridgeState()
    try:
        server = HTTPServer(("127.0.0.1", BRIDGE_PORT), make_handler(state))
    except OSError:
        print("Cannot bind 127.0.0.1:48741; another helper may already be running.")
        return 2
    print("SmartPloy local Playwright bridge ready on 127.0.0.1:48741.")
    print("Temporary pairing code (enter it only in SmartPloy):", state.pairing_code)
    print("Pairing expires in 30 minutes or after 5 bad attempts.")
    print("No browser action until SmartPloy asks and you explicitly approve.")
    print("Press Ctrl+C to stop. Browser data is cleared on exit.")
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        state.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
