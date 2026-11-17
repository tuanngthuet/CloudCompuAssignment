"""Account dropdown, guest icon, display name and persisted private avatar over HTTP."""
import os,uuid
from io import BytesIO
from pathlib import Path
import pytest
BASE=os.getenv('BROWSER_BASE_URL','').rstrip('/')
if not BASE:pytest.skip('Live disposable server required',allow_module_level=True)
if os.getenv('BROWSER_TEST_ALLOWED')!='local-demo-only':raise RuntimeError('Disposable server only')
pw=pytest.importorskip('playwright.sync_api')

@pytest.mark.parametrize('width,height',[(1440,900),(1024,768),(768,1024),(390,844),(320,740)])
def test_account_avatar_menu_guest_upload_reload_remove(width,height):
    from PIL import Image,ImageDraw
    blob=BytesIO();im=Image.new('RGB',(400,400),'#e5ddd0');d=ImageDraw.Draw(im);d.ellipse((120,70,280,230),fill='#b83f1c');d.ellipse((45,245,355,550),fill='#b83f1c');im.save(blob,'PNG')
    with pw.sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.getenv('BROWSER_EXECUTABLE') or None);context=browser.new_context(viewport={'width':width,'height':height});page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            page.goto(BASE+'/');pw.expect(page.locator('#login-link')).to_be_visible();pw.expect(page.locator('#account-toggle')).to_be_hidden();pw.expect(page.locator('#login-link img')).to_have_attribute('src','/static/user-default.svg')
            def shot(name):
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                folder=os.getenv('LABSEAT_UI_SCREENSHOTS')
                if folder:
                    Path(folder).mkdir(parents=True,exist_ok=True);page.evaluate("document.activeElement?.blur();window.scrollTo({top:0,behavior:'instant'})");page.mouse.move(0,0);page.wait_for_timeout(220);page.screenshot(path=str(Path(folder)/f'{name}-{width}.png'),full_page=True)
            shot('guest-account')
            page.locator('#login-link').click();page.locator('#show-register').click();form=page.locator('#register');username='avatar-'+uuid.uuid4().hex[:10]
            form.locator('[name=username]').fill(username);form.locator('[name=password]').fill('avatar-browser-password');form.locator('[name=password_confirm]').fill('avatar-browser-password');page.locator('#register-submit').click()
            pw.expect(page.locator('#account-toggle')).to_be_visible();pw.expect(page.locator('#identity')).to_have_text(username);pw.expect(page.locator('#account-avatar')).to_have_attribute('src','/static/user-default.svg')
            page.locator('#account-toggle').click();pw.expect(page.locator('#account-menu')).to_be_visible();assert page.locator('#account-menu').inner_text().splitlines()==['Tài khoản','Đăng xuất']
            page.keyboard.press('Escape');pw.expect(page.locator('#account-menu')).to_be_hidden();pw.expect(page.locator('#account-toggle')).to_be_focused()
            page.keyboard.press('ArrowDown');pw.expect(page.locator('#profile-link')).to_be_focused();page.keyboard.press('Enter')
            profile=page.locator('#profile-form');pw.expect(profile).to_be_visible();pw.expect(profile.locator('[name=full_name]')).to_be_enabled()
            profile.locator('[name=full_name]').fill('Nguyễn Thiện Tuấn');profile.locator('[name=email]').fill('avatar-test@example.test');page.locator('#profile-save').click();pw.expect(page.locator('#identity')).to_have_text('Nguyễn Thiện Tuấn')
            page.locator('#avatar-file').set_input_files({'name':'avatar.png','mimeType':'image/png','buffer':blob.getvalue()});pw.expect(page.locator('#avatar-message')).to_have_text('Đã lưu ảnh đại diện.')
            src=page.locator('#account-avatar').get_attribute('src');assert src.startswith('/me/avatar?v=');pw.expect(page.locator('#profile-avatar')).to_have_attribute('src',src)
            pw.expect(page.locator('#account-avatar')).to_have_js_property('naturalWidth',256)
            shot('profile-avatar')
            page.locator('#account-toggle').click();shot('account-menu');page.locator('#profile-title').click();pw.expect(page.locator('#account-menu')).to_be_hidden()
            page.reload();pw.expect(page.locator('#identity')).to_have_text('Nguyễn Thiện Tuấn');pw.expect(page.locator('#account-avatar')).to_have_attribute('src',src)
            page.locator('#avatar-file').set_input_files({'name':'bad.png','mimeType':'image/png','buffer':b'not an image'});pw.expect(page.locator('#avatar-message')).to_contain_text('không hợp lệ');pw.expect(page.locator('#account-avatar')).to_have_attribute('src',src)
            page.locator('#avatar-remove').click();pw.expect(page.locator('#account-avatar')).to_have_attribute('src','/static/user-default.svg');assert context.request.get(BASE+'/me/avatar').status==404
            page.locator('#account-toggle').click();page.locator('#logout').click();pw.expect(page.locator('#login-link')).to_be_visible();pw.expect(page.locator('#account-toggle')).to_be_hidden();assert context.request.get(BASE+'/me/avatar').status==401
            assert not errors,errors
        finally:context.close();browser.close()
