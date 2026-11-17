// Offline controller tests with a minimal DOM/fetch fixture. Not browser or DB E2E.
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
import {webcrypto} from 'node:crypto';
class Element {
  constructor(tag='div'){this.tag=tag;this.children=[];this.textContent='';this.hidden=false;this.value='';this.elements={};this.fields={};this.disabled=false;this.style={};this.dataset={};}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  reset(){this.fields={};}
  async play(){}
  showModal(){this.open=true;}
  close(){this.open=false;}
  getContext(){return {drawImage(){},getImageData:()=>({data:new Uint8ClampedArray(4),width:1,height:1})};}
  setPointerCapture(){}
  getBoundingClientRect(){return {left:0,top:0,width:parseFloat(this.style.width)||192,height:parseFloat(this.style.height)||192};}
  setAttribute(){}
  click(){}
}
async function harness(){
  const ids=[...fs.readFileSync('app/templates/index.html','utf8').matchAll(/id="([^"]+)"/g)].map(x=>x[1]);
  const nodes=Object.fromEntries(ids.map(id=>[id,new Element()]));
  for(const id of ['checkin-form'])for(const key of ['ticket_code'])nodes[id].elements[key]=new Element('input');
  for(const key of ['full_name','cccd','phone','email','current_password'])nodes['profile-form'].elements[key]=new Element('input');
  nodes['hold-panel'].hidden=true;
  const requests=[],timers=[],events=[],listeners={};
  let respond=(path)=>path==='/me'?{id:'u1',username:'student',role:'student'}:path==='/me/tickets'?[]:path==='/rooms'?[]:path==='/lab-sessions'?{items:[]}:{};
  class FormData {constructor(form){this.fields=form?.fields||{};}entries(){return Object.entries(this.fields)[Symbol.iterator]();}[Symbol.iterator](){return this.entries();}append(k,v){this.fields[k]=v;}}
  const context=vm.createContext({
    document:{querySelectorAll:()=>[],getElementById:id=>nodes[id],createElement:tag=>new Element(tag),cookie:'labseat_csrf=csrf-value; labseat_pre_csrf=pre-value',hidden:false},
    fetch:async(path,options)=>{requests.push({path,...options});const data=await respond(path,options);return {ok:true,headers:{get:()=> 'application/json'},json:async()=>data};},
    crypto:webcrypto,confirm:()=>true,FormData,Option:class extends Element{constructor(text,value){super('option');this.textContent=text;this.value=value;}},Date,console,URL,
    setInterval:fn=>{timers.push(fn);return timers.length;},setTimeout:()=>1,clearTimeout:()=>{},navigator:{},CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}},window:{dispatchEvent:event=>{events.push(event);for(const fn of listeners[event.type]||[])fn(event);},addEventListener:(type,fn)=>{(listeners[type]??=[]).push(fn);if(type==='DOMContentLoaded')setImmediate(fn);}}
  });
  vm.runInContext(fs.readFileSync(process.env.LABSEAT_UI_SCRIPT || 'app/static/app.js','utf8'),context);
  const flush=async()=>{for(let i=0;i<8;i++)await new Promise(resolve=>setImmediate(resolve));};
  await flush();
  return {nodes,requests,context,timers,events,flush,setResponder:fn=>{respond=fn;},run:code=>vm.runInContext(code,context)};
}
const lab=id=>({id,room_id:'room',open_at:'2026-01-01T00:00:00Z',close_at:'2026-01-01T02:00:00Z',start_at:'2026-01-01T03:00:00Z',end_at:'2026-01-01T04:00:00Z'});

test('late availability response never replaces the currently selected session',async()=>{
  const h=await harness();h.run(`labs=${JSON.stringify([lab('old'),lab('new')])}`);
  let resolveOld;
  h.setResponder(path=>path==='/me/tickets'?[]:path.endsWith('/seat-map')?{columns:8,rows:12,elements:[{id:'new-seat',seat_id:'new-seat',seat_code:'NEW',kind:'seat',x:0,y:2,width:1,height:1}]}:path.includes('/old/')?new Promise(resolve=>{resolveOld=resolve;}):{server_time:'2026-01-01T00:00:00Z',items:[{id:'new-seat',seat_code:'NEW',available:true}]});
  h.nodes.session.value='old';const old=h.run('availability()');
  h.nodes.session.value='new';await h.run('availability()');
  resolveOld({server_time:'2026-01-01T00:00:00Z',items:[{id:'old-seat',seat_code:'OLD',available:true}]});await old;
  assert.deepEqual(h.nodes.seats.children.map(x=>x.textContent),['NEW']);
  await h.nodes.seats.children[0].onclick();
  assert.equal(h.requests.some(r=>r.path==='/holds'),false);
  await h.nodes['hold-selected'].onclick();
  const request=h.requests.find(r=>r.path==='/holds');
  assert.equal(JSON.parse(request.body).session_id,'new');
});

