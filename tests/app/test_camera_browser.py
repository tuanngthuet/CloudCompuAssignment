"""Opt-in real Chrome camera/QR tests with fake media and mocked HTTP APIs."""
import os
import pytest
if os.getenv('RUN_CAMERA_BROWSER_TESTS') != '1':
    pytest.skip('RUN_CAMERA_BROWSER_TESTS=1 and local Chrome required', allow_module_level=True)
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit
import httpx
import qrcode
from PIL import Image
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
CODE = 'labseat-camera-fixture-ticket-1234567890'
RID = '00000000-0000-4000-8000-000000000001'
SESSION = {'id':'fixture-session','room_id':'fixture-room','event_id':'fixture-event','name':'Ca thực hành kiểm thử','room_name':'Khu thực hành','seat_code':'A101','start_at':'2026-11-20T01:00:00Z','end_at':'2026-11-20T03:00:00Z','open_at':'2026-11-10T01:00:00Z','close_at':'2026-11-19T01:00:00Z'}


def receipt(enabled=True, checked=False):
    return {'ticket':{'reservation_id':RID,'ticket_code':CODE,'status':'CHECKED_IN' if checked else 'CONFIRMED','checked_in_at':'2026-11-16T01:00:00Z' if checked else None},
        'session':SESSION | {'checkin_enabled':enabled},
        'profile':{'username':'student-fixture','full_name':'Nguyễn Văn An','cccd':'012345678901','email':'an@example.test','phone':'','avatar_url':None},
        'can_check_in':enabled and not checked,
        'reason':'Vé đã được check-in.' if checked else ('Vé hợp lệ. Có thể xác nhận check-in.' if enabled else 'Ca chưa mở check-in.')}



@pytest.fixture(scope='module')
def server():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    env = os.environ | {'DATABASE_URL': 'postgresql+psycopg://fake:fake@127.0.0.1:1/unavailable', 'APP_ENV': 'test'}
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            assert process.poll() is None
            try:
                if httpx.get(base + '/healthz').status_code == 200: break
            except httpx.TransportError: pass
            time.sleep(.05)
        else: pytest.fail('Disposable camera test HTTP server did not start')
        yield base
    finally:
        process.terminate(); process.wait(timeout=10)


