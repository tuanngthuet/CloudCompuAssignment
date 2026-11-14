-- Read-only checks. Match table/column names with the app release manifest first.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

WITH check_time AS (SELECT clock_timestamp() AS checked_at),
effective AS (
    SELECT r.user_id, r.session_id, r.seat_id
    FROM reservations AS r
    CROSS JOIN check_time AS t
    WHERE r.status IN ('CONFIRMED', 'CHECKED_IN')
       OR (r.status = 'HELD' AND r.hold_expires_at > t.checked_at)
)
SELECT 'one_effective_registration_per_user_session' AS invariant,
       session_id, user_id AS subject_id, count(*) AS registrations
FROM effective
GROUP BY session_id, user_id
HAVING count(*) > 1
UNION ALL
SELECT 'one_effective_registration_per_seat_session',
       session_id, seat_id, count(*)
FROM effective
GROUP BY session_id, seat_id
HAVING count(*) > 1
ORDER BY invariant, session_id, subject_id;

-- Expired HELD rows may remain until the next relevant write.
-- A null deadline is a finding. A due row is a diagnostic, not a duplicate.
WITH check_time AS (SELECT clock_timestamp() AS checked_at)
SELECT r.id, r.session_id, r.seat_id, r.hold_expires_at, t.checked_at,
       CASE WHEN r.hold_expires_at IS NULL THEN 'MISSING_DEADLINE'
            ELSE 'DUE_FOR_EXPIRY'
       END AS finding
FROM reservations AS r
CROSS JOIN check_time AS t
WHERE r.status = 'HELD'
  AND (r.hold_expires_at IS NULL OR r.hold_expires_at <= t.checked_at)
ORDER BY r.hold_expires_at, r.id;

COMMIT;
