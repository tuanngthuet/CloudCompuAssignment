"""LABSEAT presentation and controller integration with disposable API fixtures."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

if os.getenv('LABSEAT_BROWSER_UI_TEST') != '1':
    pytest.skip('Set LABSEAT_BROWSER_UI_TEST=1 for browser UI fixtures', allow_module_level=True)
playwright = pytest.importorskip('playwright.sync_api')
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('width,height', [(1440, 900), (1024, 768), (768, 1024), (390, 844)])
def test_booking_tickets_queue_and_admin(width, height):
    now = datetime.now(timezone.utc)
    stamps = {key: (now + delta).isoformat() for key, delta in {
        'open_at': timedelta(hours=-1), 'close_at': timedelta(hours=1),
        'start_at': timedelta(hours=2), 'end_at': timedelta(hours=3),
    }.items()}
    rooms = [{'id': str(i), 'name': name, 'has_image': i == 3} for i, name in enumerate(
        ['Phòng Aurora', 'Phòng Workshop', 'Phòng Hội thảo'], start=1)]
    labs = [dict(id=f's{i}', event_id=f'e{i}', room_id=str(i), **stamps) for i in range(1, 4)]
    seats = [dict(id=f'e{i}', kind='seat', seat_id=f'a{i}', seat_code=f'A{i:02}',
                  x=i - 1, y=2, width=1, height=1, label='') for i in range(1, 9)]
    layout = dict(columns=12, rows=6, revision=1, locked=False, elements=seats)
    state = {'status': None, 'queue': False}
    writes, errors, hold_keys = [], [], []
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.getenv('BROWSER_EXECUTABLE') or None)
        context = browser.new_context(viewport={'width': width, 'height': height})
        page = context.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))

        def respond(route):
            req = route.request
            path = req.url.split('labseat.test', 1)[1].split('?', 1)[0]
            if req.method not in ['GET', 'HEAD']:
                writes.append(path)
            if path == '/':
                return route.fulfill(content_type='text/html', body=(ROOT / 'app/templates/index.html').read_text().replace('{{ version }}', 'UI fixture'))
            if path.startswith('/static/'):
                asset = ROOT / 'app' / path.lstrip('/')
                kind = 'text/css' if path.endswith('.css') else 'image/svg+xml' if path.endswith('.svg') else 'text/javascript'
                return route.fulfill(content_type=kind, body=asset.read_bytes())
            if path.endswith('/image'):
                return route.fulfill(status=404, body='No image')
            if path.endswith('/qr'):
                return route.fulfill(content_type='image/svg+xml', body='<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160"><rect width="160" height="160" fill="white"/><path d="M10 10h40v40H10zM110 10h40v40h-40zM10 110h40v40H10zM70 70h20v20H70zM110 110h40v40h-40z" fill="black"/></svg>')
            if path.endswith('registrations.csv'):
                return route.fulfill(content_type='text/csv', body='reservation_id,username,seat_code,status,checked_in_at\nr1,participant,A01,CONFIRMED,\n')
            if path == '/me':
                data = dict(id='u1', username='organizer', role='admin')
            elif path in ('/events','/admin/events'):
                data = [dict(id=f'e{i}',name=room['name'],session_type='exam',venue=room['name'],address='',description='Programme',poster_url=None) for i,room in enumerate(rooms,1)]
            elif path == '/rooms':
                data = rooms
            elif path == '/lab-sessions':
                data = dict(items=labs, server_time=now.isoformat(), queue_policy=dict(enabled=state['queue']))
            elif path.endswith('/seat-map'):
                data = layout
            elif path == '/me/tickets':
                data = [dict(reservation_id='r1', session_id='s1', seat_id='a1', status=state['status'],
                             event_name='Ca Aurora',seat_code='A01',start_at=stamps['start_at'],ticket_code='LABSEAT-FIXTURE' if state['status'] == 'CONFIRMED' else None,
                             hold_expires_at=(now + timedelta(minutes=3)).isoformat())] if state['status'] else []
            elif path == '/holds':
                hold_keys.append(req.headers.get('idempotency-key'))
                state['status'] = 'HELD'
                if len(hold_keys)==1:
                    # Server committed; response was lost. Availability must recover it.
                    return route.abort('failed')
                data = dict(hold_id='r1', server_time=now.isoformat(), expires_at=(now + timedelta(minutes=3)).isoformat())
            elif path.endswith('/confirm'):
                state['status'] = 'CONFIRMED'
                data = dict(status='CONFIRMED')
            elif path.endswith('/cancel'):
                state['status'] = 'CANCELLED'
                data = dict(status='CANCELLED')
            elif '/queue/' in path:
                data = dict(session_id='s2', status='WAITING', number_ahead=7,
                            server_time=datetime.now(timezone.utc).isoformat(), heartbeat_after_seconds=60)
            elif path.endswith('/seats'):
                data = dict(server_time=now.isoformat(), items=[dict(id=f'a{i}', seat_code=f'A{i:02}', available=True) for i in range(1, 9)])
            elif path=='/admin/users':data={'items':[],'total':0}
            elif path in ('/admin/privacy-review','/admin/emails'):data=[]
            else:
                data = {}
            return route.fulfill(content_type='application/json', body=json.dumps(data))

        context.route('http://labseat.test/**', respond)

        def check_screen(name):
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), name
            assert 'LABSEAT' in page.title()
            folder = os.getenv('LABSEAT_UI_SCREENSHOTS')
            if folder:
                Path(folder).mkdir(parents=True, exist_ok=True)
                page.locator('[data-enter]').evaluate("async el => { await Promise.all(el.getAnimations().map(a => a.finished)); }")
                page.screenshot(path=str(Path(folder) / f'labseat-{name}-{width}.png'), full_page=True)

        try:
            page.goto('http://labseat.test/')
            playwright.expect(page.locator('#session-grid .event-card')).to_have_count(3)
            playwright.expect(page.locator('#booking-map')).to_be_hidden()
            assert page.locator('#room-filter, #date-filter, #status-filter, #rooms').count() == 0
            check_screen('catalogue')
            page.get_by_role('button', name='Xem Ca thi · Phòng Aurora', exact=True).first.click()
            page.locator('#event-session-list button').click()
            page.locator('#seats button').first.click()
            playwright.expect(page.locator('#seat-summary')).to_contain_text('A01')
            check_screen('seats')
            page.locator('#hold-selected').click()
            page.wait_for_function('holdBusy===false')
            page.evaluate('availability()')
            playwright.expect(page.locator('#hold-panel')).to_be_visible()
            page.locator('#confirm').click()
            playwright.expect(page.locator('#hold-panel')).to_be_hidden()
            page.locator('#tickets-link').click()
            playwright.expect(page.locator('#tickets [data-status=CONFIRMED]')).to_be_visible()
            playwright.expect(page.get_by_alt_text('QR đăng kí')).to_be_visible()
            playwright.expect(page.locator('#tickets .ticket-name')).to_have_text('Ca Aurora')
            playwright.expect(page.locator('#tickets')).not_to_contain_text('LABSEAT-FIXTURE')
            check_screen('tickets')
            page.locator('#tickets').get_by_role('button', name='Hủy', exact=True).click()
            playwright.expect(page.locator('#tickets [data-status=CANCELLED]')).to_be_visible()
            page.evaluate("api('/holds','POST',{session_id:'s1',seat_id:'a1'})")
            assert len(hold_keys)==2 and all(hold_keys) and hold_keys[0]!=hold_keys[1], 'New intent after recovered/cancelled hold needs a new key'
            page.locator('#admin-link').click()
            playwright.expect(page.locator('#event-form')).to_be_visible()
            page.locator('.admin-nav').get_by_role('link',name='Sơ đồ phòng',exact=True).click()
            page.locator('#editor-event').select_option('e1')
            page.locator('#image-map-load').click()
            playwright.expect(page.locator('#image-editor-board button').first).to_be_visible()
            check_screen('editor')
            page.locator('.admin-nav').get_by_role('link', name='Quản lý ca', exact=True).click()
            page.locator('#event-form input[name=name]').fill('Bản nháp LABSEAT')
            before = len(writes)
            for label, target in [('Sơ đồ phòng','layout-editor'),('Checkin','checkin-form'),('Danh sách đăng kí','registrations-panel'),('Quản lý ca','event-form')]:
                page.locator('.admin-nav').get_by_role('link', name=label, exact=True).click()
                playwright.expect(page.locator('#' + target)).to_be_visible()
                assert page.locator('[data-admin-view]:visible').count() == 1
                check_screen(target)
            assert len(writes) == before
            assert page.locator('#event-form input[name=name]').input_value() == 'Bản nháp LABSEAT'
            page.locator('.admin-nav').get_by_role('link', name='Danh sách đăng kí', exact=True).click()
            page.locator('#registration-session').select_option('s1')
            playwright.expect(page.locator('#registration-table')).to_contain_text('Người đăng kí')
            check_screen('registrations')
            state['queue'] = True
            page.goto('http://labseat.test/')
            page.get_by_role('button', name='Xem Ca thi · Phòng Workshop', exact=True).first.click()
            page.locator('#event-session-list button').click()
            playwright.expect(page.locator('#queue-position')).to_have_text('7')
            playwright.expect(page.locator('#booking-map')).to_be_hidden()
            check_screen('queue')
            page.locator('#leave-queue').click()
            playwright.expect(page.locator('#booking-catalogue')).to_be_visible()
            page.emulate_media(reduced_motion='reduce')
            assert page.locator('[data-enter]').evaluate('el => getComputedStyle(el).animationName') == 'none'
            assert not errors
        finally:
            context.close()
            browser.close()