@pytest.fixture(scope='module')
def media(tmp_path_factory):
    folder = tmp_path_factory.mktemp('camera')
    image = Image.new('RGB', (640, 480), 'white')
    qr = qrcode.make(CODE).convert('RGB'); image.paste(qr, ((640-qr.width)//2, (480-qr.height)//2))
    image.save(folder/'qr.png')
    # Chrome's fake capture device reads a real video stream in Y4M format.
    gray = image.convert('L').tobytes(); chroma = bytes([128]) * (320*240)
    with (folder/'camera.y4m').open('wb') as output:
        output.write(b'YUV4MPEG2 W640 H480 F10:1 Ip A1:1 C420jpeg\n')
        for _ in range(20): output.write(b'FRAME\n'+gray+chroma+chroma)
    return folder


@pytest.fixture
def camera_page(server, media):
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.getenv('CHROME_BIN') or None, headless=True,
            args=['--no-sandbox', '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
                  f'--use-file-for-fake-video-capture={media / "camera.y4m"}'])
        context = browser.new_context()
        page = context.new_page(); requests = []; errors = []; state = {'enabled':True,'checked':False}
        page.on('pageerror', lambda error: errors.append(str(error)))
        def route(request_route):
            request = request_route.request; path = urlsplit(request.url).path
            if path.startswith('/static/') or path in ('/', '/healthz'):
                if urlsplit(request.url).hostname == 'labseat-http.test':
                    request_route.fulfill(response=request_route.fetch(url=server+path))
                else:
                    request_route.continue_()
                return
            if path == '/admin/check-ins':
                requests.append(request.post_data_json); state['checked']=True; data = {'status':'CHECKED_IN'}
            elif path == '/admin/check-ins/lookup':
                if request.post_data_json['ticket_code'] not in (CODE,RID):
                    request_route.fulfill(status=404,content_type='application/json',body=json.dumps({'code':'ticket_not_found','message':'Không tìm thấy vé.'}));return
                data = receipt(state['enabled'],state['checked'])
            elif path == '/admin/lab-sessions/fixture-session/check-in':
                state['enabled']=request.post_data_json['enabled'];data={'session_id':'fixture-session','checkin_enabled':state['enabled']}
            elif path in ('/events','/admin/events'): data = [{'id':'fixture-event','name':SESSION['name'],'session_type':'practice','venue':'Khu thực hành','address':'','description':'Ca kiểm thử','poster_url':'/static/labseat.svg','schedule':SESSION|{'checkin_enabled':state['enabled']}}]
            elif path == '/rooms': data = [{'id':'fixture-room','name':'Khu thực hành'}]
            elif path == '/me': data = {'id':'fixture-admin', 'username':'admin', 'role':'admin', 'profile_complete':True}
            elif path == '/lab-sessions': data = {'items':[SESSION | {'checkin_enabled':state['enabled'],'session_type':'practice'}], 'queue_policy':{'enabled':False}}
            else: data = []
            request_route.fulfill(status=200, content_type='application/json', body=json.dumps(data))
        page.route(server+'/**', route)
        page.route('http://labseat-http.test/**', route)
        page.add_init_script("Object.defineProperty(window,'BarcodeDetector',{value:undefined,configurable:true});")
        yield page, server, media, requests, errors
        browser.close()


def open_scanner(page, server):
    page.goto(server+'/#checkin-form')
    expect(page.locator('#checkin-form')).to_be_visible()
    page.wait_for_function("typeof window.jsQR === 'function'")


def test_video_camera_reads_qr_without_native_detector_and_requires_confirmation(camera_page):
    page, server, _, requests, errors = camera_page
    open_scanner(page, server)
    assert page.evaluate('window.BarcodeDetector === undefined')
    page.locator('#camera').click()
    expect(page.locator('[name=ticket_code]')).to_have_value(CODE, timeout=15000)
    expect(page.locator('#checkin-result')).to_be_visible()
    expect(page.locator('#checkin-profile-info')).to_contain_text('Nguyễn Văn An')
    expect(page.locator('#checkin-confirm')).to_be_visible()
    assert page.evaluate('document.getElementById("preview").srcObject === null')
    assert requests == []
    page.locator('#checkin-confirm').click()
    expect(page.locator('#notice')).to_have_text('Đã xác nhận check-in.')
    assert requests == [{'ticket_code': CODE}] and errors == []


def test_photo_fallback_decodes_locally_without_opening_camera(camera_page):
    page, server, media, requests, errors = camera_page
    page.add_init_script("window.cameraRequests=0; navigator.mediaDevices.getUserMedia=async()=>{window.cameraRequests++;throw new DOMException('denied','NotAllowedError');};")
    open_scanner(page, server)
    page.locator('#camera-image').set_input_files(media/'qr.png')
    expect(page.locator('[name=ticket_code]')).to_have_value(CODE)
    assert page.evaluate('window.cameraRequests') == 0 and requests == [] and errors == []


def test_permission_denied_explains_browser_permission(camera_page):
    page, server, _, requests, errors = camera_page
    page.add_init_script("navigator.mediaDevices.getUserMedia=async()=>{throw new DOMException('denied','NotAllowedError');};")
    open_scanner(page, server); page.locator('#camera').click()
    expect(page.locator('#camera-status')).to_contain_text('cấp quyền camera')
    expect(page.locator('#camera')).to_be_enabled(); assert requests == [] and errors == []


def test_broken_native_detector_falls_back_to_jsqr(camera_page):
    page, server, _, requests, errors = camera_page
    page.add_init_script("window.BarcodeDetector=class{static async getSupportedFormats(){return ['qr_code'];}async detect(){throw new DOMException('unsupported','NotSupportedError');}};")
    open_scanner(page, server); page.locator('#camera').click()
    expect(page.locator('[name=ticket_code]')).to_have_value(CODE, timeout=15000)
    assert requests == [] and errors == []


def test_navigation_stops_live_tracks(camera_page):
    page, server, _, _, errors = camera_page
    open_scanner(page, server)
    page.evaluate('window.jsQR=()=>null'); page.locator('#camera').click()
    expect(page.locator('#preview')).to_have_js_property('videoWidth',640)
    assert page.evaluate('cameraStream !== null')
    page.evaluate('window.testStream=cameraStream;location.hash="#booking"')
    for _ in range(100):
        if page.evaluate('window.testStream.getTracks().every(track=>track.readyState === "ended")'):break
        page.wait_for_timeout(50)
    else:pytest.fail('Camera tracks remained live after leaving check-in')
    assert page.evaluate('cameraStream === null') and errors == []


def test_plain_http_origin_can_import_photo_without_https(camera_page):
    page, _, media, requests, errors = camera_page
    page.set_viewport_size({'width':375,'height':812})
    page.goto('http://labseat-http.test/#checkin-form')
    expect(page.locator('#checkin-form')).to_be_visible()
    assert page.evaluate('isSecureContext') is False
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#camera').click()
    expect(page.locator('#camera-status')).to_contain_text('HTTPS hoặc localhost')
    page.locator('#camera-image').set_input_files(media/'qr.png')
    expect(page.locator('[name=ticket_code]')).to_have_value(CODE)
    assert requests == [] and errors == []


def test_non_ticket_qr_does_not_navigate_or_check_in(camera_page):
    page, server, _, requests, errors = camera_page
    image = io.BytesIO(); qrcode.make('https://example.invalid/login').save(image, format='PNG')
    open_scanner(page, server)
    page.locator('#camera-image').set_input_files({'name':'external.png', 'mimeType':'image/png', 'buffer':image.getvalue()})
    expect(page.locator('#camera-status')).to_contain_text('không phải mã vé LABSEAT')
    expect(page.locator('[name=ticket_code]')).to_have_value('')
    assert page.url.startswith(server) and requests == [] and errors == []


@pytest.mark.parametrize('width,height', [(1440,900),(1024,768),(768,1024),(390,844),(320,720)])
def test_qr_modal_layout_animation_and_escape(camera_page, width, height):
    page, server, _, requests, errors = camera_page
    page.set_viewport_size({'width':width,'height':height})
    open_scanner(page, server)
    page.evaluate('window.jsQR=()=>null')
    page.get_by_role('button',name='Quét QR',exact=True).click()
    dialog = page.get_by_role('dialog',name='Quét mã QR')
    expect(dialog).to_be_visible()
    expect(page.locator('#qr-stage')).to_have_attribute('data-scanning','true')
    bounds = dialog.bounding_box(); stage = page.locator('#qr-stage').bounding_box(); frame = page.locator('.qr-viewfinder').bounding_box()
    assert bounds['width'] <= 420 and bounds['x'] >= 15 and bounds['y'] >= 15
    assert bounds['y'] + bounds['height'] <= height - 15
    assert abs(stage['width'] - stage['height']) < 1
    assert abs(frame['width']/stage['width'] - .76) < .01
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    beam = page.locator('.qr-scan-beam')
    assert beam.evaluate("el=>getComputedStyle(el).animationName") == 'qr-sweep'
    assert beam.evaluate("el=>el.getAnimations()[0].playState") == 'running'
    folder = os.getenv('QR_MODAL_SCREENSHOTS')
    if folder:
        destination = Path(folder); destination.mkdir(parents=True,exist_ok=True)
        beam.evaluate('el=>el.getAnimations().forEach(a=>{a.pause();a.currentTime=1300;})')
        page.screenshot(path=str(destination/f'scanner-{width}.png'))
    page.evaluate('window.testStream=cameraStream')
    page.keyboard.press('Escape')
    expect(dialog).not_to_be_visible()
    assert page.evaluate('window.testStream.getTracks().every(track=>track.readyState === "ended")')
    expect(page.locator('#camera')).to_be_focused()
    assert requests == [] and errors == []


@pytest.mark.parametrize('closing', ['button','backdrop','enter'])
def test_qr_modal_close_stops_camera(camera_page, closing):
    page, server, _, requests, errors = camera_page
    open_scanner(page, server); page.evaluate('window.jsQR=()=>null'); page.locator('#camera').click()
    expect(page.locator('#qr-stage')).to_have_attribute('data-scanning','true')
    page.evaluate('window.testStream=cameraStream')
    if closing == 'button': page.get_by_role('button',name='Đóng trình quét QR').click()
    elif closing == 'enter': page.keyboard.press('Enter')
    else: page.mouse.click(8,8)
    expect(page.locator('#qr-dialog')).not_to_be_visible()
    assert page.evaluate('window.testStream.getTracks().every(track=>track.readyState === "ended")')
    assert requests == [] and errors == []


def test_qr_modal_respects_reduced_motion(camera_page):
    page, server, _, requests, errors = camera_page
    page.emulate_media(reduced_motion='reduce')
    open_scanner(page, server); page.evaluate('window.jsQR=()=>null'); page.locator('#camera').click()
    expect(page.locator('#qr-stage')).to_have_attribute('data-scanning','true')
    assert page.locator('.qr-scan-beam').evaluate('el=>getComputedStyle(el).animationName') == 'none'
    page.get_by_role('button',name='Đóng trình quét QR').click()
    assert requests == [] and errors == []



def test_manual_entry_previews_ticket_and_profile_without_checkin(camera_page):
    page, server, _, requests, errors = camera_page
    open_scanner(page,server)
    page.locator('[name=ticket_code]').fill(RID)
    expect(page.locator('#checkin-result')).to_be_visible()
    expect(page.locator('#checkin-profile-info')).to_contain_text('012345678901')
    expect(page.locator('#checkin-profile-info')).to_contain_text('an@example.test')
    expect(page.locator('#checkin-profile-info')).to_contain_text('Không cung cấp')
    expect(page.locator('#checkin-confirm')).to_be_visible()
    folder=os.getenv('CHECKIN_SCREENSHOTS')
    if folder:
        Path(folder).mkdir(parents=True,exist_ok=True);page.locator('#checkin-form').screenshot(path=str(Path(folder)/'ticket-profile-desktop.png'))
    assert requests == [] and errors == []


def test_management_switch_controls_checkin_action_on_existing_session(camera_page):
    page, server, _, requests, errors = camera_page
    page.goto(server+'/#event-form')
    page.locator('#event-choice').select_option('fixture-event')
    expect(page.locator('#event-checkin-toggle')).to_have_text('Đóng check-in')
    page.locator('#event-checkin-toggle').click()
    expect(page.locator('#event-checkin-status')).to_have_text('Đang đóng check-in')
    folder=os.getenv('CHECKIN_SCREENSHOTS')
    if folder:
        Path(folder).mkdir(parents=True,exist_ok=True);page.locator('#event-checkin-control').screenshot(path=str(Path(folder)/'session-control.png'))
    page.locator('a[href="#checkin-form"]').click()
    page.locator('[name=ticket_code]').fill(CODE)
    expect(page.locator('#checkin-result')).to_be_visible()
    expect(page.locator('#checkin-confirm')).not_to_be_visible()
    expect(page.locator('#checkin-profile-info')).to_contain_text('Nguyễn Văn An')
    page.locator('a[href="#event-form"]').click()
    page.locator('#event-checkin-toggle').click()
    expect(page.locator('#event-checkin-status')).to_have_text('Đang mở check-in')
    page.locator('a[href="#checkin-form"]').click()
    page.get_by_role('button',name='Tra cứu vé',exact=True).click()
    expect(page.locator('#checkin-confirm')).to_be_visible()
    page.locator('#checkin-confirm').click()
    expect(page.locator('#checkin-decision')).to_contain_text('Vé đã được check-in')
    expect(page.locator('#checkin-confirm')).not_to_be_visible()
    assert len(requests) == 1 and errors == []


def test_checkin_preview_remains_within_mobile_viewport(camera_page):
    page, server, _, requests, errors = camera_page
    page.set_viewport_size({'width':390,'height':844});open_scanner(page,server)
    page.locator('[name=ticket_code]').fill(CODE)
    expect(page.locator('#checkin-result')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    folder=os.getenv('CHECKIN_SCREENSHOTS')
    if folder:
        Path(folder).mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(Path(folder)/'ticket-profile-mobile.png'),full_page=True)
    assert requests == [] and errors == []