test('confirming via ticket card clears the corresponding hold panel',async()=>{
  const h=await harness();
  h.run(`held={hold_id:'r1'};`);h.nodes['hold-panel'].hidden=false;
  h.setResponder(path=>path==='/me/tickets'?[{reservation_id:'r1',session_id:'s1',seat_id:'seat',status:'HELD'}]:{status:'CONFIRMED'});
  await h.run('tickets()');
  const card=h.nodes.tickets.children[0];await card.children.find(x=>x.tag==='button'&&x.textContent==='Xác nhận đăng kí').onclick();
  assert.equal(h.nodes['hold-panel'].hidden,true);
  assert.equal(h.run('held'),null);
  assert.equal(h.requests.find(r=>r.path==='/holds/r1/confirm').headers['X-CSRF-Token'],'csrf-value');
});

test('stopping camera while permission request is pending stops late stream',async()=>{
  const h=await harness();let resolveStream,stopped=0;
  h.context.navigator.mediaDevices={getUserMedia:()=>new Promise(resolve=>{resolveStream=resolve;})};
  h.context.BarcodeDetector=class{async detect(){return [];}};h.context.window.BarcodeDetector=h.context.BarcodeDetector;
  const pending=h.nodes.camera.onclick();
  h.nodes['stop-camera'].onclick();
  resolveStream({getTracks:()=>[{stop:()=>{stopped++;}}]});await pending;
  assert.equal(stopped,1);assert.equal(h.run('cameraStream'),null);
});

test('camera unsupported offers manual entry without making a check-in request',async()=>{
  const h=await harness();await h.nodes.camera.onclick();
  assert.match(h.nodes.notice.textContent,/nhập mã/);
  assert.equal(h.requests.some(r=>r.path==='/admin/check-ins'),false);
});

test('room names are rendered as text and login uses pre-login CSRF',async()=>{
  const h=await harness();
  h.setResponder(path=>path==='/rooms'?[{id:'room',name:'<img src=x onerror=alert(1)>',has_image:false}]:path==='/lab-sessions'?{items:[lab('safe')]}:path==='/me/tickets'?[]:{username:'student',role:'student'});
  await h.run('catalogue()');assert.match(h.nodes.session.children[1].textContent, /^<img src=x onerror=alert\(1\)>/);
  h.nodes.login.fields={username:'student',password:'test-password'};
  await h.nodes.login.onsubmit();
  const request=h.requests.find(r=>r.path==='/auth/login');assert.equal(request.headers['X-CSRF-Token'],'pre-value');
  assert.equal(JSON.parse(request.body).password,'test-password');
});

test('CSV parser supports BOM, commas, multiline and escaped quotes',async()=>{
  const h=await harness();const input='\uFEFFid,name\r\n1,"A, B"\r\n2,"line\nnext ""quoted"""\r\n';h.context.csvFixture=input;
  const rows=JSON.parse(JSON.stringify(h.run('parseCSV(csvFixture)')));
  assert.deepEqual(rows,[['id','name'],['1','A, B'],['2','line\nnext "quoted"']]);
});

test('availability restores own held registration without renewing it',async()=>{
  const h=await harness();h.run(`labs=${JSON.stringify([lab('s1')])}`);h.nodes.session.value='s1';
  h.setResponder(path=>path==='/me/tickets'?[{reservation_id:'held-id',session_id:'s1',seat_id:'seat1',status:'HELD',hold_expires_at:'2026-01-01T00:03:00Z'}]:path.endsWith('/seat-map')?{columns:8,rows:12,elements:[{id:'seat1',seat_id:'seat1',seat_code:'A01',kind:'seat',x:0,y:2,width:1,height:1}]}:{server_time:'2026-01-01T00:00:00Z',items:[{id:'seat1',seat_code:'A01',available:false}]});
  await h.run('availability()');assert.equal(h.run('held.hold_id'),'held-id');assert.equal(h.nodes['hold-panel'].hidden,false);assert.equal(h.nodes['hold-selected'].disabled,true);assert.equal(h.requests.some(r=>r.path==='/holds'),false);
});

