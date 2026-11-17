'use strict';
const $ = id => document.getElementById(id);
let me = null, labs = [], held = null, expires = 0, offset = 0, cameraStream = null, scanTimer = null, availabilityRevision = 0, cameraRevision = 0, cameraStarting = false;
let eventNames=new Map(),pendingProfileSession=null,profileRevision=0;
let mapSessionId=null,bookingLayoutCache=null,availabilityPolling=false;
let selectedSeat=null,currentMap=null,allRooms=[],registrationRows=[],activeRegistration=null,registrationRevision=0,holdBusy=false;
let queuePolicy={enabled:false},queueState=null,queueSessionId=null,queueNextHeartbeat=0,queueOffset=0,queueRevision=0,queueUncertain=false,queueBusy=false;
let queueFlight=Promise.resolve(),queueChanging=0,queueNewSelection=false,queueUpdatedAt=null;
let checkinReceipt=null,checkinRevision=0,checkinBusy=false,checkinLookupTimer=null;
const date = s => new Date(s).toLocaleString('vi-VN', {timeZone:'Asia/Ho_Chi_Minh'});
const cookie = name => document.cookie.split('; ').find(x => x.startsWith(name + '='))?.split('=').slice(1).join('=') || '';
function notice(message) { $('notice').textContent = message; window.dispatchEvent(new CustomEvent('labseat-notice',{detail:message})); }
// Keep one mutation key after uncertain network/server failure; no automatic POST retry.
const mutationKeys=new Map();
async function api(path, method='GET', body=null) {
  const headers = {};
  if(method !== 'GET') headers['X-CSRF-Token'] = decodeURIComponent(cookie(['/auth/login','/auth/register','/auth/email-verification/confirm','/auth/password-reset/request','/auth/password-reset/confirm'].includes(path)?'labseat_pre_csrf':'labseat_csrf'));
  if(body && !(body instanceof FormData)) headers['Content-Type'] = 'application/json';
  const idempotent=method==='POST'&&(path==='/holds'||/^\/holds\/[^/]+\/confirm$/.test(path)||/^\/reservations\/[^/]+\/cancel$/.test(path));
  const mutationId=idempotent?`${me?.id||''}:${path}:${JSON.stringify(body)}`:null;
  if(mutationId){
    if(!mutationKeys.has(mutationId))mutationKeys.set(mutationId,Array.from(crypto.getRandomValues(new Uint8Array(16)),x=>x.toString(16).padStart(2,'0')).join(''));
    headers['Idempotency-Key']=mutationKeys.get(mutationId);
  }
  const response = await fetch(path,{method,headers,body:body instanceof FormData?body:body?JSON.stringify(body):null});
  if(mutationId&&(response.ok||(response.status>=400&&response.status<500)))mutationKeys.delete(mutationId);
  if(!response.ok) { const e=await response.json(); const error=new Error(e.message);error.code=e.code;error.status=response.status;if(e.code==='profile_required'||e.code==='email_verification_required')window.dispatchEvent(new CustomEvent('labseat-profile-required',{detail:{sessionId:$('session').value}}));throw error; }
  return response.headers.get('content-type')?.includes('json') ? response.json() : response.blob();
}
function action(fn) { return async event => {event?.preventDefault(); try {await fn(event);} catch(e) {notice(e.message);} }; }
function button(text, fn) {const b=document.createElement('button');b.textContent=text;b.onclick=action(fn);return b;}
function line(parent,text,tag='p'){const e=document.createElement(tag);e.textContent=text;parent.append(e);return e;}
function values(form) {return Object.fromEntries(new FormData(form));}
function renderAccount(){
  $('identity').textContent=me?(me.full_name||me.username):'';
  $('account-toggle').hidden=!me;$('account-menu').hidden=true;$('account-toggle').setAttribute('aria-expanded','false');
  const url=me?.avatar_url||'/static/user-default.svg';
  for(const id of ['account-avatar','profile-avatar']){$(id).src=url;$(id).onerror=()=>{$(id).onerror=null;$(id).src='/static/user-default.svg';};}
  $('avatar-remove').hidden=!me?.avatar_url;
}
async function identity() {
  try{me=await api('/me');}catch{me=null;}
  renderAccount();
  $('login-panel').hidden=!!me;$('logout').hidden=!me;$('tickets-panel').hidden=!me;$('admin-panel').hidden=me?.role!=='admin';$('admin-link').hidden=me?.role!=='admin';
  window.dispatchEvent(new CustomEvent('labseat-identity',{detail:me}));
  if(me)await tickets();
}
function eventTitle(lab){return eventNames.get(lab?.event_id)||allRooms.find(r=>r.id===lab?.room_id)?.name||'Ca';}
window.addEventListener('labseat-events',event=>{eventNames=new Map(event.detail.map(e=>[e.id,e.name]));updateSummary();});
async function catalogue() {
  const rooms=await api('/rooms');allRooms=rooms;
  const catalogueData=await api('/lab-sessions');if(catalogueData.server_time)offset=Date.parse(catalogueData.server_time)-Date.now();labs=catalogueData.items;queuePolicy=catalogueData.queue_policy||{enabled:false};
  if(!queuePolicy.enabled){queueState=null;queueUncertain=false;}
const current=$('session').value||savedSession();$('session').replaceChildren(new Option('Chọn ca',''));
  for(const s of labs){const r=rooms.find(r=>r.id===s.room_id);$('session').append(new Option(`${r?.name||s.room_id} · ${date(s.start_at)}`,s.id));}
  $('session').value=labs.some(s=>s.id===current)?current:'';rememberSession();
  window.dispatchEvent(new CustomEvent('labseat-catalogue',{detail:{labs,rooms,serverTime:catalogueData.server_time}}));await availability();
}
async function availability(){
  if(queueChanging)return;
  const revision=++availabilityRevision,id=$('session').value;
  if(mapSessionId!==id){mapSessionId=id;bookingLayoutCache=null;currentMap=null;selectedSeat=null;$('seats').replaceChildren();}
  $('map-empty').hidden=!!id;if(!id){renderQueue();}if(!id){$('session-info').textContent='';selectedSeat=null;activeRegistration=null;$('hold-panel').hidden=true;updateSummary();return;}
  const lab=labs.find(s=>s.id===id);if(me?.profile_complete===false&&lab?.session_type==='exam'){await openExamProfile(id);return;}$('session-info').textContent=`${eventTitle(lab)} · ${date(lab.start_at)} → ${date(lab.end_at)}`;
  let queueTickets=null;
  if(queuePolicy.enabled){
    queueTickets=me?await api('/me/tickets'):[];
    if(revision!==availabilityRevision||$('session').value!==id)return;
    activeRegistration=queueTickets.find(r=>r.session_id===id&&['HELD','CONFIRMED','CHECKED_IN'].includes(r.status))||null;
    if(!activeRegistration){
      $('hold-panel').hidden=true;
      if(queueSessionId!==id){queueState=null;queueSessionId=id;queueNextHeartbeat=0;queueUncertain=false;}
      if(queueCanRun()&&Date.now()>=queueNextHeartbeat&&!queueBusy)await refreshQueue('heartbeat',id);
      if(revision!==availabilityRevision||$('session').value!==id)return;
      const state=queueState?.status;
      if(queueCanRun()&&!queueBusy&&!queueUncertain&&queueOpen(lab)&&(['NONE','EXPIRED'].includes(state)||(state==='LEFT'&&queueNewSelection))){
        await refreshQueue('join',id);
      }
      if(revision!==availabilityRevision||$('session').value!==id)return;
      renderQueue();
      if(!queueReady()){
        selectedSeat=null;$('map-empty').hidden=false;$('map-empty').textContent=me?'Bạn cần có lượt vào còn hạn để chọn phòng.':'Đăng nhập và vào phòng chờ để chọn phòng.';
        updateSummary();return;
      }
    }
  }
  renderQueue();$('map-empty').textContent='Chọn ca để xem sơ đồ phòng.';
  const data=await api(`/lab-sessions/${id}/seats`);window.dispatchEvent(new CustomEvent('labseat-availability',{detail:{id,next_change_at:data.next_change_at}}));if(revision!==availabilityRevision||$('session').value!==id)return;offset=Date.parse(data.server_time)-Date.now();
  const mine=queueTickets||(me?await api('/me/tickets'):[]);if(revision!==availabilityRevision||$('session').value!==id)return;activeRegistration=mine.find(r=>r.session_id===id&&['HELD','CONFIRMED','CHECKED_IN'].includes(r.status))||null;if(activeRegistration?.status==='HELD'){mutationKeys.delete(`${me.id}:/holds:${JSON.stringify({session_id:id,seat_id:activeRegistration.seat_id})}`);held={hold_id:activeRegistration.reservation_id,seat_id:activeRegistration.seat_id,session_id:id,expires_at:activeRegistration.hold_expires_at};expires=Date.parse(held.expires_at);$('hold-panel').hidden=false;}else{$('hold-panel').hidden=true;if(held?.session_id===id)held=null;}
  let layout=bookingLayoutCache?.roomId===lab.room_id?bookingLayoutCache.layout:null;
  if(!layout||(data.layout_revision!==undefined&&layout.revision!==data.layout_revision)){
    layout=await api(`/rooms/${lab.room_id}/seat-map`);if(revision!==availabilityRevision||$('session').value!==id)return;
    bookingLayoutCache={roomId:lab.room_id,layout};
  }
  currentMap=layout;
  if(selectedSeat){const item=data.items.find(s=>s.id===selectedSeat.id&&s.available);if(!item||!layout.elements.some(r=>r.seat_id===selectedSeat.id))selectedSeat=null;else selectedSeat.seat_code=item.seat_code||selectedSeat.seat_code;}
  renderSeatMap($('seats'),layout,data,true);updateSummary();

}
async function tickets(){
  const items=await api('/me/tickets');const maps=await Promise.all([...new Set(items.filter(r=>!r.seat_code).map(r=>labs.find(l=>l.id===r.session_id)?.room_id).filter(Boolean))].map(async id=>[id,await api(`/rooms/${id}/seat-map`)]));const codes=new Map(maps.flatMap(([,map])=>map.elements.filter(e=>['seat','zone'].includes(e.kind)).map(e=>[e.seat_id,e.seat_code])));$('tickets').replaceChildren();
  let visibleTickets=0;
  for(const r of items){const c=document.createElement('article');c.className='card';const badge=line(c,({HELD:'Đang giữ',CONFIRMED:'Đã xác nhận',CHECKED_IN:'Đã Checkin',CANCELLED:'Đã hủy',EXPIRED:'Hết hạn'})[r.status]||r.status,'h3');badge.setAttribute('data-status',r.status);const lab=labs.find(l=>l.id===r.session_id);line(c,r.event_name||eventTitle(lab)).className='ticket-name';const start=r.start_at||lab?.start_at;if(start)line(c,date(start),'small');const place=r.seat_code||codes.get(r.seat_id)||currentMap?.elements.find(e=>e.seat_id===r.seat_id)?.seat_code;if(place)line(c,`Vị trí: ${place}`,'small');
    if(r.ticket_code){const i=document.createElement('img');i.src=`/me/tickets/${r.reservation_id}/qr`;i.alt='QR đăng kí';c.append(i);}
    if(['CONFIRMED','CHECKED_IN'].includes(r.status))c.append(button('Gửi lại email vé',async()=>{await api(`/me/tickets/${r.reservation_id}/email-resends`,'POST');notice('Đã xếp hàng gửi lại email vé.');}));
    if(['CONFIRMED','CHECKED_IN'].includes(r.status))c.append(button('Trạng thái email',async()=>{const jobs=await api(`/me/tickets/${r.reservation_id}/emails`);const labels={PENDING:'Đang chờ',SENDING:'Đang gửi',ACCEPTED:'Đã được tiếp nhận',DELIVERED:'Đã giao thư',SKIPPED:'Không gửi',UNKNOWN:'Cần đối chiếu kết quả',HARD_BOUNCE:'Địa chỉ bị từ chối',BLOCKED:'Bị chặn',COMPLAINT:'Có phản ánh spam',SOFT_BOUNCE:'Tạm thời chưa giao được',DEFERRED:'Tạm hoãn',FAILED:'Gửi lỗi'};c.querySelector('[data-email-status]')?.remove();const status=line(c,jobs.length?jobs.map(j=>`${date(j.created_at)} · ${labels[j.status]||'Đang cập nhật'}`).join(' | '):'Chưa có yêu cầu gửi email.');status.dataset.emailStatus='';status.setAttribute('role','status');}));
    if(r.status==='HELD'){c.append(button('Xác nhận đăng kí',async()=>{await api(`/holds/${r.reservation_id}/confirm`,'POST');if(held?.hold_id===r.reservation_id){held=null;$('hold-panel').hidden=true;}notice('Đã xác nhận đăng kí');await tickets();await availability();}));}
    if(r.status==='HELD'||(r.status==='CONFIRMED'&&lab&&Date.now()+offset<Date.parse(lab.start_at)))c.append(button('Hủy',async()=>{await api(`/reservations/${r.reservation_id}/cancel`,'POST');if(held?.hold_id===r.reservation_id){held=null;$('hold-panel').hidden=true;}await tickets();await availability();}));
    c.hidden=!!$('ticket-filter')?.value&&!c.textContent.toLowerCase().includes($('ticket-filter').value.toLowerCase());if(!c.hidden)visibleTickets++;$('tickets').append(c);
  }
  $('tickets-empty').hidden=visibleTickets>0;
}
$('login').onsubmit=action(async()=>{await api('/auth/login','POST',values($('login')));$('login').reset();await identity();await catalogue();notice('Đã đăng nhập');});
$('register').onsubmit=action(async()=>{
  if($('register-submit').disabled)return;
  const form=$('register'),data=values(form);
  if(data.password!==data.password_confirm)throw Error('Mật khẩu chưa khớp.');
  $('register-submit').disabled=true;
  try{
    await api('/auth/register','POST',data);
    form.reset();await identity();await catalogue();notice('Đã tạo tài khoản.');
  }finally{$('register-submit').disabled=false;}
});
async function loadProfile(){
  const revision=++profileRevision;
  const fields=['full_name','cccd','phone','email'];
  for(const key of fields)$('profile-form').elements[key].disabled=true;
  $('profile-save').disabled=true;
  try{
    const data=await api('/me/profile');if(revision!==profileRevision||!me)return;me.email_verified=data.email_verified;window.dispatchEvent(new CustomEvent('labseat-profile',{detail:data}));
    me.full_name=data.full_name;me.avatar_url=data.avatar_url;renderAccount();
    for(const key of fields)$('profile-form').elements[key].value=data[key]||'';
    for(const key of ['full_name','cccd'])$('profile-form').elements[key].required=!!pendingProfileSession;
    $('profile-form').elements.email.required=true;$('profile-form').elements.phone.required=false;
    $('profile-status').textContent=data.profile_complete?'Đã đủ thông tin':'Cần bổ sung thông tin';
    $('profile-status').dataset.complete=String(data.profile_complete);
  }finally{
    if(revision===profileRevision){for(const key of fields)$('profile-form').elements[key].disabled=false;$('profile-save').disabled=false;}
  }
}
async function openExamProfile(id){
  await exitQueue();pendingProfileSession=id;location.hash='#profile-panel';
  notice(me?.email_verified===false?'Lưu hồ sơ và xác minh email trước khi đăng kí.':'Bổ sung họ tên, CCCD và email để đăng kí ca thi.');
}
async function startRegistration(id,type){
  if(me?.email_verified===false||(me?.profile_complete===false&&type==='exam')){await openExamProfile(id);return;}
  pendingProfileSession=null;$('session').value=id;await $('session').onchange();
}
window.addEventListener('labseat-profile-required',event=>action(async()=>openExamProfile(event.detail.sessionId))());
window.addEventListener('labseat-screen',event=>{if(event.detail==='profile-panel'&&me)action(loadProfile)();else if(event.detail!=='profile-panel')pendingProfileSession=null;});
$('profile-form').onsubmit=action(async()=>{
  if($('profile-save').disabled)return;$('profile-save').disabled=true;$('profile-message').textContent='';
  const owner=me?.id,revision=profileRevision;
  try{
    const data=await api('/me/profile','PUT',values($('profile-form')));
    if(owner!==me?.id||revision!==profileRevision)return;
    me.email_verified=data.email_verified;window.dispatchEvent(new CustomEvent('labseat-profile',{detail:data}));$('profile-form').elements.current_password.value='';
    me.profile_complete=data.profile_complete;me.full_name=data.full_name;me.avatar_url=data.avatar_url;renderAccount();
    $('profile-status').textContent=data.profile_complete?'Đã đủ thông tin':'Cần bổ sung thông tin';$('profile-status').dataset.complete=String(data.profile_complete);
    for(const key of ['full_name','cccd','phone','email'])$('profile-form').elements[key].value=data[key]||'';
    $('profile-message').textContent='Đã lưu hồ sơ.';
    if(pendingProfileSession&&data.profile_complete&&data.email_verified){const id=pendingProfileSession;pendingProfileSession=null;location.hash='#booking';await startRegistration(id,'exam');}
  }catch(error){$('profile-message').textContent=error.message;throw error;}
  finally{$('profile-save').disabled=false;}
});
let avatarBusy=false;
async function changeAvatar(removing=false){
  if(avatarBusy||!me)return;
  const file=$('avatar-file').files[0];if(!removing&&!file)return;
  if(file&&!removing&&(file.size>5*1024*1024||!['image/jpeg','image/png','image/webp'].includes(file.type))){$('avatar-file').value='';$('avatar-message').dataset.state='error';$('avatar-message').textContent='Chọn JPEG/PNG/WebP tối đa 5 MB.';throw Error($('avatar-message').textContent);}
  avatarBusy=true;$('avatar-file').disabled=true;$('avatar-remove').disabled=true;$('avatar-message').textContent='Đang lưu ảnh…';$('avatar-message').dataset.state='loading';
  const owner=me.id,revision=profileRevision;
  try{
    const body=new FormData();if(!removing)body.append('file',file);
    const data=await api('/me/avatar',removing?'DELETE':'POST',removing?null:body);
    if(owner!==me?.id||revision!==profileRevision)return;
    me.avatar_url=data.avatar_url;renderAccount();$('avatar-message').dataset.state='success';$('avatar-message').textContent=removing?'Đã xóa ảnh.':'Đã lưu ảnh đại diện.';
  }catch(error){$('avatar-message').dataset.state='error';$('avatar-message').textContent=error.message;throw error;}
  finally{avatarBusy=false;$('avatar-file').disabled=false;$('avatar-file').value='';$('avatar-remove').disabled=false;}
}
$('avatar-form').onsubmit=action(async()=>changeAvatar());
$('avatar-file').onchange=action(async()=>changeAvatar());
$('avatar-remove').onclick=action(async()=>changeAvatar(true));
$('logout').onclick=action(async()=>{profileRevision++;pendingProfileSession=null;clearCheckin();$('checkin-form').reset();$('avatar-message').textContent='';$('avatar-file').value='';$('profile-form').reset();$('profile-message').textContent='';await exitQueue();await api('/auth/logout','POST');held=null;$('hold-panel').hidden=true;stopCamera();await identity();await availability();});
$('session').onchange=action(selectSession);
$('confirm').onclick=action(async()=>{if(!held)return;await api(`/holds/${held.hold_id}/confirm`,'POST');held=null;$('hold-panel').hidden=true;notice('Đã đăng kí');await tickets();await availability();});
$('cancel-hold').onclick=action(async()=>{if(!held)return;await api(`/reservations/${held.hold_id}/cancel`,'POST');held=null;$('hold-panel').hidden=true;await tickets();await availability();});
function clearCheckin(){
  checkinRevision++;clearTimeout(checkinLookupTimer);checkinReceipt=null;
  $('checkin-result').hidden=true;$('checkin-confirm').hidden=true;
  $('checkin-ticket-info').replaceChildren();$('checkin-profile-info').replaceChildren();
  $('checkin-avatar').src='/static/user-default.svg';$('checkin-decision').textContent='';
}
function checkinRows(container,rows){
  container.replaceChildren();for(const [label,value] of rows){line(container,label,'dt');line(container,value||'Chưa cung cấp','dd');}
}
function renderCheckin(){
  const data=checkinReceipt;if(!data){$('checkin-result').hidden=true;$('checkin-confirm').hidden=true;return;}
  const {ticket,session,profile}=data;
  const labels={HELD:'Đang giữ',CONFIRMED:'Đã xác nhận',CHECKED_IN:'Đã check-in',CANCELLED:'Đã huỷ',EXPIRED:'Hết hạn'};
  checkinRows($('checkin-ticket-info'),[['Mã đăng kí',ticket.reservation_id],['Ca',session.name],['Phòng',`${session.seat_code} · ${session.room_name}`],['Thời gian',`${date(session.start_at)} → ${date(session.end_at)}`],['Trạng thái vé',labels[ticket.status]||ticket.status],['Check-in của ca',session.checkin_enabled?'Đang mở':'Đang đóng'],['Đã check-in lúc',ticket.checked_in_at?date(ticket.checked_in_at):'Chưa check-in']]);
  checkinRows($('checkin-profile-info'),[['Họ tên',profile.full_name],['Tài khoản',profile.username],['CCCD',profile.cccd],['Email',profile.email],['Số điện thoại',profile.phone||'Không cung cấp']]);
  const avatar=$('checkin-avatar');avatar.src=profile.avatar_url||'/static/user-default.svg';avatar.onerror=()=>{avatar.onerror=null;avatar.src='/static/user-default.svg';};
  $('checkin-decision').textContent=data.reason;$('checkin-decision').dataset.allowed=String(data.can_check_in===true);
  $('checkin-confirm').hidden=data.can_check_in!==true;$('checkin-confirm').disabled=checkinBusy;
  $('checkin-result').hidden=false;
}
async function lookupCheckin(){
  clearCheckin();const revision=checkinRevision,code=$('checkin-form').elements.ticket_code.value.trim();
  if(code.length<20||code.length>100){cameraStatus('Nhập đúng mã vé hoặc mã đăng kí để tra cứu.');return;}
  cameraStatus('Đang tra cứu vé…');
  try{
    const data=await api(me?.role==='staff'?'/staff/check-ins/lookup':'/admin/check-ins/lookup','POST',{ticket_code:code});
    if(revision!==checkinRevision||code!==$('checkin-form').elements.ticket_code.value.trim())return;
    if(!data?.ticket||!data?.session||!data?.profile)throw Error('Chưa đọc được thông tin vé. Hãy tra cứu lại.');
    if(me?.role==='staff'&&$('staff-session').value!==data.session.id)throw Error('Vé không thuộc ca đang chọn.');
    checkinReceipt=data;renderCheckin();cameraStatus('');
    window.dispatchEvent(new CustomEvent('labseat-checkin-preview',{detail:data.session}));
  }catch(error){if(revision===checkinRevision){clearCheckin();cameraStatus(error.message);notice(error.message);}}
}
$('checkin-form').onsubmit=action(lookupCheckin);
$('checkin-form').elements.ticket_code.oninput=()=>{
  clearCheckin();const code=$('checkin-form').elements.ticket_code.value.trim();cameraStatus('Nhập hoặc quét mã vé để tra cứu thông tin.');
  if(code.length>=20&&code.length<=100)checkinLookupTimer=setTimeout(()=>lookupCheckin(),450);
};
$('checkin-confirm').onclick=action(async()=>{
  if(checkinBusy||checkinReceipt?.can_check_in!==true)return;
  const revision=checkinRevision,code=$('checkin-form').elements.ticket_code.value.trim(),ticketCode=checkinReceipt.ticket.ticket_code;
  checkinBusy=true;renderCheckin();
  try{
    await api(me?.role==='staff'?'/staff/check-ins':'/admin/check-ins','POST',{ticket_code:ticketCode});
    if(revision!==checkinRevision||code!==$('checkin-form').elements.ticket_code.value.trim())return;
    await lookupCheckin();if(code===$('checkin-form').elements.ticket_code.value.trim()&&checkinReceipt?.ticket.ticket_code===ticketCode)notice('Đã xác nhận check-in.');
  }catch(error){if(revision===checkinRevision){await lookupCheckin();if(code===$('checkin-form').elements.ticket_code.value.trim())notice(error.message);}}
  finally{checkinBusy=false;renderCheckin();}
});
window.addEventListener('labseat-checkin-policy',event=>{if(checkinReceipt?.session.id===event.detail.sessionId)lookupCheckin();});
window.addEventListener('labseat-identity',event=>{if(!['admin','staff'].includes(event.detail?.role))clearCheckin();});
$('csv').onclick=action(async()=>{const id=$('registration-session').value;if(!id)throw Error('Chọn ca trước');const blob=await api(`/admin/lab-sessions/${id}/registrations.csv`),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='registrations.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
function cameraStatus(message){for(const id of ['camera-status','qr-status'])if($(id).textContent!==message)$(id).textContent=message;}
function openQRDialog(){
  const dialog=$('qr-dialog');dialog.hidden=false;if(!dialog.open)dialog.showModal();
}
function stopCamera(options={}){
  const active=!!cameraStream||cameraStarting;cameraRevision++;cameraStarting=false;clearTimeout(scanTimer);
  cameraStream?.getTracks().forEach(t=>t.stop());cameraStream=null;
  $('preview').srcObject=null;$('preview').hidden=true;$('camera').disabled=false;$('stop-camera').disabled=false;
  $('qr-stage').dataset.scanning='false';$('qr-placeholder').hidden=false;$('qr-retry').hidden=true;
  if(active)cameraStatus('Trình quét QR đã đóng.');
  if(options.keepDialog!==true){const dialog=$('qr-dialog');if(dialog.open)dialog.close();dialog.hidden=true;}
}
$('qr-dialog').oncancel=event=>{event.preventDefault();stopCamera();};
$('qr-dialog').onclick=event=>{
  if(event.target!==$('qr-dialog'))return;
  const box=$('qr-dialog').getBoundingClientRect();
  if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)stopCamera();
};
$('qr-dialog').onclose=()=>{if(!$('qr-dialog').open&&(cameraStream||cameraStarting))stopCamera();};
function cameraError(error){
  if(error.name==='NotAllowedError'||error.name==='PermissionDeniedError')return 'Chưa được cấp quyền camera. Hãy cho phép camera trong cài đặt trang web rồi thử lại, hoặc chọn ảnh QR.';
  if(error.name==='NotFoundError'||error.name==='DevicesNotFoundError')return 'Không tìm thấy camera. Bạn có thể chọn ảnh QR hoặc nhập mã vé.';
  if(error.name==='NotReadableError'||error.name==='TrackStartError')return 'Camera đang được ứng dụng khác sử dụng hoặc không thể mở. Hãy đóng ứng dụng đó rồi thử lại.';
  if(error.name==='OverconstrainedError')return 'Camera không đáp ứng cấu hình. Hãy thử camera khác hoặc chọn ảnh QR.';
  return 'Không mở được camera. Hãy thử lại, chọn ảnh QR hoặc nhập mã vé.';
}
async function qrDecoder(){
  let detector=null,canvas=null,context=null,windowCanvas=null;
  if(window.BarcodeDetector){try{
    const formats=window.BarcodeDetector.getSupportedFormats?await window.BarcodeDetector.getSupportedFormats():['qr_code'];
    if(formats.includes('qr_code'))detector=new window.BarcodeDetector({formats:['qr_code']});
  }catch{/* Native detection is optional; jsQR is hosted with this application. */}}
  return async (source,{cameraWindow=false}={})=>{
    let width=source.videoWidth??source.naturalWidth??source.width,height=source.videoHeight??source.naturalHeight??source.height;
    if(!width||!height)return null; // Wait for a real frame instead of stopping during video startup.
    if(cameraWindow){
      // Match object-fit:cover in the square preview, then the centred 76% guide.
      const side=Math.min(width,height)*.76;
      if(!windowCanvas)windowCanvas=document.createElement('canvas');
      windowCanvas.width=Math.max(1,Math.round(side));windowCanvas.height=windowCanvas.width;
      const windowContext=windowCanvas.getContext('2d',{willReadFrequently:true});
      if(!windowContext)throw Error('Trình duyệt không hỗ trợ đọc QR. Hãy chọn ảnh hoặc nhập mã vé.');
      windowContext.drawImage(source,(width-side)/2,(height-side)/2,side,side,0,0,windowCanvas.width,windowCanvas.height);
      source=windowCanvas;width=source.width;height=source.height;
    }
    if(detector){try{const codes=await detector.detect(source);return codes[0]?.rawValue||null;}catch{detector=null;}}
    if(typeof window.jsQR!=='function')throw Error('Không tải được bộ đọc QR. Hãy tải lại trang hoặc nhập mã vé.');
    if(!canvas){canvas=document.createElement('canvas');context=canvas.getContext('2d',{willReadFrequently:true});}
    if(!context)throw Error('Trình duyệt không hỗ trợ đọc ảnh QR. Hãy nhập mã vé.');
    const scale=Math.min(1,960/Math.max(width,height));canvas.width=Math.max(1,Math.round(width*scale));canvas.height=Math.max(1,Math.round(height*scale));
    context.drawImage(source,0,0,canvas.width,canvas.height);
    const pixels=context.getImageData(0,0,canvas.width,canvas.height);
    return window.jsQR(pixels.data,pixels.width,pixels.height,{inversionAttempts:'attemptBoth'})?.data||null;
  };
}
function acceptScannedTicket(value){
  const code=String(value).trim();
  if(!/^[A-Za-z0-9_-]{20,100}$/.test(code)){cameraStatus('Mã QR này không phải mã vé LABSEAT. Hãy thử lại với QR trên vé.');return false;}
  $('checkin-form').elements.ticket_code.value=code;stopCamera();
  cameraStatus('Đã đọc mã vé. Đang tra cứu thông tin…');lookupCheckin();return true;
}
$('stop-camera').onclick=stopCamera;
const startQRScanner=action(async()=>{
  stopCamera({keepDialog:true});openQRDialog();
  if(window.isSecureContext===false){const message='Camera trực tiếp cần HTTPS hoặc localhost. Hãy mở trang bằng HTTPS, chọn ảnh QR hoặc nhập mã vé.';cameraStatus(message);throw Error(message);}
  if(!navigator.mediaDevices?.getUserMedia){const message='Trình duyệt không hỗ trợ camera tại địa chỉ này. Hãy dùng HTTPS/localhost, chọn ảnh QR hoặc nhập mã vé.';cameraStatus(message);throw Error(message);}
  const revision=cameraRevision;cameraStarting=true;$('camera').disabled=true;$('stop-camera').disabled=false;cameraStatus('Đang chờ quyền truy cập camera…');
  try{
    let stream;
    try{stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1280},height:{ideal:720}},audio:false});}
    catch(error){if(revision!==cameraRevision)return;if(error.name!=='OverconstrainedError')throw error;stream=await navigator.mediaDevices.getUserMedia({video:true,audio:false});}
    if(revision!==cameraRevision){stream.getTracks().forEach(t=>t.stop());return;}
    cameraStream=stream;cameraStarting=false;$('preview').hidden=false;$('preview').srcObject=stream;await $('preview').play();
    if(revision!==cameraRevision)return;
    const decode=await qrDecoder();if(revision!==cameraRevision)return;
    $('qr-stage').dataset.scanning='true';$('qr-placeholder').hidden=true;
    cameraStatus('Giữ mã QR trong khung để quét.');
    const scan=async()=>{
      if(!cameraStream||revision!==cameraRevision)return;
      try{const code=await decode($('preview'),{cameraWindow:true});if(revision!==cameraRevision)return;if(code&&acceptScannedTicket(code))return;}
      catch(error){if(revision!==cameraRevision)return;stopCamera({keepDialog:true});$('qr-retry').hidden=false;cameraStatus(error.message);notice(error.message);return;}
      scanTimer=setTimeout(scan,300);
    };
    await scan();
  }catch(error){if(revision!==cameraRevision)return;stopCamera({keepDialog:true});$('qr-retry').hidden=false;const message=cameraError(error);cameraStatus(message);throw Error(message);}
});
$('camera').onclick=startQRScanner;
$('qr-retry').onclick=startQRScanner;
$('camera-image').onchange=action(async()=>{
  stopCamera({keepDialog:true});openQRDialog();const revision=cameraRevision,file=$('camera-image').files?.[0];$('camera-image').value='';if(!file)return;
  if(!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>5*1024*1024){const message='Chọn ảnh QR JPEG, PNG hoặc WebP tối đa 5 MB.';cameraStatus(message);throw Error(message);}
  cameraStatus('Đang đọc ảnh QR…');const url=URL.createObjectURL(file);
  try{
    const image=new Image();await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(Error('Không mở được ảnh. Hãy chọn ảnh QR khác.'));image.src=url;});
    if(revision!==cameraRevision)return;
    if(image.naturalWidth*image.naturalHeight>20000000)throw Error('Ảnh quá lớn. Hãy chọn ảnh QR dưới 20 megapixel.');
    const decode=await qrDecoder(),code=await decode(image);if(revision!==cameraRevision)return;
    if(!code)throw Error('Không tìm thấy QR trong ảnh. Hãy chụp rõ toàn bộ mã QR rồi thử lại.');
    acceptScannedTicket(code);
  }catch(error){if(revision===cameraRevision){cameraStatus(error.message);throw error;}}
  finally{URL.revokeObjectURL(url);}
});
window.addEventListener('pagehide',stopCamera);
setInterval(()=>{if(held){const left=Math.max(0,Math.ceil((expires-Date.now()-offset)/1000));$('countdown').textContent=`Còn ${left} giây`;$('confirm').disabled=left===0||holdBusy;}},250);
async function pollAvailability(){
  if(availabilityPolling||holdBusy)return;availabilityPolling=true;
  try{await availability();}catch(error){notice(error.message);}finally{availabilityPolling=false;}
}
setInterval(()=>{if(!document.hidden&&!$('booking').hidden&&(!window.labseatStreamHealthy||Date.now()-(window.labseatSnapshotAt||0)>30000))pollAvailability();},5000);


