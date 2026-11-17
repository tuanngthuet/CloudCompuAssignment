"""LABSEAT catalogue filters and terminology in a real browser with API fixtures."""
import json
import os
from pathlib import Path
from datetime import datetime,timedelta,timezone
from io import BytesIO
import pytest
if os.getenv('LABSEAT_BROWSER_UI_TEST')!='1':pytest.skip('Opt-in browser fixtures',allow_module_level=True)
pw=pytest.importorskip('playwright.sync_api')
ROOT=Path(__file__).resolve().parents[2]

@pytest.mark.parametrize('width,height',[(1440,900),(1024,768),(768,1024),(390,844),(320,740)])
def test_labseat_vertical_status_sections_and_horizontal_cards(width,height):
    from PIL import Image,ImageDraw
    now=datetime.now(timezone.utc)
    events=[]
    for i,(kind,start,close) in enumerate([('exam',0,60),('exam',60,120),('exam',-120,0),('practice',-60,60)]):
        schedule={k:(now+timedelta(minutes=m)).isoformat() for k,m in [('open_at',start),('close_at',close),('start_at',max(close+30,30)),('end_at',max(close+90,90))]}
        schedule|={'id':f's{i}','room_id':f'r{i}','event_id':f'e{i}'}
        events.append(dict(id=f'e{i}',name=('Ca thi lập trình cơ sở — kiểm tra thực hành cuối học phần dành cho sinh viên' if i==1 else f'Ca {i}'),session_type=kind,venue='Phòng máy A',address='',description='Nội dung ca',poster_url=f'/images/{i}.png',schedule=schedule))
    for i in range(4,8):
        base=events[0];events.append(base|{'id':f'e{i}','name':f'Ca thi bổ sung {i}','poster_url':f'/images/{i}.png','schedule':base['schedule']|{'id':f's{i}','room_id':f'r{i}','event_id':f'e{i}'}})
    images=[]
    for i in range(4):
        im=Image.new('RGB',(1280,720),['#cbbfa9','#c5d1c2','#c5cbd8','#d8c8b6'][i]);d=ImageDraw.Draw(im)
        d.text((48,80),'LABSEAT',fill='#252720',font_size=70);d.text((48,250),'CA THI' if i<3 else 'THUC HANH',fill='#252720',font_size=55);d.text((48,610),f'PHONG MAY A / 0{i+1}',fill='#252720',font_size=32)
        out=BytesIO();im.save(out,'PNG');images.append(out.getvalue())
    with pw.sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.getenv('BROWSER_EXECUTABLE') or None)
        page=browser.new_page(viewport={'width':width,'height':height});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.add_init_script(f'Date.now=()=>{int(now.timestamp()*1000)};')
        def respond(route):
            path=route.request.url.split('labseat.test',1)[1].split('?')[0]
            if path=='/':return route.fulfill(content_type='text/html',body=(ROOT/'app/templates/index.html').read_text())
            if path.startswith('/static/'):
                f=ROOT/'app'/path.lstrip('/');return route.fulfill(content_type='text/css' if path.endswith('.css') else 'image/svg+xml' if path.endswith('.svg') else 'text/javascript',body=f.read_bytes())
            if path.startswith('/images/'):return route.fulfill(content_type='image/png',body=images[int(path.split('/')[-1].split('.')[0])%len(images)])
            data=[];code=200
            if path=='/events':data=events
            elif path=='/lab-sessions':data={'items':[e['schedule'] for e in events],'server_time':now.isoformat()}
            elif path=='/me':code=401;data={'message':'Vui lòng đăng nhập'}
            return route.fulfill(status=code,content_type='application/json',body=json.dumps(data))
        page.route('http://labseat.test/**',respond)
        try:
            page.goto('http://labseat.test/')
            pw.expect(page.locator('#session-grid .event-card')).to_have_count(7)
            assert page.locator('#session-types button').all_text_contents()==['Ca thi','Ca thực hành']
            assert page.locator('#session-statuses').count()==0
            assert page.locator('.session-section h2').all_text_contents()==['Đang mở đăng kí','Sắp đăng kí','Đã qua thời hạn đăng kí']
            pw.expect(page.locator('#sessions-open .event-card')).to_have_count(5)
            pw.expect(page.locator('#sessions-soon .event-card')).to_have_count(1)
            pw.expect(page.locator('#sessions-closed .event-card')).to_have_count(1)
            tops=[page.locator('#sessions-'+key+'-section').bounding_box()['y'] for key in ['open','soon','closed']]
            assert tops[0]<tops[1]<tops[2]
            assert page.locator('#event-banners,#featured-events,#upcoming-events,[name=banner],[name=mode],[name=featured],[name=category]').count()==0
            def shot(name):
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                visible=page.locator('body').inner_text()
                for forbidden in ['sự kiện','Sự kiện','Âm nhạc','Workshop']:assert forbidden not in visible
                page.locator('[data-enter]').evaluate('async el=>{await Promise.all(el.getAnimations().map(a=>a.finished));}')
                folder=os.getenv('LABSEAT_UI_SCREENSHOTS')
                if folder:Path(folder).mkdir(parents=True,exist_ok=True);page.screenshot(path=str(Path(folder)/f'{name}-{width}.png'),full_page=True)
            for card in page.locator('#session-grid .event-card').all():
                image=card.locator('img');pw.expect(image).to_have_attribute('width','1280');pw.expect(image).to_have_attribute('height','720')
                frame=card.locator('.event-art').bounding_box();assert abs(frame['width']/frame['height']-16/9)<0.02
                title=card.locator('h3');venue=card.locator('.session-card-venue');registration=card.locator('.session-card-registration')
                assert title.bounding_box()['y']>=frame['y']+frame['height']
                assert venue.bounding_box()['y']>=title.bounding_box()['y']+title.bounding_box()['height']
                assert registration.bounding_box()['y']>=venue.bounding_box()['y']+venue.bounding_box()['height']
                assert registration.inner_text().startswith('Bắt đầu đăng kí: ')
                event=next(e for e in events if e['name']==title.inner_text())
                expected=datetime.fromisoformat(event['schedule']['open_at']).astimezone(timezone(timedelta(hours=7))).strftime('%H:%M')
                assert expected in registration.inner_text()
                assert title.evaluate('(n)=>n.scrollWidth<=n.clientWidth')
            assert page.locator('#session-grid .event-card').first.bounding_box()['width']>(250 if width>=390 else 200)
            shot('dashboard')
            right=page.locator('#sessions-open-actions [data-direction="1"]');pw.expect(right).to_be_enabled()
            right.click()
            page.wait_for_function("document.querySelector('#sessions-open').scrollLeft>0")
            pw.expect(page.locator('#sessions-open-actions [data-direction="-1"]')).to_be_enabled()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.locator('#sessions-soon .event-card').click();pw.expect(page.locator('#event-session-list button')).to_be_disabled()
            page.locator('#sessions-closed .event-card').click();pw.expect(page.locator('#event-session-list button')).to_be_disabled();shot('closed-ca')
            page.locator('#session-types [data-type=practice]').click();pw.expect(page.locator('#session-grid .event-card')).to_have_count(1)
            pw.expect(page.locator('#sessions-soon-section')).to_be_hidden();pw.expect(page.locator('#sessions-closed-section')).to_be_hidden();shot('practice')
            page.locator('#sessions-open .event-card').click();pw.expect(page.locator('#event-session-list button')).to_have_text('Đăng kí');shot('detail')
            page.locator('#event-search').fill('không có');pw.expect(page.locator('#events-empty')).to_be_visible();shot('empty')
            pw.expect(page.locator('.session-section:visible')).to_have_count(0)
            page.locator('#event-search').fill('');page.locator('#session-types [data-type=exam]').click();pw.expect(page.locator('#sessions-open .event-card')).to_have_count(5)
            assert len(set(page.locator('#session-grid .event-card').all_text_contents()))==7
            assert not errors
        finally:browser.close()
