-- Read-only LABSEAT capacity, slot and ticket invariants; every query must return zero rows.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
-- Each query must return zero rows. Run against app schema after concurrency tests.
SELECT r.session_id, r.seat_id, count(*)
FROM reservations r JOIN seats s ON s.id=r.seat_id
WHERE r.status IN ('CONFIRMED','CHECKED_IN') OR (r.status='HELD' AND r.hold_expires_at>clock_timestamp())
GROUP BY r.session_id, r.seat_id, s.capacity HAVING count(*) > s.capacity;
SELECT session_id, seat_id, slot, count(*)
FROM reservations WHERE status IN ('HELD','CONFIRMED','CHECKED_IN')
GROUP BY session_id, seat_id, slot HAVING count(*) > 1;
SELECT r.id FROM reservations r JOIN seats s ON s.id=r.seat_id
WHERE r.slot < 0 OR r.slot >= s.capacity;
SELECT session_id, user_id, count(*)
FROM reservations WHERE status IN ('HELD','CONFIRMED','CHECKED_IN')
GROUP BY session_id, user_id HAVING count(*) > 1;
SELECT id FROM reservations
WHERE status IN ('CONFIRMED','CHECKED_IN') AND ticket_code IS NULL;
SELECT id FROM reservations
WHERE (status='CHECKED_IN') <> (checked_in_at IS NOT NULL);

SELECT l.event_id, r.user_id, count(*) FROM reservations r
JOIN lab_sessions l ON l.id=r.session_id
WHERE l.event_id IS NOT NULL AND (r.status IN ('CONFIRMED','CHECKED_IN') OR (r.status='HELD' AND r.hold_expires_at>clock_timestamp()))
GROUP BY l.event_id, r.user_id HAVING count(*) > 1;

COMMIT;
