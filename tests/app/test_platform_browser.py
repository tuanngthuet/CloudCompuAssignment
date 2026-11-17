"""Real Chrome interaction with source assets and disposable HTTP fixtures."""

import json, os
from pathlib import Path
from datetime import datetime, timedelta, timezone
import pytest

if os.getenv("LABSEAT_BROWSER_UI_TEST") != "1":
    pytest.skip("Browser fixture opt-in required", allow_module_level=True)
pw = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("width", [390, 1440])
@pytest.mark.parametrize("role", ["admin", "staff", "guest"])
def test_security_management_and_staff_views(width, role):
    clock = datetime.now(timezone.utc)
    lab = dict(
        id="session-1",
        event_id="event-1",
        room_id="room-1",
        name="Ca kiểm thử",
        checkin_enabled=True,
        checkin_close_mode="end_at",
        **{
            k: (clock + timedelta(minutes=m)).isoformat()
            for k, m in [
                ("open_at", -60),
                ("close_at", 30),
                ("start_at", 60),
                ("end_at", 90),
            ]
        },
    )
    writes = []
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.getenv("BROWSER_EXECUTABLE") or None
        )
        context = browser.new_context(viewport={"width": width, "height": 900})
        page = context.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))

        def route(r):
            path = r.request.url.split("labseat.test", 1)[1].split("?", 1)[0]
            if path == "/":
                return r.fulfill(
                    content_type="text/html",
                    body=(ROOT / "app/templates/index.html")
                    .read_text()
                    .replace("{{ version }}", "fixture"),
                )
            if path.startswith("/static/"):
                asset = ROOT / "app" / path.lstrip("/")
                return r.fulfill(
                    content_type="text/css"
                    if path.endswith(".css")
                    else "image/svg+xml"
                    if path.endswith(".svg")
                    else "text/javascript",
                    body=asset.read_bytes(),
                )
            if r.request.method != "GET":
                writes.append((path, r.request.post_data_json))
            code = 200
            if path == "/me":
                data = dict(
                    id="u1",
                    username="fixture",
                    role=role,
                    email_verified=True,
                    profile_complete=True,
                )
                if role == "guest":
                    code = 401
            elif path in ("/events", "/admin/events"):
                data = [
                    dict(
                        id="event-1",
                        name="Ca kiểm thử",
                        status="ACTIVE",
                        session_type="practice",
                        venue="LAB",
                        description="",
                        address="",
                        poster_url="/static/labseat.svg",
                        schedule=lab,
                    )
                ]
            elif path == "/rooms":
                data = [dict(id="room-1", name="LAB")]
            elif path == "/lab-sessions":
                data = {
                    "items": [lab],
                    "server_time": clock.isoformat(),
                    "queue_policy": {"enabled": False},
                }
            elif path == "/admin/users":
                data = {
                    "total": 1,
                    "items": [
                        dict(
                            id="u2",
                            username="student",
                            full_name="Sinh viên",
                            email="student@example.test",
                            email_verified=True,
                            role="student",
                            status="ACTIVE",
                        )
                    ],
                }
            elif path == "/staff/lab-sessions":
                data = {"items": [lab]}
            elif path == "/staff/check-ins/lookup":
                data = {
                    "ticket": {
                        "reservation_id": "r1",
                        "ticket_code": "fixture-ticket-1234567890",
                        "status": "CONFIRMED",
                    },
                    "session": lab | {"room_name": "LAB", "seat_code": "A01"},
                    "profile": {
                        "username": "student",
                        "full_name": "Sinh viên",
                        "cccd": "••••••••8901",
                        "email": "",
                        "phone": "",
                        "avatar_url": None,
                    },
                    "can_check_in": True,
                    "reason": "Vé hợp lệ.",
                }
            elif path == "/auth/password-reset/request":
                data = {
                    "status": "queued",
                    "message": "Nếu tài khoản hợp lệ, hướng dẫn khôi phục sẽ được gửi.",
                }
            elif path == "/auth/email-verification/confirm":
                data = {"status": "verified"}
            else:
                data = []
            return r.fulfill(
                status=code, content_type="application/json", body=json.dumps(data)
            )

        context.route("http://labseat.test/**", route)
        try:
            page.goto("http://labseat.test/")
            if role == "admin":
                page.goto("http://labseat.test/#users-panel")
                pw.expect(page.locator("#users-table")).to_contain_text(
                    "student@example.test"
                )
                page.on("dialog", lambda d: d.accept("Fixture role update"))
                page.locator("#users-table select").first.select_option("staff")
                page.get_by_role("button", name="Lưu quyền và trạng thái").click()
                page.wait_for_function(
                    'document.querySelector("#users-status").textContent.includes("1 tài khoản")'
                )
                assert any(
                    path == "/admin/users/u2" and body["role"] == "staff"
                    for path, body in writes
                )
            elif role == "staff":
                page.get_by_role("link", name="Ca được giao", exact=True).click()
                pw.expect(page.locator("#checkin-form")).to_be_visible()
                page.locator("#staff-session").select_option("session-1")
                page.locator("#checkin-form input[name=ticket_code]").fill(
                    "fixture-ticket-1234567890"
                )
                page.get_by_role("button", name="Tra cứu vé", exact=True).click()
                pw.expect(page.locator("#checkin-result")).to_be_visible()
                pw.expect(page.locator("#checkin-confirm")).to_be_visible()
                pw.expect(page.locator("#staff-reveal-identity")).to_be_visible()
                assert not any(path == "/staff/check-ins" for path, _ in writes)
            else:
                page.locator("#login-link").click()
                page.get_by_text("Quên mật khẩu", exact=True).click()
                page.locator("#forgot-password input").fill("absent@example.test")
                page.get_by_role("button", name="Gửi hướng dẫn khôi phục").click()
                pw.expect(
                    page.locator("#forgot-password [role=status]")
                ).to_contain_text("Nếu tài khoản hợp lệ")
                page.goto(
                    "http://labseat.test/#auth-action?purpose=verify&id=fixture-id&token="
                    + "a" * 64
                )
                pw.expect(page.locator("#auth-action")).to_be_visible()
                assert "token=" not in page.url
                assert not any(
                    path == "/auth/email-verification/confirm" for path, _ in writes
                )
                page.locator("#auth-action-submit").click()
                pw.expect(
                    page.locator("#auth-action-form [role=status]")
                ).to_contain_text("Email đã xác minh")
            folder = os.getenv("LABSEAT_UI_SCREENSHOTS")
            if folder:
                Path(folder).mkdir(parents=True, exist_ok=True)
                page.screenshot(
                    path=str(Path(folder) / f"platform-{role}-{width}.png"),
                    full_page=True,
                )
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            assert not errors, errors
        finally:
            context.close()
            browser.close()