function updateSummary(){$('confirm').disabled=holdBusy||!held||Date.now()+offset>=expires;const lab=labs.find(s=>s.id===$('session').value);$('seat-summary').textContent=selectedSeat?`${eventTitle(lab)} · ${lab?date(lab.start_at):''} · ${selectedSeat.seat_code}`:'Chọn phòng để xem trước';$('hold-selected').disabled=holdBusy||!selectedSeat||!me||!!activeRegistration||(queuePolicy.enabled&&!queueReady());$('seats').inert=queuePolicy.enabled&&!activeRegistration&&!queueReady();$('hold-selected').textContent=activeRegistration?'Bạn đã có đăng kí ca này':'Giữ suất tối đa 3 phút';}
function renderSeatMap(container,layout,availability,interactive){
  if(layout.type==='image'){renderImageMap(container,layout,availability,interactive);return;}
  const gridKey=JSON.stringify([layout,availability?.items,interactive,selectedSeat?.id,held?.seat_id,held?.session_id,$('session').value]);
  if(container._gridMapKey===gridKey&&container.children.length)return;container._gridMapKey=gridKey;
  container.replaceChildren();container.style.position='relative';container.style.width=layout.columns*48+'px';container.style.height=layout.rows*48+'px';
  for(const e of layout.elements){const seat=availability?.items.find(s=>s.id===e.seat_id),own=held?.seat_id===e.seat_id&&held?.session_id===$('session').value;const node=document.createElement(e.kind==='seat'?'button':'div');node.className='map-item '+e.kind+(own?' own-hold':selectedSeat?.id===e.seat_id?' picked':'');Object.assign(node.style,{left:e.x*48+'px',top:e.y*48+'px',width:e.width*48-4+'px',height:e.height*48-4+'px'});node.textContent=e.kind==='seat'?e.seat_code:e.label||e.kind;
    if(e.kind==='seat'){node.type='button';node.disabled=!interactive||!seat?.available;node.setAttribute('aria-label',`${e.seat_code}: ${own?'Bạn đang giữ':selectedSeat?.id===e.seat_id?'Đang chọn':seat?.available?'Trống':'Không khả dụng'}`);node.setAttribute('aria-pressed',String(selectedSeat?.id===e.seat_id));node.onclick=()=>{selectedSeat={id:e.seat_id,seat_code:e.seat_code};renderSeatMap(container,layout,availability,interactive);updateSummary();};}
    container.append(node);
  }
}
$('hold-selected').onclick=action(async()=>{
  if(holdBusy||!selectedSeat||activeRegistration||(queuePolicy.enabled&&!queueReady()))return;
  holdBusy=true;updateSummary();
  try{
    const sid=$('session').value,seat=selectedSeat;let result;
    try{result=await api('/holds','POST',{session_id:sid,seat_id:seat.id});}
    catch(error){if(['queue_waiting','queue_expired','queue_unavailable'].includes(error.code)){selectedSeat=null;await catalogue();}throw error;}
    queueState=null;queueNextHeartbeat=0;held={...result,seat_id:seat.id,session_id:sid};expires=Date.parse(held.expires_at);offset=Date.parse(held.server_time)-Date.now();$('hold-panel').hidden=false;notice(`Đã giữ một suất tại ${seat.seat_code}`);await tickets();await availability();
  }finally{holdBusy=false;updateSummary();}
});
$('ticket-filter').oninput=action(tickets);
function parseCSV(text){const rows=[];let row=[],field='',quoted=false;for(let i=0;i<text.length;i++){const c=text[i];if(c==='"'){if(quoted&&text[i+1]==='"'){field+='"';i++;}else quoted=!quoted;}else if(c===','&&!quoted){row.push(field);field='';}else if(c==='\n'&&!quoted){row.push(field.replace(/\r$/,''));rows.push(row);row=[];field='';}else field+=c;}if(field||row.length){row.push(field);rows.push(row);}if(rows.length)rows[0][0]=rows[0][0].replace(/^\uFEFF/,'');return rows;}
function registrations(){const term=$('registration-filter').value.toLowerCase(),box=$('registration-table');box.replaceChildren();const filtered=registrationRows.slice(1).filter(r=>r.join(' ').toLowerCase().includes(term));const table=document.createElement('table');for(const [index,row] of [registrationRows[0]||[],...filtered].entries()){const tr=document.createElement('tr');for(const [columnIndex,value] of row.entries()){const cell=document.createElement(index?'td':'th'),column=(registrationRows[0]||[])[columnIndex];
      cell.textContent=index?value:({reservation_id:'Mã đăng kí',username:'Người đăng kí',seat_code:'Phòng',status:'Trạng thái',checked_in_at:'Giờ Checkin (VN)'})[value]||value;
      if(index&&column==='status')cell.textContent=({HELD:'Đang giữ',CONFIRMED:'Đã xác nhận',CHECKED_IN:'Đã Checkin',CANCELLED:'Đã hủy',EXPIRED:'Hết hạn'})[value]||value;
      if(index&&column==='checked_in_at')cell.textContent=value?date(value.replace(' ','T')):'—';
      tr.append(cell);}table.append(tr);}box.append(table);const checked=registrationRows.slice(1).filter(r=>r[3]==='CHECKED_IN').length;$('registration-stats').textContent=`${registrationRows.length?registrationRows.length-1:0} đăng kí · ${checked} đã Checkin`;}
