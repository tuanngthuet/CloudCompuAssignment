"""Live HTTP profiles: private edit, exam prerequisite and resume without reselecting."""
import os,json,uuid
from pathlib import Path
from io import BytesIO
from datetime import datetime,timedelta,timezone
import pytest
BASE=os.getenv('BROWSER_BASE_URL','').rstrip('/')
if not BASE:pytest.skip('Live disposable server required',allow_module_level=True)
if os.getenv('BROWSER_TEST_ALLOWED')!='local-demo-only':raise RuntimeError('Disposable server only')
pw=pytest.importorskip('playwright.sync_api')

@pytest.mark.parametrize('width,height',[(1440,900),(1024,768),(768,1024),(390,844),(320,740)])
def test_profile_exam_gate_resume_and_persistence(width,height):
    from PIL import Image
    with pw.sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.getenv('BROWSER_EXECUTABLE') or None)
        admin=browser.new_context();context=browser.new_context(viewport={'width':width,'height':height});page=context.new_page();errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            admin.request.get(BASE+'/');csrf=next(c['value'] for c in admin.cookies() if c['name']=='labseat_pre_csrf')
            login=admin.request.post(BASE+'/auth/login',data={'username':'profile-admin','password':'profile-browser-test-password'},headers={'X-CSRF-Token':csrf});assert login.ok,login.text()
            token=next(c['value'] for c in admin.cookies() if c['name']=='labseat_csrf');headers={'X-CSRF-Token':token}
            now=datetime.now(timezone.utc);name='Ca thi '+uuid.uuid4().hex[:6]
            data=dict(name=name,session_type='exam',venue='Phòng máy A',schedule={k:(now+timedelta(minutes=m)).isoformat() for k,m in [('open_at',-60),('close_at',20),('start_at',30),('end_at',90)]})
            image=BytesIO();Image.new('RGB',(1280,720),'#c5cbd8').save(image,'PNG')
            e=admin.request.post(BASE+'/admin/events',multipart={'data':json.dumps(data),'poster':{'name':'ca.png','mimeType':'image/png','buffer':image.getvalue()}},headers=headers);assert e.ok,e.text();e=e.json()
            response=admin.request.post(BASE+'/admin/rooms/'+e['schedule']['room_id']+'/seats',data={'seat_code':'A01'},headers=headers);assert response.ok,response.text()
            page.goto(BASE+'/');page.locator('#login-link').click();page.locator('#show-register').click()
            form=page.locator('#register');username='profile-'+uuid.uuid4().hex[:10]
            form.locator('[name=username]').fill(username);form.locator('[name=email]').fill(username+'@example.test');form.locator('[name=password]').fill('profile-browser-password');form.locator('[name=password_confirm]').fill('profile-browser-password');page.locator('#register-submit').click()
            pw.expect(page.locator('#login-panel')).to_be_hidden()
            page.locator('#session-grid').get_by_role('button',name='Xem Ca thi · '+name,exact=True).click();page.locator('#event-session-list button').click()
            pw.expect(page.locator('#profile-panel')).to_be_visible();pw.expect(page.locator('#profile-status')).to_have_text('Cần bổ sung thông tin')
            profile=page.locator('#profile-form')
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert page.locator('#session').input_value()==''
            folder=os.getenv('LABSEAT_UI_SCREENSHOTS')
            def shot(name):
                if folder:Path(folder).mkdir(parents=True,exist_ok=True);page.screenshot(path=str(Path(folder)/f'{name}-{width}.png'),full_page=True)
            shot('profile-required')
            profile.locator('[name=full_name]').fill('Nguyễn Văn An');profile.locator('[name=cccd]').fill('012345678901');profile.locator('[name=email]').fill(username+'@example.test')
            # Phone deliberately remains empty; email is mandatory.
            page.locator('#profile-save').click()
            pw.expect(page.locator('#booking-map')).to_be_visible();pw.expect(page.locator('#session')).to_have_value(e['schedule']['id'])
            page.locator('#seats button').first.click();page.locator('#hold-selected').click();pw.expect(page.locator('#hold-panel')).to_be_visible();page.locator('#confirm').click();pw.expect(page.locator('#hold-panel')).to_be_hidden()
            page.locator('#account-toggle').click();page.locator('#profile-link').click();pw.expect(profile.locator('[name=full_name]')).to_have_value('Nguyễn Văn An');pw.expect(page.locator('#profile-status')).to_have_text('Đã đủ thông tin')
            shot('profile-complete')
            profile.locator('[name=email]').fill(username+'@example.test');page.locator('#profile-save').click();pw.expect(page.locator('#profile-message')).to_have_text('Đã lưu hồ sơ.')
            page.reload();pw.expect(profile.locator('[name=email]')).to_have_value(username+'@example.test');pw.expect(profile.locator('[name=cccd]')).to_have_value('012345678901')
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            profile.locator('[name=phone]').fill('');page.locator('#profile-save').click();pw.expect(page.locator('#profile-status')).to_have_text('Đã đủ thông tin')
            page.reload();pw.expect(profile.locator('[name=phone]')).to_have_value('');pw.expect(profile.locator('[name=email]')).to_have_value(username+'@example.test')
            page.locator('#account-toggle').click();page.locator('#logout').click();pw.expect(page.locator('#login-link')).to_be_visible()
            assert profile.locator('[name=cccd]').input_value()==''
            assert context.request.get(BASE+'/me/profile').status==401
            assert not errors,errors
        finally:context.close();admin.close();browser.close()
