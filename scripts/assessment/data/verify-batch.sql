-- Run read-only with psql -v ON_ERROR_STOP=1 and CSV UUID lists from the private manifest:
-- -v user_ids=<users[].id> -v event_ids=<events[]> -v room_ids=<rooms[]> .
-- IDs, not editable names, define the batch scope; never derive these lists from name searches.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT role, count(*)
FROM users
WHERE id = ANY(string_to_array(:'user_ids', ',')::uuid[])
GROUP BY role ORDER BY role;

SELECT session_type, count(DISTINCT e.id) AS events, count(l.id) AS schedules
FROM events e LEFT JOIN lab_sessions l ON l.event_id = e.id
WHERE e.id = ANY(string_to_array(:'event_ids', ',')::uuid[])
GROUP BY session_type ORDER BY session_type;

SELECT count(*) AS image_maps, min(jsonb_array_length(layout->'elements')) AS smallest_map,
       max(jsonb_array_length(layout->'elements')) AS largest_map
FROM room_layouts m JOIN rooms r ON r.id = m.room_id
WHERE r.id = ANY(string_to_array(:'room_ids', ',')::uuid[]) AND layout->>'type' = 'image';

SELECT r.status, count(*)
FROM reservations r
JOIN users u ON u.id = r.user_id
JOIN lab_sessions l ON l.id = r.session_id
JOIN events e ON e.id = l.event_id
WHERE u.id = ANY(string_to_array(:'user_ids', ',')::uuid[])
  AND e.id = ANY(string_to_array(:'event_ids', ',')::uuid[])
GROUP BY r.status ORDER BY r.status;

SELECT j.status, count(*)
FROM email_jobs j
JOIN users u ON u.id = j.user_id
WHERE u.id = ANY(string_to_array(:'user_ids', ',')::uuid[]) AND j.reservation_id IS NOT NULL
GROUP BY j.status ORDER BY j.status;
COMMIT;
