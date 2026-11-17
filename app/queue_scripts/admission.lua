-- One bounded, atomic operation per session. PostgreSQL still owns reservations.
local action, user, generation = ARGV[1], ARGV[2], ARGV[3]
local close_at, ttl_at = tonumber(ARGV[4]), tonumber(ARGV[5])
local capacity, duration, grace = tonumber(ARGV[6]), tonumber(ARGV[7]), tonumber(ARGV[8])
local epoch, version = ARGV[9], tonumber(ARGV[10])
local granted = {}
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local function failure(code) return cjson.encode({error=code}) end
local raw_ready = redis.call('GET', KEYS[1])
if not raw_ready then return failure('queue_unavailable') end
local ok, ready = pcall(cjson.decode, raw_ready)
local server = redis.call('INFO', 'server')
local run_id = string.match(server, 'run_id:([^\r\n]+)')
if not ok or ready.epoch ~= epoch or ready.version ~= version or ready.run_id ~= run_id then
    return failure('queue_unavailable')
end
if action == 'ready' then return cjson.encode({server_ms=now,status='READY'}) end
local expected = {'string','string','zset','zset','hash','zset'}
for i=2,6 do
    local kind=redis.call('TYPE',KEYS[i]).ok
    if kind ~= 'none' and kind ~= expected[i] then return failure('queue_unavailable') end
end
local function read_entry(id)
    local value=redis.call('HGET',KEYS[5],id)
    if not value then return nil end
    local valid, entry=pcall(cjson.decode,value)
    if not valid then return nil end
    return entry
end
local function write_entry(id,entry) redis.call('HSET',KEYS[5],id,cjson.encode(entry)) end
-- Keep reservations independent when registration closes; do not admit new viewers.
if now >= close_at then return cjson.encode({status=action=='leave' and 'LEFT' or 'CLOSED',server_ms=now}) end
-- Clean at most 100 expired slots and 100 abandoned waiters per call.
for _,id in ipairs(redis.call('ZRANGEBYSCORE',KEYS[4],'-inf',now,'LIMIT',0,100)) do
    local entry=read_entry(id)
    if entry and entry.status=='ADMITTED' then entry.status='EXPIRED';write_entry(id,entry) end
    redis.call('ZREM',KEYS[4],id)
end
for _,id in ipairs(redis.call('ZRANGEBYSCORE',KEYS[6],'-inf','('..(now-grace),'LIMIT',0,100)) do
    local entry=read_entry(id)
    if entry and entry.status=='WAITING' then entry.status='EXPIRED';write_entry(id,entry) end
    redis.call('ZREM',KEYS[3],id);redis.call('ZREM',KEYS[6],id)
end
if redis.call('ZCOUNT',KEYS[4],'-inf',now)>0 or redis.call('ZCOUNT',KEYS[6],'-inf','('..(now-grace))>0 then
    return failure('queue_capacity')
end
local entry=read_entry(user)
if action=='join' and (not entry or (entry.status~='WAITING' and entry.status~='ADMITTED')) then
    if redis.call('ZCARD',KEYS[3])>=1000 or redis.call('HLEN',KEYS[5])>=10000 then return failure('queue_capacity') end
    local sequence=redis.call('INCR',KEYS[2])
    entry={status='WAITING',generation=generation,sequence=sequence,last_seen=now,joined=now}
    write_entry(user,entry)
    redis.call('ZADD',KEYS[3],sequence,user);redis.call('ZADD',KEYS[6],now,user)
elseif action=='heartbeat' and entry and entry.status=='WAITING' then
    if not redis.call('ZSCORE',KEYS[3],user) or not redis.call('ZSCORE',KEYS[6],user) then return failure('queue_unavailable') end
    entry.last_seen=now;write_entry(user,entry);redis.call('ZADD',KEYS[6],now,user)
elseif action=='leave' then
    if entry then
        redis.call('ZREM',KEYS[3],user);redis.call('ZREM',KEYS[4],user);redis.call('ZREM',KEYS[6],user)
        entry.status='LEFT';write_entry(user,entry)
    end
elseif action=='consume' and entry and entry.generation==generation and entry.status=='ADMITTED' then
    entry.status='CONSUMED';write_entry(user,entry);redis.call('ZREM',KEYS[4],user)
end
-- Validate the caller's entry before granting anything after a partial script error.
entry=read_entry(user)
if entry and entry.status=='WAITING' and (not redis.call('ZSCORE',KEYS[3],user) or not redis.call('ZSCORE',KEYS[6],user)) then return failure('queue_unavailable') end
if entry and entry.status=='ADMITTED' then
    local deadline=redis.call('ZSCORE',KEYS[4],user)
    if not deadline or tonumber(deadline)~=entry.expires then return failure('queue_unavailable') end
end
if action~='guard' then
    local room=capacity-redis.call('ZCARD',KEYS[4])
    if room>0 then
        local first=redis.call('ZRANGE',KEYS[3],0,capacity-1)
        for _,id in ipairs(first) do
            if room<=0 then break end
            local candidate=read_entry(id)
            if not candidate then return failure('queue_unavailable') end
            if candidate.status=='ADMITTED' then
                -- A previous allocation may have committed before removing the waiting index.
                if not redis.call('ZSCORE',KEYS[4],id) then return failure('queue_unavailable') end
                redis.call('ZREM',KEYS[3],id);redis.call('ZREM',KEYS[6],id)
            elseif candidate.status=='WAITING' then
                local seen=redis.call('ZSCORE',KEYS[6],id)
                if not seen or tonumber(seen)<now-grace then return failure('queue_unavailable') end
                local expires=math.min(now+duration,close_at)
                -- Reserve the slot FIRST: a failed HSET can waste a slot, never grant an uncounted one.
                redis.call('ZADD',KEYS[4],expires,id)
                candidate.status='ADMITTED';candidate.expires=expires;write_entry(id,candidate)
                table.insert(granted,math.max(0,now-(candidate.joined or now)))
                redis.call('ZREM',KEYS[3],id);redis.call('ZREM',KEYS[6],id)
                room=room-1
            else return failure('queue_unavailable') end
        end
    end
end
for i=2,6 do if redis.call('EXISTS',KEYS[i])==1 then redis.call('PEXPIREAT',KEYS[i],ttl_at) end end
entry=read_entry(user)
if action=='leave' then return cjson.encode({status='LEFT',server_ms=now,granted_wait_ms=granted}) end
if not entry then return cjson.encode({status='NONE',server_ms=now,granted_wait_ms=granted}) end
local ahead=cjson.null
if entry.status=='WAITING' then ahead=redis.call('ZRANK',KEYS[3],user) end
return cjson.encode({status=entry.status,server_ms=now,number_ahead=ahead,expires_ms=entry.expires or cjson.null,generation=entry.generation,granted_wait_ms=granted})
