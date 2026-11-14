-- Reference schema for a disposable PostgreSQL database.
BEGIN;

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    role text NOT NULL CHECK (role IN ('student', 'admin')),
    password_hash text NOT NULL
);

CREATE TABLE login_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users (id),
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL
);

CREATE TABLE rooms (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    image_key text
);

CREATE TABLE seats (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id uuid NOT NULL REFERENCES rooms (id),
    seat_code text NOT NULL,
    UNIQUE (room_id, seat_code)
);

CREATE TABLE lab_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id uuid NOT NULL REFERENCES rooms (id),
    open_at timestamptz NOT NULL,
    close_at timestamptz NOT NULL,
    start_at timestamptz NOT NULL,
    end_at timestamptz NOT NULL,
    CHECK (open_at < close_at AND close_at <= start_at AND start_at < end_at)
);

CREATE TABLE session_seats (
    session_id uuid REFERENCES lab_sessions (id),
    seat_id uuid REFERENCES seats (id),
    PRIMARY KEY (session_id, seat_id)
);

CREATE TABLE reservations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users (id),
    session_id uuid NOT NULL,
    seat_id uuid NOT NULL,
    status text NOT NULL CHECK (status IN ('HELD', 'CONFIRMED', 'CHECKED_IN', 'EXPIRED', 'CANCELLED')),
    hold_expires_at timestamptz NOT NULL,
    ticket_code text UNIQUE,
    checked_in_at timestamptz,
    FOREIGN KEY (session_id, seat_id) REFERENCES session_seats (session_id, seat_id),
    CHECK (status NOT IN ('CONFIRMED', 'CHECKED_IN') OR ticket_code IS NOT NULL),
    CHECK ((status = 'CHECKED_IN') = (checked_in_at IS NOT NULL))
);

CREATE UNIQUE INDEX reservations_active_user_session
    ON reservations (user_id, session_id)
    WHERE status IN ('HELD', 'CONFIRMED', 'CHECKED_IN');

CREATE UNIQUE INDEX reservations_active_session_seat
    ON reservations (session_id, seat_id)
    WHERE status IN ('HELD', 'CONFIRMED', 'CHECKED_IN');

CREATE TABLE audit_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id uuid NOT NULL REFERENCES users (id),
    reservation_id uuid REFERENCES reservations (id),
    action text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

COMMIT;