test('admin registrations use their own session selector independently of booking',async()=>{
  const h=await harness();h.nodes.session.value='student-filtered';h.nodes['registration-session'].value='admin-session';
  h.setResponder(()=>({text:async()=>'reservation_id,username,seat_code,status,checked_in_at\n1,Student,A01,CONFIRMED,2026-11-12 17:00:00+00:00\n'}));
  await h.nodes['load-registrations'].onclick();
  assert.equal(h.requests.at(-1).path,'/admin/lab-sessions/admin-session/registrations.csv');
  assert.equal(h.run('registrationRows[1][2]'),'A01');
  assert.equal(h.nodes['registration-table'].children[0].children[0].children[1].textContent,'Người đăng kí');
  assert.equal(h.nodes['registration-table'].children[0].children[1].children[3].textContent,'Đã xác nhận');
  assert.match(h.nodes['registration-table'].children[0].children[1].children[4].textContent,/13\/11\/2026/);
});

test('late registrations response cannot replace a newly selected session',async()=>{
  const h=await harness();let resolveOld;
  h.setResponder(path=>path.includes('/old/')?new Promise(resolve=>{resolveOld=resolve;}):{text:async()=>'id,name,seat,status\n2,New,B02,CONFIRMED\n'});
  h.nodes['registration-session'].value='old';const old=h.nodes['load-registrations'].onclick();
  h.nodes['registration-session'].value='new';await h.nodes['registration-session'].onchange();
  resolveOld({text:async()=>'id,name,seat,status\n1,Old,A01,CONFIRMED\n'});await old;
  assert.equal(h.run('registrationRows[1][2]'),'B02');
});

test('waiting queue hides the catalogue and map and restores without joining',async()=>{
  const h=await harness();h.run(`queuePolicy={enabled:true};labs=${JSON.stringify([lab('q')])}`);h.nodes.session.value='q';
  h.setResponder(path=>path==='/me/tickets'?[]:{session_id:'q',status:'WAITING',number_ahead:3,server_time:new Date().toISOString(),heartbeat_after_seconds:5});
  await h.run('availability()');
  assert.equal(h.nodes.seats.children.length,0);
  assert.equal(h.nodes['booking-map'].hidden,true);
  assert.equal(h.nodes['booking-catalogue'].hidden,true);
  assert.equal(h.nodes['hold-selected'].disabled,true);
  assert.match(h.nodes['queue-position'].textContent,/3/);
  assert.equal(h.requests.some(r=>r.path.endsWith('/queue/join')),false);
  assert.equal(h.requests.some(r=>r.path.endsWith('/seats')),false);
  assert.equal(h.requests.at(-1).headers['X-CSRF-Token'],'csrf-value');
});

test('expired admission disables hold even with a selected seat',async()=>{
  const h=await harness();h.nodes.session.value='q';
  h.run(`queuePolicy={enabled:true};selectedSeat={id:'seat',seat_code:'A01'};queueState={session_id:'q',status:'ADMITTED',admission_expires_at:'2000-01-01T00:00:00Z'};updateSummary();`);
  assert.equal(h.nodes['hold-selected'].disabled,true);
  await h.nodes['hold-selected'].onclick();
  assert.equal(h.requests.some(r=>r.path==='/holds'),false);
});

test('late queue response cannot change the newly selected session',async()=>{
  const h=await harness();let resolve;
  h.nodes.session.value='old';h.run('queuePolicy={enabled:true}');
  h.setResponder(()=>new Promise(done=>{resolve=done;}));
  const pending=h.run("refreshQueue('join','old')");await h.flush();
  h.nodes.session.value='new';h.run('queueRevision++;queueState=null;');
  resolve({session_id:'old',status:'ADMITTED',server_time:new Date().toISOString(),admission_expires_at:new Date(Date.now()+120000).toISOString()});await pending;
  assert.equal(h.run('queueState'),null);
  assert.equal(h.run('queueBusy'),false);
});

