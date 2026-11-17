"""Opt-in browser smoke against an isolated, freshly seeded local app."""
import os
import pytest

BASE=os.getenv('BROWSER_BASE_URL')
if not BASE:
    pytest.skip('BROWSER_BASE_URL and isolated local seed required',allow_module_level=True)
if os.getenv('BROWSER_TEST_ALLOWED')!='local-demo-only':
    raise RuntimeError('Set BROWSER_TEST_ALLOWED=local-demo-only for an isolated demo')
playwright=pytest.importorskip('playwright.sync_api')

def test_student_ticket_and_admin_manual_checkin():
    password=os.environ['BROWSER_TEST_PASSWORD']
    with playwright.sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.getenv('BROWSER_EXECUTABLE') or None)
        student=browser.new_context();admin=browser.new_context()
        try:
            page=student.new_page();operator=admin.new_page()
            for tab,name in [(page,os.getenv('BROWSER_STUDENT','student001')),(operator,'admin')]:
                tab.goto(BASE+'/#login-panel')
                tab.get_by_label('Tài khoản',exact=True).fill(name)
                tab.get_by_label('Mật khẩu',exact=True).fill(password)
                tab.get_by_role('button',name='Đăng nhập',exact=True).click()
                playwright.expect(tab.locator('#login-panel')).to_be_hidden()
            # Each test owns a valid current ca; never depend on stale demo schedule/order.
            from datetime import datetime,timedelta,timezone
            from io import BytesIO
            import json,uuid
            from PIL import Image
            now=datetime.now(timezone.utc);image=BytesIO();Image.new('RGB',(1280,720),'blue').save(image,'PNG')
            csrf=next(c['value'] for c in admin.cookies() if c['name']=='labseat_csrf');headers={'X-CSRF-Token':csrf}
            payload={'name':'Checkin '+uuid.uuid4().hex[:8],'session_type':'practice','venue':'Test',
                     'schedule':{k:(now+timedelta(minutes=m)).isoformat() for k,m in [('open_at',-60),('close_at',9),('start_at',10),('end_at',60)]}}
            event=admin.request.post(BASE+'/admin/events',multipart={'data':json.dumps(payload),'poster':{'name':'test.png','mimeType':'image/png','buffer':image.getvalue()}},headers=headers)
            assert event.status==201,event.text()
            schedule=event.json()['schedule'];session_id=schedule['id']
            assert admin.request.post(BASE+'/admin/rooms/'+schedule['room_id']+'/seats',data={'seat_code':'CHECKIN'},headers=headers).status==201
            page.goto(BASE+'/?session='+session_id+'#booking')
            page.locator('#seats button:not([disabled])').first.click()
            page.locator('#hold-selected').click()
            playwright.expect(page.locator('#hold-panel')).to_be_visible()
            page.locator('#confirm').click()
            page.get_by_role('link',name='Ca đã đăng kí',exact=True).click()
            playwright.expect(page.locator('#tickets [data-status=CONFIRMED]').first).to_be_visible()
            card=page.locator('#tickets .card').filter(has=page.locator('[data-status=CONFIRMED]')).first
            code=next(t['ticket_code'] for t in page.request.get(BASE+'/me/tickets').json() if t['status']=='CONFIRMED' and t['session_id']==session_id)
            playwright.expect(card.get_by_alt_text('QR đăng kí')).to_be_visible()
            operator.locator('.admin-nav').get_by_role('link',name='Checkin',exact=True).click()
            operator.locator('#checkin-form input[name=ticket_code]').fill(code)
            operator.evaluate("id=>api(`/admin/lab-sessions/${id}/check-in`,'PATCH',{enabled:true})",session_id)
            operator.locator('#checkin-form').get_by_role('button',name='Tra cứu vé',exact=True).click()
            playwright.expect(operator.locator('#checkin-confirm')).to_be_visible()
            operator.locator('#checkin-confirm').click()
            playwright.expect(operator.locator('#notice')).to_contain_text('Đã xác nhận check-in.')
            page.reload()
            playwright.expect(page.locator('#tickets [data-status=CHECKED_IN]').first).to_be_visible()
        finally:
            student.close();admin.close();browser.close()

@pytest.mark.parametrize('viewport', [dict(width=1440,height=1000),dict(width=1024,height=768),dict(width=390,height=844)])
def test_screen_navigation_preserves_drafts_without_writing(viewport):
    """Navigation is read-only; role guards, narrow layouts and drafts remain usable."""
    with playwright.sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.getenv('BROWSER_EXECUTABLE') or None)
        context=browser.new_context(viewport=viewport)
        page=context.new_page();errors=[];writes=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('request',lambda request:writes.append(request.url) if request.method not in ['GET','HEAD','OPTIONS'] else None)
        try:
            page.goto(BASE+'/#registrations-panel')
            playwright.expect(page.locator('#login-panel')).to_be_visible()
            page.get_by_label('Tài khoản',exact=True).fill('admin')
            page.get_by_label('Mật khẩu',exact=True).fill(os.environ['BROWSER_TEST_PASSWORD'])
            page.get_by_role('button',name='Đăng nhập',exact=True).click()
            playwright.expect(page.locator('#registrations-panel')).to_be_visible()
            page.locator('.admin-nav').get_by_role('link',name='Quản lý ca',exact=True).click()
            page.locator('#event-form input[name=name]').fill('Bản nháp chưa lưu')
            count=len(writes)
            for label,target in [('Sơ đồ phòng','layout-editor'),('Checkin','checkin-form'),('Danh sách đăng kí','registrations-panel'),('Quản lý ca','event-form')]:
                page.locator('.admin-nav').get_by_role('link',name=label,exact=True).click()
                playwright.expect(page.locator('#'+target)).to_be_visible()
                assert page.locator('[data-admin-view]:visible').count()==1
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),label
            assert page.locator('#event-form input[name=name]').input_value()=='Bản nháp chưa lưu'
            assert len(writes)==count,'Navigation must not submit forms'
            page.locator('.admin-nav').get_by_role('link',name='Danh sách đăng kí',exact=True).click()
            page.locator('#registration-session').select_option(index=1)
            playwright.expect(page.locator('#registration-stats')).to_contain_text('đăng kí')
            playwright.expect(page.locator('#registration-table table')).to_be_visible()
            with page.expect_download() as download:
                page.locator('#csv').click()
            assert download.value.suggested_filename=='registrations.csv'

            page.locator('#account-toggle').click()
            page.get_by_role('button',name='Đăng xuất',exact=True).click()
            playwright.expect(page.locator('#login-link')).to_be_visible()
            playwright.expect(page.locator('#admin-panel')).to_be_hidden()
            assert not errors
        finally:
            context.close();browser.close()
