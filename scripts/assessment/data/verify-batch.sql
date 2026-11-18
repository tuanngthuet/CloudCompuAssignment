-- Run with psql -v ON_ERROR_STOP=1 -v batch_prefix=b1-<batch>.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT role, count(*)
FROM users
WHERE starts_with(username, :'batch_prefix' || '-')
GROUP BY role ORDER BY role;

SELECT session_type, count(DISTINCT e.id) AS events, count(l.id) AS schedules
FROM events e LEFT JOIN lab_sessions l ON l.event_id = e.id
WHERE starts_with(e.name, '[' || :'batch_prefix' || '] ')
GROUP BY session_type ORDER BY session_type;

SELECT count(*) AS image_maps, min(jsonb_array_length(layout->'elements')) AS smallest_map,
       max(jsonb_array_length(layout->'elements')) AS largest_map
FROM room_layouts m JOIN rooms r ON r.id = m.room_id
WHERE starts_with(r.name, '[' || :'batch_prefix' || '] ') AND layout->>'type' = 'image';

SELECT r.status, count(*)
FROM reservations r
JOIN users u ON u.id = r.user_id
JOIN lab_sessions l ON l.id = r.session_id
JOIN events e ON e.id = l.event_id
WHERE starts_with(u.username, :'batch_prefix' || '-')
  AND starts_with(e.name, '[' || :'batch_prefix' || '] ')
GROUP BY r.status ORDER BY r.status;

SELECT j.status, count(*)
FROM email_jobs j
JOIN users u ON u.id = j.user_id
WHERE starts_with(u.username, :'batch_prefix' || '-') AND j.reservation_id IS NOT NULL
GROUP BY j.status ORDER BY j.status;
COMMIT;