const openLab=id=>({...lab(id),open_at:new Date(Date.now()-60000).toISOString(),close_at:new Date(Date.now()+600000).toISOString()});
const queueResult=(status='NONE',extra={})=>({session_id:'q',status,number_ahead:2,server_time:new Date().toISOString(),heartbeat_after_seconds:5,...extra});
async function queueHarness(){
  const h=await harness();h.run(`queuePolicy={enabled:true};labs=${JSON.stringify([openLab('q'),openLab('new')])};allRooms=[{id:'room',name:'Phòng máy A'}];`);h.nodes.session.value='q';return h;
}
test('selecting an open session automatically restores then joins using CSRF',async()=>{
  const h=await queueHarness();
  h.setResponder(path=>path==='/me/tickets'?[]:path.endsWith('/heartbeat')?queueResult():queueResult('WAITING'));
  await h.nodes.session.onchange();
  assert.deepEqual(h.requests.filter(r=>r.path.includes('/queue/')).map(r=>r.path.split('/').at(-1)),['heartbeat','join']);
  assert.equal(h.nodes['queue-position'].textContent,'2');
  assert.equal(h.requests.at(-1).headers['X-CSRF-Token'],'csrf-value');
  assert.equal(h.nodes['booking-map'].hidden,true);
});
test('guest selecting a session requests login and resumes that session after identity',async()=>{
  const h=await queueHarness();h.run('me=null');
  await h.nodes.session.onchange();
  assert.equal(h.events.find(e=>e.type==='labseat-login-request').detail.returnToBooking,true);
  assert.equal(h.requests.some(r=>r.path.includes('/queue/')),false);
  h.run("me={id:'u1'}");
  h.setResponder(path=>path==='/me/tickets'?[]:path.endsWith('/heartbeat')?queueResult():queueResult('WAITING'));
  await h.run('availability()');
  assert.equal(h.requests.filter(r=>r.path.endsWith('/join')).length,1);
});
test('server expired lease automatically rejoins, local clock alone cannot create another lease',async()=>{
  const h=await queueHarness();h.run("queueState={session_id:'q',status:'ADMITTED',admission_expires_at:'2000-01-01T00:00:00Z'};renderQueue()");
  assert.equal(h.requests.some(r=>r.path.endsWith('/join')),false);
  h.setResponder(path=>path==='/me/tickets'?[]:path.endsWith('/heartbeat')?queueResult('EXPIRED'):queueResult('WAITING'));
  await h.run('availability()');
  assert.equal(h.requests.filter(r=>r.path.endsWith('/join')).length,1);
  assert.equal(h.run('queueState.status'),'WAITING');
});
test('leaving clears the selected session and never automatically rejoins',async()=>{
  const h=await queueHarness();h.run("queueSessionId='q';queueState={session_id:'q',status:'WAITING'}");
  h.setResponder(()=>queueResult('LEFT'));
  await h.nodes['leave-queue'].onclick();await h.run('availability()');
  assert.equal(h.nodes.session.value,'');assert.equal(h.nodes['booking-catalogue'].hidden,false);
  assert.equal(h.requests.filter(r=>r.path.endsWith('/leave')).length,1);
  assert.equal(h.requests.some(r=>r.path.endsWith('/join')),false);
});
test('switching sessions waits for an in-flight join, leaves old session, then joins new',async()=>{
  const h=await queueHarness();let resolve;
  h.run("queueSessionId='q'");
  h.setResponder(path=>path==='/me/tickets'?[]:path==='/lab-sessions/q/queue/join'?new Promise(done=>{resolve=done;}):path.endsWith('/heartbeat')?queueResult():queueResult('WAITING',{session_id:'new'}));
  const pending=h.run("refreshQueue('join','q')");await h.flush();
  h.nodes.session.value='new';const switching=h.nodes.session.onchange();await h.flush();
  assert.equal(h.requests.some(r=>r.path.endsWith('/leave')),false);
  resolve(queueResult('ADMITTED'));await pending;await switching;
  assert.deepEqual(h.requests.filter(r=>r.path.includes('/queue/')).map(r=>r.path),['/lab-sessions/q/queue/join','/lab-sessions/q/queue/leave','/lab-sessions/new/queue/heartbeat','/lab-sessions/new/queue/join']);
  assert.equal(h.run('queueState.session_id'),'new');
});
test('unknown join result is checked with heartbeat before any retry',async()=>{
  const h=await queueHarness();let heartbeat=0,join=0;
  h.setResponder(path=>{
    if(path==='/me/tickets')return [];
    if(path.endsWith('/heartbeat'))return ++heartbeat===1?queueResult():queueResult('WAITING');
    if(path.endsWith('/join')){join++;throw new Error('network timeout');}
  });
  await h.run('availability()');assert.equal(h.run('queueUncertain'),true);assert.equal(join,1);
  await h.run('availability()');assert.equal(join,1);
  h.run('queueNextHeartbeat=0');await h.run('availability()');
  assert.equal(heartbeat,2);assert.equal(join,1);assert.equal(h.run('queueState.status'),'WAITING');
});
test('existing hold bypasses admission even after selection expires',async()=>{
  const h=await queueHarness();h.run("queueState={status:'EXPIRED'}");
  h.setResponder(path=>path==='/me/tickets'?[{session_id:'q',reservation_id:'r',seat_id:'s',status:'HELD',hold_expires_at:new Date(Date.now()+100000).toISOString()}]:path.endsWith('/seats')?{server_time:new Date().toISOString(),items:[]}:{columns:1,rows:1,elements:[]});
  await h.run('availability()');assert.equal(h.requests.some(r=>r.path.includes('/queue/')),false);
  assert.equal(h.nodes['hold-panel'].hidden,false);assert.equal(h.nodes['queue-panel'].hidden,true);
});
test('leaving booking screen stops admission and returning does not auto rejoin',async()=>{
  const h=await queueHarness();h.run("queueSessionId='q'");h.setResponder(()=>queueResult('LEFT'));
  h.context.window.dispatchEvent({type:'labseat-screen',detail:'tickets-panel'});await h.flush();
  await h.run('availability()');assert.equal(h.nodes.session.value,'');
  assert.equal(h.requests.some(r=>r.path.endsWith('/join')),false);
});

