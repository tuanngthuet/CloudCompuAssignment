"""Real HTTP signup with PostgreSQL; only run against an explicit disposable server."""
import os
import uuid
from pathlib import Path
import pytest

BASE = os.getenv('BROWSER_BASE_URL', '').rstrip('/')
if not BASE:
    pytest.skip('Set BROWSER_BASE_URL for live signup tests', allow_module_level=True)
if os.getenv('BROWSER_TEST_ALLOWED') != 'local-demo-only':
    raise RuntimeError('Explicit disposable server authorization required')
pw = pytest.importorskip('playwright.sync_api')


@pytest.mark.parametrize('width,height', [(1440,900), (1024,768), (768,1024), (390,844), (320,740)])
def test_registration_real_http_password_errors_session_and_login(width, height):
    username = 'new-user-' + uuid.uuid4().hex[:12]
    password = 'browser-signup-password'
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.getenv('BROWSER_EXECUTABLE') or None)
        context = browser.new_context(viewport={'width':width, 'height':height})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        try:
            page.goto(BASE + '/')
            page.locator('#login-link').click()
            page.locator('#show-register').click()
            form = page.locator('#register')
            pw.expect(page.get_by_role('dialog', name='Tạo tài khoản')).to_be_visible()
            pw.expect(form.locator('[name=username]')).to_be_focused()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            for _ in range(12):
                page.keyboard.press('Tab')
                assert page.evaluate('document.querySelector("#login-panel").contains(document.activeElement)')
                assert page.evaluate('document.activeElement.getClientRects().length > 0')
            page.keyboard.press('Escape')
            pw.expect(page.locator('#login-panel')).to_be_hidden()
            pw.expect(page.locator('#login-link')).to_be_focused()
            page.locator('#login-link').click()
            pw.expect(page.locator('#login')).to_be_visible()
            page.locator('#show-register').click()
            form.locator('[name=username]').fill(username)
            form.locator('[name=password]').fill(password)
            form.locator('[name=password_confirm]').fill(password + 'mismatch')
            page.locator('#register-submit').click()
            pw.expect(page.locator('#login-message')).to_have_text('Mật khẩu chưa khớp.')
            assert form.locator('[name=username]').input_value() == username
            form.locator('[name=password_confirm]').fill(password)
            shot_dir = os.getenv('LABSEAT_UI_SCREENSHOTS')
            if shot_dir:
                Path(shot_dir).mkdir(parents=True, exist_ok=True)
                page.locator('#show-login').click()
                page.locator('#show-register').click()
                page.screenshot(path=str(Path(shot_dir) / f'register-{width}.png'))
            page.locator('#register-submit').click()
            pw.expect(page.locator('#login-panel')).to_be_hidden()
            pw.expect(page.locator('#identity')).to_have_text(username)
            pw.expect(page.locator('#tickets-link')).to_be_visible()
            pw.expect(page.locator('#admin-link')).to_be_hidden()
            assert context.request.get(BASE + '/me').json()['username'] == username
            assert form.locator('[name=password]').input_value() == ''
            page.locator('#tickets-link').click()
            pw.expect(page.locator('#tickets-panel')).to_be_visible()
            page.locator('#account-toggle').click();page.locator('#logout').click()
            pw.expect(page.locator('#login-link')).to_be_visible()
            assert context.request.get(BASE + '/me').status == 401
            if not page.locator('#login-panel').is_visible():
                page.locator('#login-link').click()
            page.locator('#show-register').click()
            form.locator('[name=username]').fill(username)
            form.locator('[name=password]').fill(password)
            form.locator('[name=password_confirm]').fill(password)
            page.locator('#register-submit').click()
            pw.expect(page.locator('#login-message')).to_have_text('Tên tài khoản đã tồn tại.')
            pw.expect(page.locator('#register-submit')).to_be_enabled()
            page.locator('#show-login').click()
            page.get_by_label('Tài khoản', exact=True).fill(username)
            page.get_by_label('Mật khẩu', exact=True).fill(password)
            page.locator('#login button').click()
            pw.expect(page.locator('#login-panel')).to_be_hidden()
            pw.expect(page.locator('#identity')).to_have_text(username)
            page.reload()
            pw.expect(page.locator('#identity')).to_have_text(username)
            assert not errors
        finally:
            context.close()
            browser.close()
