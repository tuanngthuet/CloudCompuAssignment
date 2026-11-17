'use strict';
(() => {
  const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
  const control=(text,fn,secondary=true)=>{const b=node('button',text,secondary?'secondary':'');b.type='button';b.onclick=action(async()=>{if(b.disabled)return;b.disabled=true;try{await fn();}finally{b.disabled=false;}});return b;};
  const formAction=(id,fn)=>{$(id).onsubmit=action(async()=>{const f=$(id),status=f.querySelector('[data-form-status]'),b=f.querySelector('button');if(b.disabled)return;b.disabled=true;status.textContent='Đang xử lí…';try{await fn(f,status);}catch(e){status.textContent=e.message;throw e;}finally{b.disabled=false;}});};
  formAction('forgot-password',async(f,status)=>{const result=await api('/auth/password-reset/request','POST',values(f));status.textContent=result.message;});
  formAction('password-change',async(f,status)=>{await api('/auth/password/change','POST',values(f));f.reset();status.textContent='Đã đổi mật khẩu và thu hồi các phiên khác.';await identity();});
  const statusLabels={PENDING:'Đang chờ',SENDING:'Đang gửi',ACCEPTED:'Brevo đã tiếp nhận',DELIVERED:'Đã giao thư',DEFERRED:'Tạm hoãn',SOFT_BOUNCE:'Tạm thời chưa giao được',HARD_BOUNCE:'Địa chỉ bị từ chối',BLOCKED:'Bị chặn',COMPLAINT:'Có phản ánh spam',UNKNOWN:'Cần đối chiếu kết quả gửi',FAILED:'Gửi lỗi',SKIPPED:'Không gửi'};
  $('verify-email').onclick=action(async()=>{const b=$('verify-email');if(b.disabled)return;b.disabled=true;try{await api('/auth/email-verification/request','POST');$('email-verification-status').textContent='Đã xếp hàng gửi liên kết xác minh. Kiểm tra hộp thư và thư rác.';}finally{b.disabled=false;}});
  window.addEventListener('labseat-profile',e=>{$('email-verification-banner').hidden=!me||e.detail.email_verified;$('email-verification-status').textContent=e.detail.email_verified?'Email đã xác minh.':'Email chưa xác minh. Bấm gửi liên kết, sau đó mở email để xác nhận. Nếu chưa có email, hãy lưu email trong hồ sơ trước.';$('verify-email').hidden=e.detail.email_verified;});
  let challenge=null;
  function parseAuthLink(){
    if(!location.hash.startsWith('#auth-action?'))return;
    const args=new URLSearchParams(location.hash.split('?').slice(1).join('?'));
    challenge={challenge_id:args.get('id'),token:args.get('token'),purpose:args.get('purpose')};
    history.replaceState(null,'',location.pathname+location.search+'#auth-action');
    $('auth-action-title').textContent=challenge.purpose==='reset'?'Đặt lại mật khẩu':'Xác minh email';
    $('reset-password-fields').hidden=challenge.purpose!=='reset';
    for(const input of $('reset-password-fields').querySelectorAll('input'))input.required=challenge.purpose==='reset';
    window.dispatchEvent(new Event('hashchange'));
  }
  window.addEventListener('hashchange',parseAuthLink);parseAuthLink();
  formAction('auth-action-form',async(f,status)=>{
    if(!challenge)throw Error('Liên kết không hợp lệ. Hãy yêu cầu liên kết mới.');
    const body={challenge_id:challenge.challenge_id,token:challenge.token};
    if(challenge.purpose==='reset')Object.assign(body,values(f));
    await api(challenge.purpose==='reset'?'/auth/password-reset/confirm':'/auth/email-verification/confirm','POST',body);
    status.textContent=challenge.purpose==='reset'?'Đã đặt lại mật khẩu. Đăng nhập để tiếp tục.':'Email đã xác minh. Bạn có thể đăng kí ca.';
    challenge=null;f.reset();$('auth-action-submit').hidden=true;await identity();
  });
  let page=0,total=0;
  async function loadUsers(){
    const response=await api('/admin/users?q='+encodeURIComponent($('user-search-text').value)+'&offset='+page*25+'&limit=25');total=response.total;
    $('users-status').textContent=`${total} tài khoản · Trang ${page+1}`;$('users-prev').disabled=page===0;$('users-next').disabled=(page+1)*25>=total;
    $('users-table').replaceChildren();
    const review=await api('/admin/privacy-review');
    if(review.length){const box=node('div',undefined,'management-row');box.append(node('h3','Hồ sơ cần duyệt thời hạn lưu trữ'));for(const user of review){const row=node('p',user.username+' · '+date(user.last_activity_at));row.append(control('Duyệt ẩn danh',async()=>{const reason=prompt('Xác nhận đã rà soát hồ sơ và nhập lý do duyệt ẩn danh. Thao tác này xóa thông tin cá nhân:');if(!reason?.trim())return;await api(`/admin/users/${user.id}/anonymize`,'POST',{reason});await loadUsers();}));box.append(row);}$('users-table').append(box);}
    for(const user of response.items){
      const row=node('article',undefined,'management-row');row.append(node('h3',user.full_name||user.username),node('p',`${user.username} · ${user.email||'Chưa có email'} · ${user.email_verified?'Đã xác minh':'Chưa xác minh'}`));
      const role=node('select');role.setAttribute('aria-label',`Vai trò của ${user.username}`);for(const value of ['student','staff','admin'])role.append(new Option(value,value));role.value=user.role;
      const state=node('select');state.setAttribute('aria-label',`Trạng thái của ${user.username}`);for(const [value,label] of [['ACTIVE','Hoạt động'],['LOCKED','Khóa']])state.append(new Option(label,value));state.value=user.status;
      role.disabled=state.disabled=user.status==='ANONYMIZED';
      row.append(role,state,control('Lưu quyền và trạng thái',async()=>{
        const reason=prompt('Lý do thay đổi quyền/trạng thái:');if(!reason?.trim())return;
        await api(`/admin/users/${user.id}`,'PATCH',{role:role.value,status:state.value,reason});
        await identity();if(me?.role==='admin')await loadUsers();notice('Đã cập nhật tài khoản.');
      }),control('Xem hồ sơ',async()=>{
        const data=await api(`/admin/users/${user.id}`);const details=node('dl',undefined,'checkin-info');
        for(const [label,value] of [['Họ tên',data.full_name],['CCCD',data.cccd],['Điện thoại',data.phone],['Email',data.email]])details.append(node('dt',label),node('dd',value||'Không cung cấp'));
        row.querySelector('dl')?.remove();row.append(details);
      }));$('users-table').append(row);
    }
  }
  formAction('user-search',async(f,status)=>{page=0;await loadUsers();status.textContent='Đã tải danh sách.';});
  // Status is always present for keyboard/screen-reader feedback.
  if(!$('user-search').querySelector('[data-form-status]')){const p=node('p');p.dataset.formStatus='';p.setAttribute('role','status');$('user-search').append(p);}
  $('users-prev').onclick=action(async()=>{if(page>0){page--;await loadUsers();}});
  $('users-next').onclick=action(async()=>{if((page+1)*25<total){page++;await loadUsers();}});
  async function loadAssignments(){
    const id=$('assignment-session').value;const box=$('staff-assignment-list');box.replaceChildren();if(!id)return;
    for(const user of await api(`/admin/lab-sessions/${id}/staff`)){
      const row=node('div',undefined,'management-row');row.append(node('p',user.full_name||user.username),control('Thu hồi phân công',async()=>{await api(`/admin/lab-sessions/${id}/staff/${user.id}`,'DELETE');await loadAssignments();}));box.append(row);
    }
  }
  async function assignmentChoices(){
    const current=$('assignment-session').value;
    $('assignment-session').replaceChildren(new Option('Chọn ca',''),...labs.map(l=>new Option(eventTitle(l)+' · '+date(l.start_at),l.id)));$('assignment-session').value=current;
    const response=await api('/admin/users?role=staff&limit=100');
    $('assignment-user').replaceChildren(new Option('Chọn staff',''),...response.items.filter(u=>u.role==='staff'&&u.status==='ACTIVE').map(u=>new Option(u.full_name||u.username,u.id)));
    await loadAssignments();
  }
  $('assignment-session').onchange=action(loadAssignments);
  formAction('staff-assign',async(f,status)=>{const sid=$('assignment-session').value,uid=$('assignment-user').value;if(!sid||!uid)throw Error('Chọn ca và staff.');await api(`/admin/lab-sessions/${sid}/staff/${uid}`,'PUT');status.textContent='Đã phân công staff.';await loadAssignments();});
  async function loadEmails(){
    const box=$('email-jobs-list');box.replaceChildren();
    for(const job of await api('/admin/emails')){
      const row=node('article',undefined,'management-row');row.append(node('h3',`${job.kind} · ${statusLabels[job.status]||job.status}`),node('p',date(job.created_at)));
      if(job.reservation_id)row.append(control('Gửi lại email vé',async()=>{await api(`/admin/tickets/${job.reservation_id}/email-resends`,'POST');notice('Đã xếp hàng gửi lại.');await loadEmails();}));box.append(row);
    }
  }
  $('email-jobs-refresh').onclick=action(loadEmails);
  formAction('email-unblock',async(f,status)=>{await api('/admin/email-suppressions/'+encodeURIComponent(f.elements.email.value),'DELETE');status.textContent='Đã gỡ chặn email và ghi lịch sử.';});
  const checkinForm=$('checkin-form'),adminMount=checkinForm.parentElement;
  async function staffChoices(){
    const response=await api('/staff/lab-sessions');$('staff-session').replaceChildren(new Option('Chọn ca',''),...response.items.map(l=>new Option((l.name||'Ca')+' · '+date(l.start_at),l.id)));
    $('checkin-form').hidden=false;
  }
  $('staff-session').onchange=()=>{clearCheckin();$('checkin-form').reset();connectStream($('staff-session').value);};
  $('staff-reveal-identity').onclick=action(async()=>{
    if(!checkinReceipt)return;const rid=checkinReceipt.ticket.reservation_id;
    const data=await api(`/staff/check-ins/${rid}/identity`,'POST');
    if(checkinReceipt?.ticket.reservation_id!==rid)return;
    checkinReceipt.profile.cccd=data.cccd;renderCheckin();notice('Đã ghi lịch sử xem CCCD để đối chiếu.');
  });
  window.addEventListener('labseat-identity',e=>{
    $('staff-link').hidden=e.detail?.role!=='staff';$('staff-reveal-identity').hidden=e.detail?.role!=='staff';
    if(e.detail?.role==='staff'){$('staff-checkin-mount').append(checkinForm);action(staffChoices)();}
    else if(checkinForm.parentElement!==adminMount)adminMount.append(checkinForm);
  });
  window.addEventListener('labseat-screen',e=>{
    if(e.detail==='staff-panel'&&me?.role==='staff')checkinForm.hidden=false;
  });
  const selected=()=>labs.find(l=>l.event_id===$('event-choice').value);
  $('checkin-policy-save').onclick=action(async()=>{
    const lab=selected();if(!lab)throw Error('Chọn ca đã lưu.');const mode=$('checkin-close-mode').value;
    const data=await api(`/admin/lab-sessions/${lab.id}/check-in`,'PATCH',{enabled:lab.checkin_enabled,close_mode:mode,closes_at:mode==='custom'&&$('checkin-closes-at').value?new Date($('checkin-closes-at').value+'+07:00').toISOString():null});
    Object.assign(lab,{checkin_enabled:data.checkin_enabled,checkin_close_mode:data.close_mode,checkin_closes_at:data.closes_at});
    window.dispatchEvent(new Event('labseat-admin-refresh'));notice('Đã lưu hạn check-in.');
  });
  for(const kind of ['cancel','archive','delete'])$(kind+'-event').onclick=action(async()=>{
    const id=$('event-choice').value;if(!id)throw Error('Chọn ca đã lưu.');
    const reason=kind==='delete'?null:prompt(kind==='cancel'?'Lý do hủy ca (người đăng kí sẽ được thông báo):':'Lý do lưu trữ:');
    if(kind!=='delete'&&!reason?.trim())return;
    if(!confirm(kind==='delete'?'Xóa hẳn ca chưa có lịch sử đăng kí?':kind==='cancel'?'Hủy ca và dừng tiếp nhận vé?':'Lưu trữ ca khỏi danh sách sử dụng?'))return;
    await api(kind==='delete'?`/admin/events/${id}`:`/admin/events/${id}/${kind}`,kind==='delete'?'DELETE':'POST',reason?{reason}:undefined);
    await catalogue();window.dispatchEvent(new Event('labseat-admin-refresh'));notice(kind==='cancel'?'Ca đã hủy. Thông báo đang được xử lí.':'Đã cập nhật ca.');
  });
  function adminView(){
    if(me?.role!=='admin')return;
    const hash=location.hash.slice(1);
    if(hash==='users-panel')action(loadUsers)();
    if(hash==='staff-assignment-panel')action(assignmentChoices)();
    if(hash==='email-jobs-panel')action(loadEmails)();
  }
  window.addEventListener('hashchange',adminView);window.addEventListener('labseat-identity',adminView);
  let stream=null,streamId='',expiryTimer=null,resyncTimer=null,lastRefresh=0,retryTimer=null,retryDelay=1000;
  const closeStream=()=>{stream?.close();stream=null;streamId='';clearTimeout(retryTimer);window.labseatStreamHealthy=false;};
  function refreshSnapshot(){
    if(document.hidden||Date.now()-lastRefresh<250)return;lastRefresh=Date.now();
    if(!$('booking').hidden)action(pollAvailability)();
    if(checkinReceipt)action(lookupCheckin)();
  }
  function connectStream(id){
    closeStream();if(!id||typeof EventSource==='undefined'||document.hidden)return;streamId=id;
    const source=new EventSource(`/lab-sessions/${id}/stream`);stream=source;
    source.onopen=()=>{if(stream!==source)return;window.labseatStreamHealthy=true;retryDelay=1000;refreshSnapshot();};
    source.addEventListener('changed',()=>{window.labseatSnapshotAt=Date.now();refreshSnapshot();});
    const fail=()=>{if(stream!==source)return;closeStream();retryTimer=setTimeout(()=>connectStream(id),retryDelay);retryDelay=Math.min(30000,retryDelay*2);};
    source.addEventListener('degraded',fail);source.onerror=fail;
  }
  window.addEventListener('labseat-availability',e=>{
    if(e.detail.id!==$('session').value)return;window.labseatSnapshotAt=Date.now();
    if(streamId!==e.detail.id)connectStream(e.detail.id);
    clearTimeout(expiryTimer);
    if(e.detail.next_change_at)expiryTimer=setTimeout(refreshSnapshot,Math.max(250,Math.min(300000,Date.parse(e.detail.next_change_at)-Date.now()-offset+300)));
  });
  document.addEventListener('visibilitychange',()=>{if(document.hidden)closeStream();else {connectStream($('session').value);refreshSnapshot();}});
  window.addEventListener('labseat-checkin-preview',e=>{if(streamId!==e.detail.id)connectStream(e.detail.id);});
  window.addEventListener('pagehide',closeStream);
  setInterval(()=>{if(!document.hidden&&streamId)refreshSnapshot();},30000);
  window.addEventListener('labseat-screen',e=>{if(e.detail==='booking'&&$('session').value)connectStream($('session').value);else if(e.detail!=='staff-panel'&&e.detail!=='admin-panel')closeStream();});
})();
