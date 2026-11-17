"""Opt-in UI E2E against disposable HTTP app + PostgreSQL/Redis (not API mocks)."""
import os
import time
import uuid
from datetime import datetime,timedelta,timezone
import pytest

BASE=os.getenv('BROWSER_BASE_URL')
if not BASE or os.getenv('BROWSER_QUEUE_TEST_ALLOWED')!='local-demo-only':
    pytest.skip('Disposable browser queue stack required',allow_module_level=True)
if os.getenv('APP_ENV')!='test' or not os.getenv('DATABASE_URL','').rsplit('/',1)[-1].endswith('_test'):
    raise RuntimeError('Queue browser fixtures may only change an isolated *_test DB')
playwright=pytest.importorskip('playwright.sync_api')


def test_real_waiting_room_auto_admit_reload_expire_and_leave():
    import httpx
    from pathlib import Path
    from app.queue_admin import change
    from app.infrastructure.database.session import Session
    from app.models import QueueSettings
    password=os.environ['BROWSER_TEST_PASSWORD']
    with httpx.Client(base_url=BASE) as admin:
        admin.get('/')
        assert admin.post('/auth/login',json={'username':'admin','password':password},headers={'X-CSRF-Token':admin.cookies['labseat_pre_csrf']}).status_code==200
        admin.headers['X-CSRF-Token']=admin.cookies['labseat_csrf']
        import json
        from io import BytesIO
        from PIL import Image
        clock=datetime.now(timezone.utc);event_name='Queue event '+uuid.uuid4().hex[:8]
        image=BytesIO();Image.new('RGB',(1280,720),'blue').save(image,'PNG')
        payload={'name':event_name,'session_type':'practice','venue':'Queue test',
                 'schedule':{k:(clock+timedelta(minutes=m)).isoformat() for k,m in [('open_at',-60),('close_at',10),('start_at',20),('end_at',60)]}}
        event=admin.post('/admin/events',data={'data':json.dumps(payload)},files={'poster':('ca.png',image.getvalue(),'image/png')})
        assert event.status_code==201,event.text
        schedule=event.json()['schedule'];lab=schedule['id']
        for code in ('Q1','Q2','Q3'):
            assert admin.post('/admin/rooms/'+schedule['room_id']+'/seats',json={'seat_code':code}).status_code==201
    # Short TEST policy makes expiry observable; production defaults remain 10/120/5/60.
    change('enable','browser-test','isolated accelerated UI fixture',capacity=1,selection_seconds=8,heartbeat_seconds=1,waiting_grace_seconds=5)
    with playwright.sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.getenv('BROWSER_EXECUTABLE') or None)
        contexts=[];pages=[];errors=[];joins=[]
        try:
            for username in ['student002','student003','student004']:
                context=browser.new_context(viewport={'width':1440,'height':1000});contexts.append(context)
                page=context.new_page();pages.append(page)
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.on('request',lambda request:joins.append(request.url) if request.method=='POST' and request.url.endswith('/queue/join') else None)
                # Second student begins as a guest: selecting a session must open login.
                page.goto(BASE+'/'+('' if username=='student003' else '#login-panel'))
                if username=='student003':continue
                page.get_by_label('Tài khoản',exact=True).fill(username);page.get_by_label('Mật khẩu',exact=True).fill(password)
                page.get_by_role('button',name='Đăng nhập',exact=True).click()
                playwright.expect(page.locator('#login-panel')).to_be_hidden()
            def choose_event(page):
                page.locator('#session-types [data-type=practice]').click()
                page.get_by_role('button',name='Xem Ca thực hành · '+event_name,exact=True).click()
                page.locator('#event-session-list button').click()
            first,second,third=pages
            choose_event(first)
            playwright.expect(first.locator('#seats button:not([disabled])').first).to_be_visible()
            playwright.expect(first.locator('#admission-banner')).to_be_visible()
            choose_event(second)
            playwright.expect(second.locator('#login-panel')).to_be_visible()
            second.get_by_label('Tài khoản',exact=True).fill('student003');second.get_by_label('Mật khẩu',exact=True).fill(password)
            second.get_by_role('button',name='Đăng nhập',exact=True).click()
            playwright.expect(second.locator('#login-panel')).to_be_hidden()
            playwright.expect(second.locator('#queue-position')).to_have_text('0')
            playwright.expect(second.locator('#booking-map')).to_be_hidden()
            playwright.expect(second.locator('#booking-catalogue')).to_be_hidden()
            assert second.locator('#seats button').count()==0
            assert len(joins)==2,'Selecting a session should join automatically once'
            screenshot_dir=os.getenv('BROWSER_QUEUE_SCREENSHOTS')
            for width,height in [(1440,1000),(1024,1000),(390,844)]:
                second.set_viewport_size({'width':width,'height':height})
                assert second.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
                if screenshot_dir:
                    Path(screenshot_dir).mkdir(parents=True,exist_ok=True)
                    second.locator('#queue-panel').screenshot(path=str(Path(screenshot_dir)/f'waiting-{width}.png'))
            first.locator('#seats button:not([disabled])').first.click();first.locator('#hold-selected').click()
            playwright.expect(first.locator('#hold-panel')).to_be_visible()
            playwright.expect(second.locator('#seats button:not([disabled])').first).to_be_visible(timeout=10000)
            deadline=second.evaluate('queueState.admission_expires_at')
            second.reload();playwright.expect(second.locator('#seats button:not([disabled])').first).to_be_visible()
            assert second.evaluate('queueState.admission_expires_at')==deadline
            assert len(joins)==2,'Reload must restore without joining or renewing'
            # Another tab sees the same lease, without a second join or deadline extension.
            tab=contexts[1].new_page();tab.on('request',lambda request:joins.append(request.url) if request.method=='POST' and request.url.endswith('/queue/join') else None);tab.goto(second.url)
            playwright.expect(tab.locator('#admission-banner')).to_be_visible()
            assert tab.evaluate('queueState.admission_expires_at')==deadline
            assert len(joins)==2
            tab.close()
            choose_event(third)
            playwright.expect(third.locator('#queue-position')).to_have_text('0')
            first.locator('#confirm').click()
            playwright.expect(first.locator('#notice')).to_contain_text('Đã đăng kí')
            playwright.expect(third.locator('#seats button:not([disabled])').first).to_be_visible(timeout=15000)
            playwright.expect(second.locator('#queue-position')).to_have_text('0',timeout=10000)
            assert len(joins)==4,'The expired second lease should rejoin at the back automatically'
            assert second.locator('#hold-selected').is_disabled()
            third.locator('#leave-admission').click()
            playwright.expect(third.locator('#booking-catalogue')).to_be_visible()
            assert third.locator('#session').input_value()==''
            playwright.expect(second.locator('#admission-banner')).to_be_visible(timeout=10000)
            second.locator('#leave-admission').click()
            playwright.expect(second.locator('#booking-catalogue')).to_be_visible()
            assert second.locator('#session').input_value()==''
            # Navigation away cancels participation, and Back to booking does not join again.
            choose_event(third)
            playwright.expect(third.locator('#admission-banner')).to_be_visible()
            third.get_by_role('link',name='Ca đã đăng kí',exact=True).click()
            playwright.expect(third.locator('#tickets-panel')).to_be_visible()
            third.get_by_role('link',name='Danh sách ca',exact=True).click()
            playwright.expect(third.locator('#booking-catalogue')).to_be_visible()
            assert third.locator('#session').input_value()==''
            assert len(joins)==5
            assert not errors
        finally:
            for context in contexts:context.close()
            browser.close()
            change('begin','browser-test','cleanup accelerated fixture')
            while True:
                with Session() as db:
                    until=db.get(QueueSettings,1).recovery_not_before
                if datetime.now(timezone.utc)>=until:break
                time.sleep(.1)
            change('disable','browser-test','fixture drained and contexts closed')
