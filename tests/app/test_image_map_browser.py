"""Room quadrilaterals, deletion, drag-add, capacities and booking over real HTTP."""
import os,uuid
from pathlib import Path
from datetime import datetime,timedelta,timezone
from io import BytesIO
import pytest
BASE=os.getenv('BROWSER_BASE_URL')
if not BASE:pytest.skip('Live disposable local app required',allow_module_level=True)
if os.getenv('BROWSER_TEST_ALLOWED')!='local-demo-only':raise RuntimeError('Disposable server only')
pw=pytest.importorskip('playwright.sync_api')

@pytest.mark.parametrize('width,height',[(1440,900),(1024,768),(768,1024),(390,844),(320,740)])
def test_room_map_detect_delete_drag_edit_capacity_and_booking(width,height):
    from PIL import Image
    from test_image_detection import floorplan,encoded
    with pw.sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.getenv('BROWSER_EXECUTABLE') or None);contexts=[];errors=[]
        def user(name):
            context=browser.new_context(viewport={'width':width,'height':height});contexts.append(context);page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(BASE+'/#login-panel');page.get_by_label('Tài khoản',exact=True).fill(name);page.get_by_label('Mật khẩu',exact=True).fill(os.environ['BROWSER_TEST_PASSWORD']);page.locator('#login button').click();pw.expect(page.locator('#login-panel')).to_be_hidden()
            if name!='admin':
                csrf=next(c['value'] for c in context.cookies() if c['name']=='labseat_csrf')
                response=context.request.put(BASE+'/me/profile',data={'full_name':'Học viên kiểm thử','cccd':'','phone':'','email':name+'@example.test'},headers={'X-CSRF-Token':csrf});assert response.ok,response.text();page.reload()
            return context,page
        def shot(page,name):
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            folder=os.getenv('LABSEAT_UI_SCREENSHOTS')
            if folder:
                Path(folder).mkdir(parents=True,exist_ok=True);page.evaluate("document.activeElement?.blur();window.scrollTo({top:0,behavior:'instant'})");page.mouse.move(0,0);page.wait_for_timeout(180);page.screenshot(path=str(Path(folder)/f'{name}-{width}.png'),full_page=True)
        try:
            admin,operator=user('admin');now=datetime.now(timezone.utc);name='Ca sơ đồ phòng '+uuid.uuid4().hex[:8]
            form=operator.locator('#event-form');art=BytesIO();Image.new('RGB',(720,958),'#c5cbd8').save(art,'PNG')
            form.locator('[name=poster]').set_input_files({'name':'ca.png','mimeType':'image/png','buffer':art.getvalue()});form.locator('[name=name]').fill(name);form.locator('[name=venue]').fill('Khu thực hành')
            # Reused seeded students need non-overlapping sessions across viewport cases.
            shift=timedelta(hours=2*[1440,1024,768,390,320].index(width))
            for key,m in [('open_at',-60),('close_at',20),('start_at',30),('end_at',90)]:form.locator(f'[name={key}]').fill((now+timedelta(minutes=m)+(shift if key!='open_at' else timedelta())).astimezone(timezone(timedelta(hours=7))).strftime('%Y-%m-%dT%H:%M'))
            operator.locator('#save-event').click();pw.expect(operator.locator('#event-save-status')).to_contain_text('Đã lưu ca')
            event=next(e for e in admin.request.get(BASE+'/events').json() if e['name']==name);room=event['schedule']['room_id']
            normalized=Image.open(BytesIO(admin.request.get(BASE+event['poster_url']).body()));assert normalized.size==(1280,720)
            operator.locator('.admin-nav a[href="#layout-editor"]').click();operator.locator('#editor-event').select_option(event['id'])
            operator.locator('#image-map-file').set_input_files({'name':'rooms.png','mimeType':'image/png','buffer':encoded(floorplan())});operator.locator('#image-map-detect').click();pw.expect(operator.locator('#image-editor-board path')).to_have_count(3)
            assert operator.locator('#image-region-kind,#image-map-tolerance').count()==0
            for rid,label in [('r1','Phòng A'),('r2','Phòng B')]:
                operator.locator(f'#image-editor-board [data-region-id={rid}]').click();pw.expect(operator.locator('#image-region-properties')).to_be_visible();operator.locator('#image-region-label').fill(label);operator.locator('#image-region-capacity').fill('2');operator.locator('#image-region-apply').click()
            operator.locator('#image-editor-board [data-region-id=r3]').click();operator.locator('#image-region-delete').click();pw.expect(operator.locator('#image-editor-board path')).to_have_count(2)
            operator.locator('#room-tool-add').click();svg=operator.locator('#image-editor-board svg');svg.scroll_into_view_if_needed();box=svg.bounding_box()
            a=(box['x']+350/600*box['width'],box['y']+230/360*box['height']);b=(box['x']+500/600*box['width'],box['y']+330/360*box['height'])
            # Escape cancels a drag without adding a room.
            operator.mouse.move(*a);operator.mouse.down();operator.mouse.move(*b,steps=5);operator.keyboard.press('Escape');operator.mouse.up();pw.expect(operator.locator('#image-editor-board path')).to_have_count(2)
            operator.locator('#room-tool-add').click();svg.scroll_into_view_if_needed();box=svg.bounding_box()
            # A room inside an existing room must be rejected by the editor.
            operator.mouse.move(box['x']+40/600*box['width'],box['y']+40/360*box['height']);operator.mouse.down();operator.mouse.move(box['x']+140/600*box['width'],box['y']+120/360*box['height'],steps=5);operator.mouse.up();pw.expect(operator.locator('#image-editor-board path')).to_have_count(2);pw.expect(operator.locator('#image-editor-message')).to_have_text('Phòng mới chồng lên phòng khác.')
            a=(box['x']+350/600*box['width'],box['y']+230/360*box['height']);b=(box['x']+500/600*box['width'],box['y']+330/360*box['height'])
            operator.mouse.move(*a);operator.mouse.down();operator.mouse.move(*b,steps=10);operator.mouse.up();pw.expect(operator.locator('#image-editor-board path')).to_have_count(3)
            operator.locator('#image-region-label').fill('Phòng C');operator.locator('#image-region-capacity').fill('3');operator.locator('#image-region-apply').click();operator.locator('#image-map-save').click();pw.expect(operator.locator('#notice')).to_have_text('Đã lưu sơ đồ phòng.')
            layout=admin.request.get(BASE+f'/rooms/{room}/seat-map').json();assert layout['detector']=='quadrilateral-v1';assert [(r['label'],r['capacity'],r['kind']) for r in layout['elements']]==[('Phòng A',2,'zone'),('Phòng B',2,'zone'),('Phòng C',3,'zone')]
            shot(operator,'room-editor')
            operator.reload()
            sessions=admin.request.get(BASE+'/lab-sessions').json()['items']
            expected_events={e['id'] for e in admin.request.get(BASE+'/admin/events').json()
                             if (e.get('schedule') or next((s for s in sessions if s.get('event_id')==e['id']),{})).get('room_id')}
            pw.expect(operator.locator('#editor-event option')).to_have_count(len(expected_events)+1)
            assert set(operator.locator('#editor-event option').evaluate_all('(options)=>options.map(option=>option.value)'))==expected_events|{''}
            operator.locator('#editor-event').select_option(event['id']);operator.locator('#image-map-load').click();pw.expect(operator.locator('#image-editor-board path')).to_have_count(3)
            operator.locator('#image-editor-board [data-region-id^=m]').click();pw.expect(operator.locator('#image-region-label')).to_have_value('Phòng C');pw.expect(operator.locator('#image-region-capacity')).to_have_value('3')
            for username in ['student001','student002']:
                _,page=user(username);page.goto(BASE+'/#booking');page.locator('#session-grid').get_by_role('button',name='Xem Ca thi · '+name,exact=True).click();page.locator('#event-session-list button').click();pw.expect(page.locator('#seats path')).to_have_count(3)
                page.locator('#seats [data-region-id=r2]').click();pw.expect(page.locator('#seat-summary')).to_contain_text('Phòng B');page.locator('#hold-selected').click();pw.expect(page.locator('#confirm')).to_be_enabled();page.locator('#confirm').click();pw.expect(page.locator('#hold-panel')).to_be_hidden();page.locator('#tickets-link').click()
                ticket=page.locator('#tickets .card').filter(has_text=name).filter(has_text='Phòng B');pw.expect(ticket).to_have_count(1);pw.expect(ticket.get_by_alt_text('QR đăng kí')).to_be_visible();shot(page,'room-registration')
            _,third=user('student003');third.goto(BASE+'/#booking');third.locator('#session-grid').get_by_role('button',name='Xem Ca thi · '+name,exact=True).click();third.locator('#event-session-list button').click();pw.expect(third.locator('#seats [data-region-id=r2]')).to_have_attribute('aria-disabled','true');pw.expect(third.locator('#seats [data-region-id^=m]')).to_have_attribute('aria-disabled','false');third.locator('#seats [data-region-id^=m]').click();pw.expect(third.locator('#seat-summary')).to_contain_text('Phòng C');third.locator('#hold-selected').click();pw.expect(third.locator('#confirm')).to_be_enabled();third.locator('#confirm').click();pw.expect(third.locator('#hold-panel')).to_be_hidden();shot(third,'room-booking')
            operator.locator('#image-map-load').click();pw.expect(operator.locator('#image-map-save')).to_be_disabled();pw.expect(operator.locator('#room-tool-add')).to_be_disabled();operator.locator('#image-editor-board [data-region-id=r1]').click();pw.expect(operator.locator('#image-region-delete')).to_be_disabled()
            assert not errors,errors
        finally:
            for context in contexts:context.close()
            browser.close()