test('an in-flight hold prevents automatic admission changes and duplicate hold requests',async()=>{
  const h=await queueHarness();let resolve;
  h.run(`queueState=${JSON.stringify(queueResult('ADMITTED',{admission_expires_at:new Date(Date.now()+120000).toISOString()}))};selectedSeat={id:'s',seat_code:'A01'}`);
  h.setResponder(path=>path==='/holds'?new Promise(done=>{resolve=done;}):path==='/me/tickets'?[]:{});
  const pending=h.nodes['hold-selected'].onclick();await h.flush();
  assert.equal(h.run('queueCanRun()'),false);assert.equal(h.nodes['hold-selected'].disabled,true);
  await h.nodes['hold-selected'].onclick();assert.equal(h.requests.filter(r=>r.path==='/holds').length,1);
  resolve({hold_id:'r',expires_at:new Date(Date.now()+180000).toISOString(),server_time:new Date().toISOString()});
  // Complete the ordinary availability path without creating a new admission.
  h.nodes.session.value='';await pending;assert.equal(h.run('holdBusy'),false);
});


test('ticket names and seat labels load without catalogue metadata or displaying internal codes',async()=>{
  const h=await harness();h.run('labs=[];allRooms=[];eventNames=new Map()');
  const before=h.requests.length;
  h.setResponder(path=>{assert.equal(path,'/me/tickets');return [{reservation_id:'reservation-uuid',session_id:'session-uuid',seat_id:'seat-uuid',ticket_code:'SECRET-QR-CODE',status:'CONFIRMED',event_name:'Đêm nhạc mùa hè',seat_code:'Khu A',start_at:'2026-12-01T12:00:00Z'}];});
  await h.run('tickets()');
  const card=h.nodes.tickets.children[0],copy=card.children.map(c=>c.textContent).join(' ');
  assert.equal(card.children.find(c=>c.className==='ticket-name').textContent,'Đêm nhạc mùa hè');
  assert.match(copy,/Vị trí: Khu A/);
  for(const code of ['SECRET-QR-CODE','session-uuid','seat-uuid','reservation-uuid'])assert.equal(copy.includes(code),false);
  assert.equal(card.children.find(c=>c.tag==='img').src,'/me/tickets/reservation-uuid/qr');
  assert.equal(h.requests.length,before+1);
});

test('ticket missing metadata never falls back to UUID text',async()=>{
  const h=await harness();h.run('labs=[];allRooms=[]');
  h.setResponder(()=>[{reservation_id:'r',session_id:'session-uuid',seat_id:'seat-uuid',status:'CANCELLED'}]);
  await h.run('tickets()');
  const copy=h.nodes.tickets.children[0].children.map(c=>c.textContent).join(' ');
  assert.match(copy,/Ca/);assert.equal(copy.includes('uuid'),false);
});

test('signup submits prelogin CSRF, refreshes identity and clears password fields',async()=>{
  const h=await harness();
  h.nodes.register.fields={username:'new-user',email:'new-user@example.test',password:'short',password_confirm:'short'};
  await h.nodes.register.onsubmit();
  const request=h.requests.find(r=>r.path==='/auth/register');
  assert.equal(request.headers['X-CSRF-Token'],'pre-value');
  assert.deepEqual(JSON.parse(request.body),{username:'new-user',email:'new-user@example.test',password:'short',password_confirm:'short'});
  assert.deepEqual(h.nodes.register.fields,{});
  assert.equal(h.nodes['register-submit'].disabled,false);
  assert.equal(h.nodes.notice.textContent,'Đã tạo tài khoản. Xác minh email để đăng kí ca.');
});