$('load-registrations').onclick=action(async()=>{
  const id=$('registration-session').value,revision=++registrationRevision;
  if(!id)throw Error('Chọn ca trước');
  const blob=await api(`/admin/lab-sessions/${id}/registrations.csv`),text=await blob.text();
  if(revision!==registrationRevision||$('registration-session').value!==id)return;
  registrationRows=parseCSV(text);registrations();
});
$('registration-session').onchange=action(async()=>{
  registrationRevision++;registrationRows=[];registrations();
  if($('registration-session').value)await $('load-registrations').onclick();
});
$('registration-filter').oninput=registrations;

window.addEventListener('DOMContentLoaded',()=>action(async()=>{await identity();await catalogue();if(me)await tickets();})());


function queueReady(){
  return !queueUncertain&&queueState?.session_id===$('session').value&&queueState?.status==='ADMITTED'&&Date.parse(queueState.admission_expires_at)>Date.now()+queueOffset;
}
function queueCanRun(){return !holdBusy&&!!me&&!document.hidden&&!$('booking').hidden&&!queueChanging&&!!$('session').value;}
function queueOpen(lab){return lab&&Date.parse(lab.open_at)<=Date.now()+offset&&Date.now()+offset<Date.parse(lab.close_at);}
// Serialize mutations, including a leave after a join whose response was invalidated.
function queueTransport(operation,id){
  const request=queueFlight.then(()=>api(`/lab-sessions/${id}/queue/${operation}`,'POST',{}));
  queueFlight=request.catch(()=>{});return request;
}
async function selectSession(){
  const id=$('session').value,old=queueSessionId,revision=++queueRevision;
  queueChanging++;availabilityRevision++;queueState=null;queueUpdatedAt=null;queueSessionId=id;queueNewSelection=true;queueUncertain=false;queueNextHeartbeat=0;selectedSeat=null;activeRegistration=null;
  rememberSession();renderQueue();updateSummary();
  try{
    if(queuePolicy.enabled&&me&&old&&old!==id)await queueTransport('leave',old);
  }catch(error){
    if(revision===queueRevision){$('session').value='';queueSessionId=null;rememberSession();}
    notice('Chưa rời được hàng chờ. Hãy thử lại.');
    return;
  }finally{queueChanging--;renderQueue();}
  if(revision!==queueRevision)return;
  if(queuePolicy.enabled&&id&&!me&&queueOpen(labs.find(lab=>lab.id===id))){
    window.dispatchEvent(new CustomEvent('labseat-login-request',{detail:{opener:$('login-link'),returnToBooking:true}}));
  }
  await availability();
}
async function exitQueue(){
  const old=queueSessionId||$('session').value;
  queueRevision++;availabilityRevision++;queueChanging++;$('session').value='';queueSessionId=null;queueState=null;queueUpdatedAt=null;queueNewSelection=false;queueUncertain=false;selectedSeat=null;activeRegistration=null;
  $('hold-panel').hidden=true;rememberSession();renderQueue();updateSummary();
  try{if(queuePolicy.enabled&&me&&old)await queueTransport('leave',old);}
  finally{queueChanging--;renderQueue();}
}
async function refreshQueue(operation,id=$('session').value){
  if(!id||!me||queueBusy)return;
  const revision=queueRevision;queueBusy=true;renderQueue();
  try{
    const data=await queueTransport(operation,id);
    if(revision!==queueRevision||$('session').value!==id)return;
    queueState=data;queueSessionId=id;queueOffset=Date.parse(data.server_time)-Date.now();queueUpdatedAt=data.server_time;queueUncertain=false;
    queueNextHeartbeat=Date.now()+(data.heartbeat_after_seconds||5)*1000;
    if(operation==='join'||['WAITING','ADMITTED'].includes(data.status))queueNewSelection=false;
    if(data.status==='DISABLED'){queuePolicy={enabled:false};queueState=null;}
  }catch(error){
    if(revision!==queueRevision||$('session').value!==id)return;
    queueUncertain=true;queueNextHeartbeat=Date.now()+5000;
    if(error.code==='registration_closed'){queueState={session_id:id,status:'CLOSED'};queueUncertain=false;}
    if(error.code==='active_registration'){await tickets();}
    notice(error.message);
  }finally{queueBusy=false;renderQueue();updateSummary();}
}
function renderQueue(){
  const id=$('session').value,lab=labs.find(s=>s.id===id),gated=queuePolicy.enabled&&!!id&&!activeRegistration;
  const admitted=gated&&queueReady(),visible=gated&&!admitted;
  const wasHidden=$('queue-panel').hidden;
  $('queue-panel').hidden=!visible;$('booking-catalogue').hidden=gated||!!id;$('booking-map').hidden=visible||!id;$('admission-banner').hidden=!admitted;
  if(admitted){
    $('admission-session').textContent=`${eventTitle(lab)} · ${lab?date(lab.start_at):''}`;
    const left=Math.max(0,Math.ceil((Date.parse(queueState.admission_expires_at)-Date.now()-queueOffset)/1000));
    $('queue-deadline').textContent=`Còn ${left} giây để chọn và giữ phòng`;
    if(!wasHidden&&!$('booking').hidden)$('map-title').focus?.({preventScroll:true});
  }
  if(!visible)return;
  const state=queueState?.status||'NONE',open=queueOpen(lab);
  const messages={NONE:'Đang đưa bạn vào hàng chờ…',WAITING:'Đến lượt sẽ tự vào chọn đăng kí.',ADMITTED:'Đang xếp lại lượt…',EXPIRED:'Đang xếp lại lượt…',LEFT:'Bạn đã rời hàng chờ.',CONSUMED:'Đã dùng lượt. Xem Ca đã đăng kí.',CLOSED:'Chưa mở hoặc đã đóng đăng kí.'};
  const message=!open?messages.CLOSED:!me?'Đăng nhập để vào hàng chờ.':queueUncertain?'Đang kết nối lại…':messages[state]||'Đang khôi phục lượt của bạn…';
  if($('queue-status').textContent!==message)$('queue-status').textContent=message;
  $('queue-title').textContent=!open?'Chưa thể đăng kí ca':queueUncertain?'Đang kết nối lại':state==='WAITING'?'Bạn đang trong hàng chờ':'Đang chuẩn bị lượt của bạn';
  $('queue-room').textContent=eventTitle(lab);
  $('queue-session-time').textContent=lab?`${date(lab.start_at)} → ${date(lab.end_at)}`:'';
  $('queue-count').hidden=state!=='WAITING'||queueUncertain;
  $('queue-position').textContent=state==='WAITING'&&!queueUncertain?new Intl.NumberFormat('vi-VN').format(queueState.number_ahead??0):'—';
  const seconds=queuePolicy.selection_seconds||120,windowLabel=seconds%60===0?`${seconds/60} phút`:`${seconds} giây`;
  $('queue-policy-help').textContent=`Bạn có ${windowLabel} để chọn phòng khi đến lượt.`;
  $('queue-updated').textContent=queueUpdatedAt?`Cập nhật lần cuối: ${new Date(queueUpdatedAt).toLocaleTimeString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'})}`:'Đang kết nối an toàn với phòng chờ…';
  $('queue-panel').dataset.uncertain=String(queueUncertain);
  $('check-queue').hidden=!queueUncertain;$('check-queue').disabled=queueBusy||!me||!!queueChanging;
  if(wasHidden&&!$('booking').hidden){$('queue-title').focus?.({preventScroll:true});}
}
$('check-queue').onclick=action(async()=>{queueNextHeartbeat=0;await availability();});
$('back-to-events').onclick=$('leave-queue').onclick=$('leave-admission').onclick=action(async()=>{await exitQueue();notice('Bạn đã trở lại danh sách ca.');await availability();window.dispatchEvent(new CustomEvent('labseat-home')); });
window.addEventListener('labseat-screen',event=>{
  if(event.detail!=='booking'&&queuePolicy.enabled&&$('session').value){exitQueue().catch(()=>notice('Chưa rời được hàng chờ.'));}
});
setInterval(()=>{if(queuePolicy.enabled){renderQueue();updateSummary();}},250);
setInterval(()=>{
  if(queuePolicy.enabled&&queueCanRun()&&!activeRegistration&&!queueBusy&&Date.now()>=queueNextHeartbeat){
    pollAvailability();
  }
},500);

function savedSession(){
  try{return new URL(location.href).searchParams.get('session')||'';}catch{return '';}
}
function rememberSession(){
  try{
    const url=new URL(location.href),id=$('session').value;
    if(id)url.searchParams.set('session',id);else url.searchParams.delete('session');
    history.replaceState(null,'',url.pathname+url.search+url.hash);
  }catch{ /* Navigation still works where History API is unavailable. */ }
}
