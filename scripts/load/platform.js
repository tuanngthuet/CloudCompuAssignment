// Synthetic acceptance only: 24 reads/s + 2 workflows/s × 3 writes = 30 requests/s.
import http from 'k6/http';
import { check } from 'k6';
import { SharedArray } from 'k6/data';
import { Rate, Trend } from 'k6/metrics';
if (!__ENV.BASE_URL || !__ENV.SESSION_ID || !__ENV.SESSIONS_FILE) throw Error('BASE_URL, SESSION_ID, SESSIONS_FILE required');
const identities = new SharedArray('private synthetic sessions', () => JSON.parse(open(__ENV.SESSIONS_FILE)));
if (identities.length < 100 || identities.some(x => !x.session_token || !x.csrf_token || !x.seat_id)) throw Error('Supply 100 distinct, verified synthetic user sessions with seat_id; never use real profiles');
const base=__ENV.BASE_URL.replace(/\/$/,''), sid=__ENV.SESSION_ID;
const failures=new Rate('platform_unexpected_failure'), reads=new Trend('platform_read_ms'), writes=new Trend('platform_write_ms');
export const options={
  scenarios:{
    reads:{executor:'constant-arrival-rate',rate:24,timeUnit:'1s',duration:'15m',preAllocatedVUs:60,maxVUs:60,exec:'read'},
    writes:{executor:'constant-arrival-rate',rate:2,timeUnit:'1s',duration:'15m',preAllocatedVUs:40,maxVUs:40,exec:'write'},
  },
  summaryTrendStats:['avg','med','p(95)','p(99)','max'],
  thresholds:{platform_unexpected_failure:['rate<0.01'],platform_read_ms:['p(95)<500'],platform_write_ms:['p(95)<1000'],dropped_iterations:['count==0']},
};
export function setup(){
  const r=http.get(base+'/lab-sessions');
  if(r.status!==200 || r.json().queue_policy.enabled)throw Error('This 30RPS scenario requires admission disabled; use booking.js for queue acceptance');
}
function identity(){const u=identities[(__VU-1)%identities.length];http.cookieJar().set(base,'labseat_session',u.session_token);return u;}
function accepted(r,expected,write=false){
  const ok=check(r,{'Expected status':x=>expected.includes(x.status)});failures.add(!ok);
  (write?writes:reads).add(r.timings.duration);return ok;
}
export function read(){identity();accepted(http.get(base+(__ITER%2?'/events':`/lab-sessions/${sid}/seats`)),[200]);}
export function write(){
  const u=identity(),params={headers:{'Content-Type':'application/json','X-CSRF-Token':u.csrf_token}};
  let r=http.post(base+'/holds',JSON.stringify({session_id:sid,seat_id:u.seat_id}),params);
  if(!accepted(r,[200],true))return;
  const id=r.json().hold_id;
  r=http.post(base+`/holds/${id}/confirm`,'{}',params);if(!accepted(r,[200],true))return;
  accepted(http.post(base+`/reservations/${id}/cancel`,'{}',params),[200],true);
}