test('signup mismatch never sends account creation and preserves input',async()=>{
  const h=await harness();
  h.nodes.register.fields={username:'new-user',email:'new-user@example.test',password:'short',password_confirm:'different-password'};
  await h.nodes.register.onsubmit();
  assert.equal(h.requests.some(r=>r.path==='/auth/register'),false);
  assert.equal(h.nodes.notice.textContent,'Mật khẩu chưa khớp.');
  assert.equal(h.nodes.register.fields.username,'new-user');
});


test('profile reads private fields and saves with authenticated CSRF',async()=>{
  const h=await harness();const profile={full_name:'Nguyễn Văn An',cccd:'012345678901',phone:'',email:'an@example.test',profile_complete:true};
  h.setResponder(()=>profile);
  await h.run('loadProfile()');
  assert.equal(h.nodes['profile-form'].elements.cccd.value,'012345678901');
  assert.equal(h.nodes['profile-form'].elements.email.required,true);
  assert.equal(h.nodes['profile-form'].elements.phone.required,false);
  h.nodes['profile-form'].fields={full_name:profile.full_name,cccd:profile.cccd,phone:profile.phone,email:profile.email};
  await h.nodes['profile-form'].onsubmit();
  const req=h.requests.find(r=>r.path==='/me/profile'&&r.method==='PUT');
  assert.equal(req.headers['X-CSRF-Token'],'csrf-value');
  assert.equal(h.run('me.profile_complete'),true);
  assert.equal(h.nodes['profile-message'].textContent,'Đã lưu hồ sơ.');
  assert.equal(h.nodes['profile-save'].disabled,false);
});


test('late profile save cannot refill private fields after logout',async()=>{
  const h=await harness();let resolveSave;
  h.setResponder(()=>new Promise(resolve=>{resolveSave=resolve;}));
  h.nodes['profile-form'].fields={full_name:'Test',cccd:'012345678901',phone:'',email:'an@example.test'};
  const saving=h.nodes['profile-form'].onsubmit();
  h.run('profileRevision++;me=null;');
  resolveSave({full_name:'Test',cccd:'012345678901',phone:'',email:'an@example.test',profile_complete:true});await saving;
  assert.equal(h.nodes['profile-form'].elements.cccd.value,'');
  assert.equal(h.nodes['profile-message'].textContent,'');
});


test('account header uses full name, avatar and default person after logout or image failure',async()=>{
  const h=await harness();
  h.run("me={id:'u1',username:'student',full_name:'Nguyễn Thiện Tuấn',avatar_url:'/me/avatar?v=photo'};renderAccount();");
  assert.equal(h.nodes.identity.textContent,'Nguyễn Thiện Tuấn');
  assert.equal(h.nodes['account-avatar'].src,'/me/avatar?v=photo');
  assert.equal(h.nodes['account-toggle'].hidden,false);
  h.nodes['account-avatar'].onerror();assert.equal(h.nodes['account-avatar'].src,'/static/user-default.svg');
  h.run('me=null;renderAccount();');
  assert.equal(h.nodes['account-toggle'].hidden,true);
  assert.equal(h.nodes['account-menu'].hidden,true);
  assert.equal(h.nodes['profile-avatar'].src,'/static/user-default.svg');
});

test('availability polling keeps room nodes and reuses geometry until revision changes',async()=>{
  const h=await harness();h.run(`labs=${JSON.stringify([lab('s1')])}`);h.nodes.session.value='s1';let revision=1;
  h.setResponder(path=>path==='/me/tickets'?[]:path.endsWith('/seat-map')?{revision,columns:8,rows:12,elements:[{id:'room1',seat_id:'room1',seat_code:'Phòng A',kind:'seat',x:0,y:2,width:1,height:1}]}:{server_time:new Date().toISOString(),layout_revision:revision,items:[{id:'room1',seat_code:'Phòng A',available:true}]});
  await h.run('availability()');const original=h.nodes.seats.children[0];
  await h.run('availability()');assert.equal(h.nodes.seats.children[0],original);
  assert.equal(h.requests.filter(r=>r.path.endsWith('/seat-map')).length,1);
  revision=2;await h.run('availability()');assert.notEqual(h.nodes.seats.children[0],original);
  assert.equal(h.requests.filter(r=>r.path.endsWith('/seat-map')).length,2);
});

