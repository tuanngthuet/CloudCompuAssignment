'use strict';
// Ca catalogue and authoring. Uses the shared session catalogue for booking.
(() => {
  const el=id=>document.getElementById(id),form=el('event-form');
  let events=[],sessions=[],type='exam',offset=0,revision=0,previewURL=null,originalTimes=null,posterCheck=Promise.resolve(true);
  const keys=['open_at','close_at','start_at','end_at'];
  const label=e=>`${e.session_type==='exam'?'Ca thi':'Ca thực hành'} · ${e.name}`;
  const schedule=e=>e.schedule||sessions.find(s=>s.event_id===e.id);
  const text=(tag,value)=>{const n=document.createElement(tag);n.textContent=value;return n;};
  const display=v=>new Date(v).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',dateStyle:'short',timeStyle:'short'});
  function state(e,now=Date.now()+offset){const s=schedule(e);return !s?'closed':now<Date.parse(s.open_at)?'soon':now<Date.parse(s.close_at)?'open':'closed';}
  function details(e){
    el('event-detail').hidden=false;el('event-detail-title').textContent=label(e);el('event-detail-description').textContent=e.description;
    el('event-detail-location').textContent=[e.venue,e.address].filter(Boolean).join(' · ');
    const box=el('event-session-list'),s=schedule(e);box.replaceChildren();
    if(s){
      box.append(text('p',`Diễn ra: ${display(s.start_at)} → ${display(s.end_at)}`),text('p',`Đăng kí: ${display(s.open_at)} → ${display(s.close_at)}`));
      const b=text('button',state(e)==='soon'?'Chưa mở đăng kí':state(e)==='closed'?'Đã qua thời hạn đăng kí':'Đăng kí');b.type='button';b.disabled=state(e)!=='open';
      b.onclick=action(async()=>{await startRegistration(s.id,e.session_type);if(location.hash==='#profile-panel')return;(el('queue-panel').hidden?el('booking-map'):el('queue-panel')).scrollIntoView({block:'start'});});box.append(b);
    }
    el('event-detail').scrollIntoView({block:'start'});el('event-detail-title').focus({preventScroll:true});
  }
  const groups=['open','soon','closed'];
  function card(e){
      const b=text('button','');b.type='button';b.className='event-card';b.setAttribute('aria-label',`Xem ${label(e)}`);
      const frame=text('div','');frame.className='event-art poster';const fallback=text('span','Không tải được ảnh ca');fallback.className='image-failure';frame.append(fallback);
      const img=document.createElement('img');img.src=e.poster_url;img.alt=label(e);img.width=1280;img.height=720;img.loading='lazy';img.onerror=()=>img.remove();frame.append(img);
      const copy=text('div','');copy.className='session-card-copy';
      const title=text('h3',e.name),venue=text('p',e.venue),registration=text('p',`Bắt đầu đăng kí: ${schedule(e)?.open_at?display(schedule(e).open_at):'Chưa công bố'}`);
      venue.className='session-card-venue';registration.className='session-card-registration';copy.append(title,venue,registration);
      b.append(frame,copy);b.onclick=()=>details(e);return b;
  }
  function updateRails(){
    for(const key of groups){
      const rail=el('sessions-'+key),max=rail.scrollWidth-rail.clientWidth;
      el('sessions-'+key+'-actions').hidden=max<=1;
      for(const button of el('sessions-'+key+'-actions').children)button.disabled=button.dataset.direction==='-1'?rail.scrollLeft<=1:rail.scrollLeft>=max-1;
    }
  }
  function resetRails(){for(const key of groups)el('sessions-'+key).scrollLeft=0;}
  function render(){
    const term=el('event-search').value.trim().toLocaleLowerCase('vi');
    const now=Date.now()+offset;
    const items=events.filter(e=>(!e.status||e.status==='ACTIVE')&&e.session_type===type&&[e.name,e.venue,e.address].join(' ').toLocaleLowerCase('vi').includes(term)).sort((a,b)=>Date.parse(schedule(a)?.start_at||0)-Date.parse(schedule(b)?.start_at||0));
    el('events-empty').hidden=items.length>0;
    for(const key of groups){
      const matches=items.filter(e=>state(e,now)===key),rail=el('sessions-'+key),left=rail.scrollLeft;
      el('sessions-'+key+'-section').hidden=!matches.length;rail.replaceChildren(...matches.map(card));rail.scrollLeft=left;
    }
    for(const b of el('session-types').children)b.setAttribute('aria-pressed',String(b.dataset.type===type));
    requestAnimationFrame(updateRails);
  }
  for(const button of document.querySelectorAll('[data-session-rail]'))button.onclick=()=>{
    const rail=el(button.dataset.sessionRail);
    rail.scrollBy({left:Number(button.dataset.direction)*rail.clientWidth*.9,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
  };
  for(const key of groups)el('sessions-'+key).addEventListener('scroll',updateRails,{passive:true});
  window.addEventListener('resize',updateRails);
  function choices(){
    const c=el('event-choice'),current=c.value;c.replaceChildren(new Option('Tạo ca mới',''),...events.map(e=>new Option(label(e),e.id)));c.value=current;
    const r=el('registration-session'),id=r.value;r.replaceChildren(new Option('Chọn ca',''),...events.filter(e=>schedule(e)).map(e=>new Option(label(e),schedule(e).id)));r.value=id;
    window.dispatchEvent(new CustomEvent('labseat-events',{detail:events.map(e=>({...e,schedule:schedule(e)}))}));
  }
  async function refresh(){const rev=++revision,result=await api(me?.role==='admin'?'/admin/events':'/events');if(rev!==revision)return;events=result;choices();render();renderCheckinPolicy();}
  for(const b of el('session-types').children)b.onclick=()=>{type=b.dataset.type;resetRails();el('event-detail').hidden=true;render();};
  el('event-search').oninput=()=>{resetRails();render();};
  el('close-event-detail').onclick=()=>{el('event-detail').hidden=true;el('event-search').focus();};
  window.addEventListener('labseat-home',()=>{el('event-detail').hidden=true;el('event-search').focus({preventScroll:true});window.scrollTo({top:0});});
  function preview(url){if(previewURL){URL.revokeObjectURL(previewURL);previewURL=null;}const img=el('event-poster-preview');img.hidden=!url;if(url)img.src=url;else img.removeAttribute('src');}
  form.elements.poster.onchange=()=>{
    const file=form.elements.poster.files[0];preview(null);if(!file){posterCheck=Promise.resolve(true);return;}
    const input=form.elements.poster;
    posterCheck=(async()=>{
      try{
        if(file.size>5*1024*1024||!['image/jpeg','image/png','image/webp'].includes(file.type))throw Error('Chọn JPEG/PNG/WebP tối đa 5 MB.');
        const bitmap=await createImageBitmap(file).catch(()=>{throw Error('Nội dung ảnh không hợp lệ.');});bitmap.close();
        if(input.files[0]!==file)return false;previewURL=URL.createObjectURL(file);el('event-poster-preview').src=previewURL;el('event-poster-preview').hidden=false;return true;
      }catch(error){if(input.files[0]===file){input.value='';notice(error.message);}return false;}
    })();
  };
  let checkinPolicyBusy=false;
  function renderCheckinPolicy(){
    const selected=events.find(e=>e.id===el('event-choice').value),s=selected?schedule(selected):null;
    const enabled=s?.checkin_enabled===true,button=el('event-checkin-toggle');
    button.disabled=!s||checkinPolicyBusy;button.textContent=enabled?'Đóng check-in':'Mở check-in';button.setAttribute('aria-pressed',String(enabled));
    el('event-checkin-status').textContent=s?(enabled?'Đang mở check-in':'Đang đóng check-in'):'Lưu ca trước để cài đặt check-in.';
  }
  el('event-checkin-toggle').onclick=action(async()=>{
    if(checkinPolicyBusy)return;
    const selected=events.find(e=>e.id===el('event-choice').value),s=selected?schedule(selected):null;if(!s)return;
    checkinPolicyBusy=true;renderCheckinPolicy();
    try{
      const updated=await api(`/admin/lab-sessions/${s.id}/check-in`,'PATCH',{enabled:!s.checkin_enabled,close_mode:el('checkin-close-mode').value,closes_at:el('checkin-close-mode').value==='custom'&&el('checkin-closes-at').value?new Date(el('checkin-closes-at').value+'+07:00').toISOString():null});
      if(selected.schedule)selected.schedule.checkin_enabled=updated.checkin_enabled;
      const cached=sessions.find(l=>l.id===s.id);if(cached)cached.checkin_enabled=updated.checkin_enabled;
      window.dispatchEvent(new CustomEvent('labseat-checkin-policy',{detail:{sessionId:s.id,enabled:updated.checkin_enabled}}));
      notice(updated.checkin_enabled?'Đã mở check-in cho ca.':'Đã đóng check-in cho ca.');
    }finally{checkinPolicyBusy=false;renderCheckinPolicy();}
  });
  el('event-choice').onchange=()=>{
    const e=events.find(e=>e.id===el('event-choice').value);
    for(const k of ['name','session_type','description','venue','address'])form.elements[k].value=e?.[k]||(k==='session_type'?'exam':'');
    const s=e?schedule(e):null;el('checkin-close-mode').value=s?.checkin_close_mode||'end_at';el('checkin-closes-at').value=s?.checkin_closes_at?new Date(Date.parse(s.checkin_closes_at)+7*3600000).toISOString().slice(0,16):'';for(const k of keys)form.elements[k].value=s?.[k]?new Date(Date.parse(s[k])+7*3600000).toISOString().slice(0,16):'';
    originalTimes=Object.fromEntries(keys.map(k=>[k,form.elements[k].value]));form.elements.poster.value='';form.elements.poster.required=!e;posterCheck=Promise.resolve(true);preview(e?.poster_url);el('event-save-status').textContent='';renderCheckinPolicy();
  };
  form.onsubmit=async event=>{
    event.preventDefault();if(el('save-event').disabled)return;el('save-event').disabled=true;const message=el('event-save-status');
    try{
      if(!await posterCheck)throw Error('Chọn ảnh ca hợp lệ.');
      const data=Object.fromEntries(['name','session_type','description','venue','address'].map(k=>[k,form.elements[k].value]));
      const times=Object.fromEntries(keys.map(k=>[k,form.elements[k].value]));
      if(!originalTimes||keys.some(k=>times[k]!==originalTimes[k]))data.schedule=Object.fromEntries(keys.map(k=>[k,new Date(times[k]+':00+07:00').toISOString()]));
      const id=el('event-choice').value,body=new FormData();body.append('data',JSON.stringify(data));const file=form.elements.poster.files[0];if(file)body.append('poster',file);
      message.textContent='Đang lưu ca…';const saved=await api('/admin/events'+(id?'/'+id:''),id?'PATCH':'POST',body);
      const existing=events.findIndex(e=>e.id===saved.id);if(existing<0)events.push(saved);else events[existing]=saved;choices();el('event-choice').value=saved.id;
      originalTimes=times;form.elements.poster.value='';form.elements.poster.required=false;preview(saved.poster_url);
      await catalogue();await refresh();el('event-choice').value=saved.id;renderCheckinPolicy();message.textContent='Đã lưu ca.';
    }catch(error){message.textContent=error.message;}finally{el('save-event').disabled=false;}
  };
  window.addEventListener('labseat-catalogue',event=>{sessions=event.detail.labs;if(event.detail.serverTime)offset=Date.parse(event.detail.serverTime)-Date.now();refresh().catch(error=>{el('events-empty').hidden=false;el('events-empty').textContent='Chưa tải được danh sách ca.';notice(error.message);});});
  window.addEventListener('labseat-admin-refresh',()=>refresh().catch(error=>notice(error.message)));
  setInterval(render,30000);
})();
