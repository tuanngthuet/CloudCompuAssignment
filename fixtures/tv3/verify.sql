-- Run after schema.sql against a disposable database.
-- Roll back all rows after exercising the reference constraints and lock order.
BEGIN;

DO $fixture$
DECLARE
    first_user uuid;
    second_user uuid;
    room uuid;
    first_seat uuid;
    second_seat uuid;
    session uuid;
    original_hold uuid;
    hold_deadline timestamptz;
    observed_at timestamptz;
    changed_rows integer;
    violated_constraint text;
BEGIN
    INSERT INTO users (role, password_hash)
        VALUES ('student', 'fixture-only-a') RETURNING id INTO first_user;
    INSERT INTO users (role, password_hash)
        VALUES ('student', 'fixture-only-b') RETURNING id INTO second_user;
    INSERT INTO rooms (name) VALUES ('Fixture room') RETURNING id INTO room;
    INSERT INTO seats (room_id, seat_code)
        VALUES (room, 'A1') RETURNING id INTO first_seat;
    INSERT INTO seats (room_id, seat_code)
        VALUES (room, 'A2') RETURNING id INTO second_seat;
    INSERT INTO lab_sessions (room_id, open_at, close_at, start_at, end_at)
        VALUES (room, now() - interval '1 hour', now() + interval '1 hour',
                now() + interval '2 hours', now() + interval '3 hours')
        RETURNING id INTO session;
    INSERT INTO session_seats (session_id, seat_id)
        VALUES (session, first_seat), (session, second_seat);

    -- The hold is already expired by wall clock but still occupies both indexes.
    INSERT INTO reservations (user_id, session_id, seat_id, status, hold_expires_at)
        VALUES (first_user, session, first_seat, 'HELD', now() - interval '1 second')
        RETURNING id INTO original_hold;

    BEGIN
        INSERT INTO reservations (user_id, session_id, seat_id, status, hold_expires_at)
            VALUES (first_user, session, second_seat, 'HELD', now() + interval '180 seconds');
        RAISE EXCEPTION 'Expected one hold per user and session';
    EXCEPTION WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS violated_constraint = CONSTRAINT_NAME;
        IF violated_constraint <> 'reservations_active_user_session' THEN
            RAISE;
        END IF;
    END;

    BEGIN
        INSERT INTO reservations (user_id, session_id, seat_id, status, hold_expires_at)
            VALUES (second_user, session, first_seat, 'HELD', now() + interval '180 seconds');
        RAISE EXCEPTION 'Expected one hold per seat and session';
    EXCEPTION WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS violated_constraint = CONSTRAINT_NAME;
        IF violated_constraint <> 'reservations_active_session_seat' THEN
            RAISE;
        END IF;
    END;

    -- The caller owns the transaction. Read the database clock after taking locks.
    PERFORM 1 FROM users WHERE id = second_user FOR UPDATE;
    SELECT close_at INTO hold_deadline FROM lab_sessions WHERE id = session FOR UPDATE;
    PERFORM 1 FROM session_seats WHERE session_id = session AND seat_id = first_seat FOR UPDATE;
    observed_at := clock_timestamp();
    UPDATE reservations
       SET status = 'EXPIRED'
     WHERE session_id = session AND status = 'HELD' AND hold_expires_at <= observed_at
       AND (user_id = second_user OR seat_id = first_seat);
    GET DIAGNOSTICS changed_rows = ROW_COUNT;
    IF changed_rows <> 1 OR NOT EXISTS (
        SELECT 1 FROM reservations WHERE id = original_hold AND status = 'EXPIRED'
    ) THEN
        RAISE EXCEPTION 'Expected expired hold to be retained in history';
    END IF;

    INSERT INTO reservations (user_id, session_id, seat_id, status, hold_expires_at)
        VALUES (second_user, session, first_seat, 'HELD',
                LEAST(hold_deadline, observed_at + interval '180 seconds'));
    RAISE NOTICE 'PASS: both partial unique indexes and expiry release';
END
$fixture$;

ROLLBACK;