test('a slow background poll does not clear the visible room list while waiting',async()=>{
  const h=await harness();h.run(`labs=${JSON.stringify([lab('s1')])}`);h.nodes.session.value='s1';
  const result={server_time:new Date().toISOString(),layout_revision:1,items:[{id:'room1',seat_code:'Phòng A',available:true}]};
  h.setResponder(path=>path==='/me/tickets'?[]:path.endsWith('/seat-map')?{revision:1,columns:8,rows:12,elements:[{id:'room1',seat_id:'room1',seat_code:'Phòng A',kind:'seat',x:0,y:2,width:1,height:1}]}:result);
  await h.run('availability()');const original=h.nodes.seats.children[0];let resolve;
  h.setResponder(path=>path==='/me/tickets'?[]:new Promise(r=>{resolve=r;}));
  const poll=h.run('pollAvailability()');await h.run('pollAvailability()');
  assert.equal(h.nodes.seats.children[0],original);
  resolve(result);await poll;assert.equal(h.nodes.seats.children[0],original);
});

test('mutation retries reuse a key after uncertain failure and new intents get new keys',async()=>{
  const h=await harness();let attempts=0;
  h.setResponder(path=>{
    if(path==='/holds'&&++attempts===1)throw Error('response lost after commit');
    return {hold_id:'r1',expires_at:'2026-01-01T00:03:00Z'};
  });
  const call="api('/holds','POST',{session_id:'s1',seat_id:'a1'})";
  await assert.rejects(h.run(call),/response lost/);
  await h.run(call);
  await h.run(call);
  const writes=h.requests.filter(r=>r.path==='/holds');
  assert.match(writes[0].headers['Idempotency-Key'],/^[a-f0-9]{32}$/);
  assert.equal(writes[0].headers['Idempotency-Key'],writes[1].headers['Idempotency-Key']);
  assert.notEqual(writes[1].headers['Idempotency-Key'],writes[2].headers['Idempotency-Key']);
  assert.equal(writes[1].headers['X-CSRF-Token'],'csrf-value');
});

test('camera permission errors explain recovery and release the controls',async()=>{
  const h=await harness();h.context.navigator.mediaDevices={getUserMedia:async()=>{const e=new Error('private device error');e.name='NotAllowedError';throw e;}};
  await h.nodes.camera.onclick();
  assert.match(h.nodes['camera-status'].textContent,/cấp quyền camera/);
  assert.equal(h.nodes.camera.disabled,false);assert.equal(h.nodes['stop-camera'].disabled,false);
  assert.equal(h.requests.some(r=>r.path==='/admin/check-ins'),false);
});

test('camera blocks insecure origins before requesting device access',async()=>{
  const h=await harness();let calls=0;h.context.window.isSecureContext=false;
  h.context.navigator.mediaDevices={getUserMedia:async()=>{calls++;}};
  await h.nodes.camera.onclick();assert.equal(calls,0);assert.match(h.nodes['camera-status'].textContent,/HTTPS hoặc localhost/);
});

test('scanned ticket fills the form and stops the stream without auto check-in',async()=>{
  const h=await harness();let stopped=0;const code='synthetic-camera-ticket-1234567890';
  h.context.navigator.mediaDevices={getUserMedia:async()=>({getTracks:()=>[{stop:()=>stopped++}]})};
  h.context.window.BarcodeDetector=class{static async getSupportedFormats(){return ['qr_code'];}async detect(){return [{rawValue:code}];}};
  h.nodes.preview.videoWidth=640;h.nodes.preview.videoHeight=480;
  await h.nodes.camera.onclick();
  assert.equal(h.nodes['checkin-form'].elements.ticket_code.value,code);assert.equal(stopped,1);
  assert.equal(h.nodes.preview.srcObject,null);assert.equal(h.nodes.preview.hidden,true);
  assert.match(h.nodes['camera-status'].textContent,/tra cứu/);
  assert.equal(h.requests.some(r=>r.path==='/admin/check-ins'),false);
});

test('native decoder completion after stopping cannot fill a ticket',async()=>{
  const h=await harness();let finish,started;
  const detecting=new Promise(resolve=>{started=resolve;});
  h.context.navigator.mediaDevices={getUserMedia:async()=>({getTracks:()=>[{stop(){}}]})};
  h.context.window.BarcodeDetector=class{async detect(){started();return new Promise(resolve=>{finish=resolve;});}};
  h.nodes.preview.videoWidth=640;h.nodes.preview.videoHeight=480;
  const pending=h.nodes.camera.onclick();await detecting;h.nodes['stop-camera'].onclick();
  finish([{rawValue:'synthetic-late-ticket-1234567890'}]);await pending;
  assert.equal(h.nodes['checkin-form'].elements.ticket_code.value,'');
});

