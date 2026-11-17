"""Opt-in real-browser presentation tests with explicit API fixtures; no DB/AWS."""
import json
import os
from pathlib import Path

import pytest

if os.getenv('LABSEAT_BROWSER_UI_TEST') != '1':
    pytest.skip('Set LABSEAT_BROWSER_UI_TEST=1 for browser UI fixtures', allow_module_level=True)
playwright = pytest.importorskip('playwright.sync_api')
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('width,height', [(1440, 1000), (1024, 768), (390, 844)])
def test_guest_dashboard_and_login_modal(width, height):
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.getenv('BROWSER_EXECUTABLE') or None)
        context = browser.new_context(viewport={'width': width, 'height': height})
        page = context.new_page()
        errors = []
        writes = []
        state = {'authenticated': False}
        page.on('pageerror', lambda error: errors.append(str(error)))

        def respond(route):
            request = route.request
            path = request.url.split('labseat.test', 1)[1].split('?', 1)[0]
            if request.method == 'POST':
                writes.append(path)
            if path == '/':
                return route.fulfill(content_type='text/html', body=(ROOT / 'app/templates/index.html').read_text().replace('{{ version }}', 'UI fixture'))
            if path.startswith('/static/'):
                asset = ROOT / 'app' / path.lstrip('/')
                return route.fulfill(content_type='text/css' if path.endswith('.css') else 'text/javascript', body=asset.read_text())
            status = 200
            if path == '/me':
                status = 200 if state['authenticated'] else 401
                result = {'username': 'student', 'role': 'student'} if state['authenticated'] else {'code': 'unauthenticated', 'message': 'Chưa đăng nhập', 'request_id': 'fixture'}
            elif path == '/auth/login':
                state['authenticated'] = json.loads(request.post_data)['password'] == 'correct-password'
                status = 200 if state['authenticated'] else 401
                result = {} if state['authenticated'] else {'code': 'invalid_login', 'message': 'Tài khoản hoặc mật khẩu không đúng', 'request_id': 'fixture'}
            elif path == '/lab-sessions':
                result = {'items': []}
            else:
                result = []
            return route.fulfill(status=status, content_type='application/json', body=json.dumps(result))

        context.route('http://labseat.test/**', respond)
        try:
            page.goto('http://labseat.test/')
            dialog = page.get_by_role('dialog', name='Chào mừng bạn trở lại')
            playwright.expect(page.locator('#booking')).to_be_visible()
            playwright.expect(page.locator('#login-panel')).to_be_hidden()
            page.locator('#event-search').fill('Ca đang tìm')
            page.locator('#login-link').click()
            playwright.expect(dialog).to_be_visible()
            playwright.expect(page.locator('#booking')).to_be_visible()
            assert page.evaluate('document.querySelector("#login-panel").matches(":modal")')
            assert page.evaluate('getComputedStyle(document.documentElement).overflow') == 'hidden'
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            playwright.expect(page.get_by_label('Tài khoản', exact=True)).to_be_focused()
            screenshot_dir = os.getenv('LABSEAT_UI_SCREENSHOTS')
            if screenshot_dir:
                Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(Path(screenshot_dir) / f'login-modal-{width}.png'))
            for _ in range(8):
                page.keyboard.press('Tab')
                assert page.evaluate('document.activeElement === document.querySelector("#login-panel") || document.querySelector("#login-panel").contains(document.activeElement)')
            page.keyboard.press('Escape')
            playwright.expect(dialog).to_be_hidden()
            playwright.expect(page.locator('#login-link')).to_be_focused()
            assert page.locator('#event-search').input_value() == 'Ca đang tìm'
            for close_method in ['button', 'backdrop', 'browse']:
                page.locator('#login-link').click()
                playwright.expect(dialog).to_be_visible()
                if close_method == 'button':
                    page.get_by_role('button', name='Đóng đăng nhập').click()
                elif close_method == 'backdrop':
                    page.mouse.click(4, 4)
                else:
                    page.locator('#browse-without-login').click()
                playwright.expect(dialog).to_be_hidden()
            assert writes == [], 'Opening and closing the popup must never submit login'
            page.locator('#login-link').click()
            page.get_by_label('Tài khoản', exact=True).fill('student')
            page.get_by_label('Mật khẩu', exact=True).fill('wrong-password')
            dialog.get_by_role('button', name='Đăng nhập', exact=True).click()
            playwright.expect(page.locator('#login-message')).to_contain_text('Tài khoản hoặc mật khẩu không đúng')
            playwright.expect(dialog).to_be_visible()
            screenshot_dir = os.getenv('LABSEAT_UI_SCREENSHOTS')
            if screenshot_dir:
                Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(Path(screenshot_dir) / f'login-error-{width}.png'))
            page.get_by_label('Mật khẩu', exact=True).fill('correct-password')
            dialog.get_by_role('button', name='Đăng nhập', exact=True).click()
            playwright.expect(dialog).to_be_hidden()
            playwright.expect(page.locator('#booking')).to_be_visible()
            playwright.expect(page.locator('#login-link')).to_be_hidden()
            assert page.evaluate('getComputedStyle(document.documentElement).overflow') != 'hidden'
            assert not errors
        finally:
            context.close()
            browser.close()
