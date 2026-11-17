"""Room selection/polling preserve the SVG, image, list, scroll and keyboard focus."""
import json,os
from datetime import datetime,timedelta,timezone
from pathlib import Path
import pytest
if os.getenv('LABSEAT_BROWSER_UI_TEST')!='1':pytest.skip('Browser fixture opt-in required',allow_module_level=True)
pw=pytest.importorskip('playwright.sync_api')
ROOT=Path(__file__).resolve().parents[2]

@pytest.mark.parametrize('width,height',[(1440,900),(390,844),(320,740)])
def test_room_updates_do_not_reload_image_or_rebuild_list(width,height):
    now=datetime.now(timezone.utc);stamps={k:(now+timedelta(minutes=m)).isoformat() for k,m in [('open_at',-60),('close_at',60),('start_at',90),('end_at',150)]}
    lab=dict(id='s1',event_id='e1',room_id='room',session_type='practice',**stamps)
    state={'remaining':2,'revision':1,'maps':0,'images':0,'seats':0,'fail':False}
    with pw.sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.getenv('BROWSER_EXECUTABLE') or None);page=browser.new_page(viewport={'width':width,'height':height});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        def respond(route):
            path=route.request.url.split('labseat.test',1)[1].split('?')[0]
            if path=='/':return route.fulfill(content_type='text/html',body=(ROOT/'app/templates/index.html').read_text())
            if path.startswith('/static/'):
                asset=ROOT/'app'/path.lstrip('/');return route.fulfill(content_type='text/css' if path.endswith('.css') else 'image/svg+xml' if path.endswith('.svg') else 'text/javascript',body=asset.read_bytes())
            if path in ['/map.png','/poster.png']:
                if path=='/map.png':state['images']+=1
                return route.fulfill(content_type='image/svg+xml',body='<svg xmlns="http://www.w3.org/2000/svg" width="500" height="220"><rect width="500" height="220" fill="#eee"/><path d="M10 10H230V200H10ZM260 10H490V200H260Z" fill="white" stroke="black"/></svg>')
            status=200
            if path=='/me':data={'id':'u1','username':'student','role':'student','profile_complete':True}
            elif path=='/rooms':data=[{'id':'room','name':'Khu A'}]
            elif path=='/lab-sessions':data={'items':[lab],'server_time':now.isoformat(),'queue_policy':{'enabled':False}}
            elif path=='/events':data=[dict(id='e1',session_type='practice',name='Ca thực hành ổn định',venue='Khu A',description='',address='',poster_url='/poster.png',schedule=lab)]
            elif path=='/me/tickets':data=[]
            elif path.endswith('/seats'):
                state['seats']+=1
                if state['fail']:status=503;data={'code':'temporary','message':'Chưa cập nhật được số suất.'}
                else:data={'server_time':datetime.now(timezone.utc).isoformat(),'layout_revision':state['revision'],'items':[{'id':'a','seat_code':'Phòng A','available':state['remaining']>0,'remaining':state['remaining'],'capacity':2},{'id':'b','seat_code':'Phòng B','available':True,'remaining':3,'capacity':3}]}
            elif path.endswith('/seat-map'):
                state['maps']+=1
                data={'type':'image','detector':'quadrilateral-v1','columns':500,'rows':220,'image_url':'/map.png','revision':state['revision'],'elements':[{'id':'a','seat_id':'a','kind':'zone','label':'Phòng A','capacity':2,'points':[[10+state['revision'],10],[230,10],[230,200],[10+state['revision'],200]]},{'id':'b','seat_id':'b','kind':'zone','label':'Phòng B','capacity':3,'points':[[260,10],[490,10],[490,200],[260,200]]}]}
            else:data=[]
            return route.fulfill(status=status,content_type='application/json',body=json.dumps(data))
        page.route('http://labseat.test/**',respond)
        try:
            page.goto('http://labseat.test/');page.locator('#session-types [data-type=practice]').click();page.locator('#sessions-open .event-card').click();page.locator('#event-session-list button').click()
            buttons=page.locator('#seats .image-map-option');pw.expect(buttons).to_have_count(2)
            page.evaluate("window.original={svg:document.querySelector('#seats svg'),image:document.querySelector('#seats image'),button:document.querySelector('#seats button'),path:document.querySelector('#seats path')}")
            buttons.first.click();pw.expect(buttons.first).to_have_attribute('aria-pressed','true')
            assert page.evaluate("original.button===document.querySelector('#seats button') && original.image===document.querySelector('#seats image')")
            before=state['seats'];scroll=page.evaluate('scrollY')
            page.wait_for_timeout(5400)  # Exercise the real 5-second background timer.
            assert state['seats']>before
            assert page.evaluate("original.svg===document.querySelector('#seats svg') && original.button===document.activeElement && original.path===document.querySelector('#seats path')")
            assert abs(page.evaluate('scrollY')-scroll)<2
            assert state['maps']==1 and state['images']==1
            state['remaining']=1;page.evaluate('availability()');pw.expect(buttons.first).to_contain_text('Còn 1/2');pw.expect(buttons.first).to_have_attribute('aria-pressed','true')
            assert page.evaluate("original.button===document.querySelector('#seats button')")
            state['fail']=True;page.evaluate('pollAvailability()');pw.expect(page.locator('#notice')).to_have_text('Chưa cập nhật được số suất.')
            assert page.evaluate("original.image===document.querySelector('#seats image')")
            state['fail']=False;state['remaining']=0;page.evaluate('availability()');pw.expect(buttons.first).to_be_disabled();pw.expect(page.locator('#hold-selected')).to_be_disabled()
            assert state['maps']==1
            state['revision']=2;page.evaluate('availability()');assert state['maps']==2
            assert page.evaluate("original.svg!==document.querySelector('#seats svg')")
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert not errors,errors
        finally:browser.close()