const inspectedTicket=(code,allowed=true,checked=false,name='Nguyễn Văn An')=>({
  ticket:{reservation_id:'fixture-registration',ticket_code:code,status:checked?'CHECKED_IN':'CONFIRMED',checked_in_at:checked?'2026-11-16T01:00:00Z':null},
  session:{id:'fixture-session',name:'Ca kiểm thử',room_name:'Khu thực hành',seat_code:'A101',start_at:'2026-11-20T01:00:00Z',end_at:'2026-11-20T03:00:00Z',checkin_enabled:allowed},
  profile:{username:'student',full_name:name,cccd:'012345678901',email:'an@example.test',phone:'',avatar_url:null},
  can_check_in:allowed&&!checked,reason:checked?'Vé đã được check-in.':allowed?'Vé hợp lệ.':'Ca chưa mở check-in.'
});

test('ticket lookup shows private profile and requires a separate check-in action',async()=>{
  const h=await harness(),code='lookup-ticket-fixture-1234567890';let checked=false;
  h.setResponder(path=>path==='/admin/check-ins/lookup'?inspectedTicket(code,true,checked):path==='/admin/check-ins'?(checked=true,{status:'CHECKED_IN'}):{});
  h.nodes['checkin-form'].elements.ticket_code.value=code;await h.nodes['checkin-form'].onsubmit();
  assert.equal(h.nodes['checkin-result'].hidden,false);assert.equal(h.nodes['checkin-confirm'].hidden,false);
  assert.ok(h.nodes['checkin-profile-info'].children.some(n=>n.textContent==='Nguyễn Văn An'));
  assert.equal(h.requests.some(r=>r.path==='/admin/check-ins'),false);
  await h.nodes['checkin-confirm'].onclick();
  assert.equal(h.requests.filter(r=>r.path==='/admin/check-ins').length,1);
  assert.equal(h.nodes['checkin-confirm'].hidden,true);
  assert.equal(h.nodes['checkin-decision'].textContent,'Vé đã được check-in.');
});

test('closed session hides check-in action but still shows ticket information',async()=>{
  const h=await harness(),code='closed-ticket-fixture-1234567890';h.setResponder(()=>inspectedTicket(code,false));
  h.nodes['checkin-form'].elements.ticket_code.value=code;await h.nodes['checkin-form'].onsubmit();
  assert.equal(h.nodes['checkin-result'].hidden,false);assert.equal(h.nodes['checkin-confirm'].hidden,true);
  await h.nodes['checkin-confirm'].onclick();assert.equal(h.requests.some(r=>r.path==='/admin/check-ins'),false);
});

test('late ticket lookup never exposes the previous registrant after input changes',async()=>{
  const h=await harness(),old='previous-ticket-fixture-1234567890',next='current-ticket-fixture-1234567890';let resolveOld;
  h.setResponder((path,request)=>JSON.parse(request.body).ticket_code===old?new Promise(resolve=>{resolveOld=resolve;}):inspectedTicket(next,true,false,'Người mới'));
  h.nodes['checkin-form'].elements.ticket_code.value=old;const pending=h.nodes['checkin-form'].onsubmit();
  h.nodes['checkin-form'].elements.ticket_code.value=next;h.nodes['checkin-form'].elements.ticket_code.oninput();
  await h.nodes['checkin-form'].onsubmit();resolveOld(inspectedTicket(old,true,false,'Người cũ'));await pending;
  assert.ok(h.nodes['checkin-profile-info'].children.some(n=>n.textContent==='Người mới'));
  assert.equal(h.nodes['checkin-profile-info'].children.some(n=>n.textContent==='Người cũ'),false);
});


test('unverified account banner follows identity and remains hidden for guests',async()=>{
  const h=await harness();
  h.run("me={id:'u1',username:'student',email_verified:false};renderAccount()");
  assert.equal(h.nodes['email-verification-banner'].hidden,false);
  h.run('me.email_verified=true;renderAccount()');
  assert.equal(h.nodes['email-verification-banner'].hidden,true);
  h.run('me=null;renderAccount()');
  assert.equal(h.nodes['email-verification-banner'].hidden,true);
});
