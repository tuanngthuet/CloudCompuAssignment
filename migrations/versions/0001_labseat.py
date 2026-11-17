"""LABSEAT schema baseline, frozen independently of runtime ORM models."""

import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_labseat"
down_revision = None
branch_labels = None
depends_on = None


CHECK_EXPRESSIONS = {
    "booking_queue_settings": {
        "queue_capacity_range": "capacity >= 1 AND capacity <= 100",
        "queue_grace_range": "waiting_grace_seconds > heartbeat_seconds AND "
        "waiting_grace_seconds <= 600",
        "queue_heartbeat_range": "heartbeat_seconds >= 1 AND heartbeat_seconds <= 30",
        "queue_selection_range": "selection_seconds >= 1 AND selection_seconds <= 600",
        "queue_singleton": "id = 1",
    },
    "events": {
        "session_type_values": "session_type IS NULL OR (session_type::text = ANY "
        "(ARRAY['exam'::character varying, 'practice'::character "
        "varying]::text[]))"
    },
    "lab_sessions": {
        "lab_sessions_check": "open_at < close_at AND close_at <= start_at AND start_at "
        "< end_at"
    },
    "notification_deliveries": {
        "notification_status": "status::text = ANY "
        "(ARRAY['PENDING'::character varying, "
        "'SENT'::character varying, "
        "'SKIPPED'::character varying]::text[])"
    },
    "reservations": {
        "reservation_slot_nonnegative": "slot >= 0",
        "reservations_check": "(status::text <> ALL (ARRAY['CONFIRMED'::character "
        "varying, 'CHECKED_IN'::character varying]::text[])) OR "
        "ticket_code IS NOT NULL",
        "reservations_check1": "status::text = 'CHECKED_IN'::text) = (checked_in_at IS "
        "NOT NULL",
        "reservations_status_check": "status::text = ANY (ARRAY['HELD'::character "
        "varying, 'CONFIRMED'::character varying, "
        "'CHECKED_IN'::character varying, "
        "'EXPIRED'::character varying, "
        "'CANCELLED'::character varying]::text[])",
    },
    "seats": {"seat_capacity_range": "capacity >= 1 AND capacity <= 100000"},
    "users": {
        "users_role_check": "role::text = ANY (ARRAY['student'::character varying, "
        "'admin'::character varying]::text[])"
    },
}


INDEX_PREDICATES = {
    "ix_outbox_pending": "(published_at IS NULL)",
    "uq_active_seat_session": "((status)::text = ANY ((ARRAY['HELD'::character varying, "
    "'CONFIRMED'::character varying, 'CHECKED_IN'::character "
    "varying])::text[]))",
    "uq_active_user_session": "((status)::text = ANY ((ARRAY['HELD'::character varying, "
    "'CONFIRMED'::character varying, 'CHECKED_IN'::character "
    "varying])::text[]))",
}


def definitions(operations):
    operations.create_table(
        "booking_queue_settings",
        sa.Column("id", sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column("enabled", sa.BOOLEAN(), autoincrement=False, nullable=False),
        sa.Column(
            "recovery_pending", sa.BOOLEAN(), autoincrement=False, nullable=False
        ),
        sa.Column("policy_version", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("epoch", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("capacity", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column(
            "selection_seconds", sa.INTEGER(), autoincrement=False, nullable=False
        ),
        sa.Column(
            "heartbeat_seconds", sa.INTEGER(), autoincrement=False, nullable=False
        ),
        sa.Column(
            "waiting_grace_seconds", sa.INTEGER(), autoincrement=False, nullable=False
        ),
        sa.Column(
            "recovery_not_before",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "updated_by", sa.VARCHAR(length=100), autoincrement=False, nullable=False
        ),
        sa.CheckConstraint(
            "capacity >= 1 AND capacity <= 100", name="queue_capacity_range"
        ),
        sa.CheckConstraint(
            "heartbeat_seconds >= 1 AND heartbeat_seconds <= 30",
            name="queue_heartbeat_range",
        ),
        sa.CheckConstraint("id = 1", name="queue_singleton"),
        sa.CheckConstraint(
            "selection_seconds >= 1 AND selection_seconds <= 600",
            name="queue_selection_range",
        ),
        sa.CheckConstraint(
            "waiting_grace_seconds > heartbeat_seconds AND waiting_grace_seconds <= 600",
            name="queue_grace_range",
        ),
        sa.PrimaryKeyConstraint("id", name="booking_queue_settings_pkey"),
    )
    operations.create_table(
        "events",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("name", sa.VARCHAR(length=100), autoincrement=False, nullable=False),
        sa.Column("description", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column("venue", sa.VARCHAR(length=120), autoincrement=False, nullable=False),
        sa.Column(
            "address", sa.VARCHAR(length=300), autoincrement=False, nullable=False
        ),
        sa.Column("poster_key", sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column(
            "session_type", sa.VARCHAR(length=10), autoincrement=False, nullable=True
        ),
        sa.CheckConstraint(
            "session_type IS NULL OR (session_type::text = ANY (ARRAY['exam'::character varying, 'practice'::character varying]::text[]))",
            name="session_type_values",
        ),
        sa.PrimaryKeyConstraint("id", name="events_pkey"),
        postgresql_ignore_search_path=False,
    )
    operations.create_table(
        "queue_policy_events",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("actor", sa.VARCHAR(length=100), autoincrement=False, nullable=False),
        sa.Column(
            "reason", sa.VARCHAR(length=500), autoincrement=False, nullable=False
        ),
        sa.Column(
            "before",
            postgresql.JSONB(astext_type=sa.Text()),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "after",
            postgresql.JSONB(astext_type=sa.Text()),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="queue_policy_events_pkey"),
    )
    operations.create_table(
        "rooms",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("name", sa.VARCHAR(length=120), autoincrement=False, nullable=False),
        sa.Column("image_key", sa.TEXT(), autoincrement=False, nullable=True),
        sa.PrimaryKeyConstraint("id", name="rooms_pkey"),
        postgresql_ignore_search_path=False,
    )
    operations.create_table(
        "users",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column(
            "username", sa.VARCHAR(length=100), autoincrement=False, nullable=False
        ),
        sa.Column("password_hash", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column("role", sa.VARCHAR(length=20), autoincrement=False, nullable=False),
        sa.Column(
            "full_name",
            sa.VARCHAR(length=150),
            server_default=sa.text("''::character varying"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "cccd",
            sa.VARCHAR(length=12),
            server_default=sa.text("''::character varying"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "phone",
            sa.VARCHAR(length=20),
            server_default=sa.text("''::character varying"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "email",
            sa.VARCHAR(length=254),
            server_default=sa.text("''::character varying"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("avatar_key", sa.TEXT(), autoincrement=False, nullable=True),
        sa.CheckConstraint(
            "role::text = ANY (ARRAY['student'::character varying, 'admin'::character varying]::text[])",
            name="users_role_check",
        ),
        sa.PrimaryKeyConstraint("id", name="users_pkey"),
        sa.UniqueConstraint("username", name="users_username_key"),
        postgresql_ignore_search_path=False,
    )
    operations.create_table(
        "idempotency_records",
        sa.Column("user_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column(
            "key_hash", sa.VARCHAR(length=64), autoincrement=False, nullable=False
        ),
        sa.Column(
            "fingerprint", sa.VARCHAR(length=64), autoincrement=False, nullable=False
        ),
        sa.Column(
            "response",
            postgresql.JSONB(astext_type=sa.Text()),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="idempotency_records_user_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "key_hash", name="idempotency_records_pkey"),
    )
    operations.create_table(
        "lab_sessions",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("room_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column(
            "open_at",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "close_at",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "start_at",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "end_at",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("event_id", sa.UUID(), autoincrement=False, nullable=True),
        sa.Column(
            "checkin_enabled",
            sa.BOOLEAN(),
            server_default=sa.text("false"),
            autoincrement=False,
            nullable=False,
        ),
        sa.CheckConstraint(
            "open_at < close_at AND close_at <= start_at AND start_at < end_at",
            name="lab_sessions_check",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name="lab_sessions_event_id_fkey",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["room_id"], ["rooms.id"], name="lab_sessions_room_id_fkey"
        ),
        sa.PrimaryKeyConstraint("id", name="lab_sessions_pkey"),
        postgresql_ignore_search_path=False,
    )
    operations.create_index(
        "ix_lab_sessions_event_id",
        "lab_sessions",
        ["event_id"],
        unique=False,
        postgresql_include=[],
    )
    operations.create_table(
        "login_sessions",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("user_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column(
            "token_hash", sa.VARCHAR(length=64), autoincrement=False, nullable=False
        ),
        sa.Column(
            "csrf_hash", sa.VARCHAR(length=64), autoincrement=False, nullable=False
        ),
        sa.Column(
            "expires_at",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="login_sessions_user_id_fkey"
        ),
        sa.PrimaryKeyConstraint("id", name="login_sessions_pkey"),
        sa.UniqueConstraint("token_hash", name="login_sessions_token_hash_key"),
    )
    operations.create_table(
        "room_layouts",
        sa.Column("room_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("revision", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column(
            "layout",
            postgresql.JSONB(astext_type=sa.Text()),
            autoincrement=False,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["room_id"],
            ["rooms.id"],
            name="room_layouts_room_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("room_id", name="room_layouts_pkey"),
    )
    operations.create_table(
        "seats",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("room_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column(
            "seat_code", sa.VARCHAR(length=30), autoincrement=False, nullable=False
        ),
        sa.Column(
            "capacity",
            sa.INTEGER(),
            server_default=sa.text("1"),
            autoincrement=False,
            nullable=False,
        ),
        sa.CheckConstraint(
            "capacity >= 1 AND capacity <= 100000", name="seat_capacity_range"
        ),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], name="seats_room_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="seats_pkey"),
        sa.UniqueConstraint("room_id", "seat_code", name="seats_room_id_seat_code_key"),
        postgresql_ignore_search_path=False,
    )
    operations.create_table(
        "checkin_policy_events",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("session_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("actor_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("enabled", sa.BOOLEAN(), autoincrement=False, nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name="checkin_policy_events_actor_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["lab_sessions.id"],
            name="checkin_policy_events_session_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="checkin_policy_events_pkey"),
    )
    operations.create_index(
        "ix_checkin_policy_events_session_id",
        "checkin_policy_events",
        ["session_id"],
        unique=False,
        postgresql_include=[],
    )
    operations.create_table(
        "session_seats",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("session_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("seat_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["seat_id"], ["seats.id"], name="session_seats_seat_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["lab_sessions.id"], name="session_seats_session_id_fkey"
        ),
        sa.PrimaryKeyConstraint("id", name="session_seats_pkey"),
        sa.UniqueConstraint(
            "session_id", "seat_id", name="session_seats_session_id_seat_id_key"
        ),
        postgresql_ignore_search_path=False,
    )
    operations.create_table(
        "reservations",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("user_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("session_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("seat_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("status", sa.VARCHAR(length=20), autoincrement=False, nullable=False),
        sa.Column(
            "hold_expires_at",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "ticket_code", sa.VARCHAR(length=100), autoincrement=False, nullable=True
        ),
        sa.Column(
            "checked_in_at",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            "slot",
            sa.INTEGER(),
            server_default=sa.text("0"),
            autoincrement=False,
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status::text <> ALL (ARRAY['CONFIRMED'::character varying, 'CHECKED_IN'::character varying]::text[])) OR ticket_code IS NOT NULL",
            name="reservations_check",
        ),
        sa.CheckConstraint(
            "(status::text = 'CHECKED_IN'::text) = (checked_in_at IS NOT NULL)",
            name="reservations_check1",
        ),
        sa.CheckConstraint(
            "status::text = ANY (ARRAY['HELD'::character varying, 'CONFIRMED'::character varying, 'CHECKED_IN'::character varying, 'EXPIRED'::character varying, 'CANCELLED'::character varying]::text[])",
            name="reservations_status_check",
        ),
        sa.CheckConstraint("slot >= 0", name="reservation_slot_nonnegative"),
        sa.ForeignKeyConstraint(
            ["seat_id"], ["seats.id"], name="reservations_seat_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "seat_id"],
            ["session_seats.session_id", "session_seats.seat_id"],
            name="reservations_session_id_seat_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["lab_sessions.id"], name="reservations_session_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="reservations_user_id_fkey"
        ),
        sa.PrimaryKeyConstraint("id", name="reservations_pkey"),
        sa.UniqueConstraint("ticket_code", name="reservations_ticket_code_key"),
        postgresql_ignore_search_path=False,
    )
    operations.create_index(
        "uq_active_seat_session",
        "reservations",
        ["seat_id", "session_id", "slot"],
        unique=True,
        postgresql_where="status IN ('HELD','CONFIRMED','CHECKED_IN')",
    )
    operations.create_index(
        "uq_active_user_session",
        "reservations",
        ["user_id", "session_id"],
        unique=True,
        postgresql_where="status IN ('HELD','CONFIRMED','CHECKED_IN')",
    )
    operations.create_table(
        "audit_events",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("actor_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("reservation_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("action", sa.VARCHAR(length=30), autoincrement=False, nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name="audit_events_actor_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["reservations.id"],
            name="audit_events_reservation_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="audit_events_pkey"),
    )
    operations.create_table(
        "notification_deliveries",
        sa.Column("reservation_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column(
            "notification_type",
            sa.VARCHAR(length=60),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.VARCHAR(length=20),
            server_default=sa.text("'PENDING'::character varying"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "provider_message_id",
            sa.VARCHAR(length=254),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            "completed_at",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=True,
        ),
        sa.CheckConstraint(
            "status::text = ANY (ARRAY['PENDING'::character varying, 'SENT'::character varying, 'SKIPPED'::character varying]::text[])",
            name="notification_status",
        ),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["reservations.id"],
            name="notification_deliveries_reservation_id_fkey",
        ),
        sa.PrimaryKeyConstraint(
            "reservation_id", "notification_type", name="notification_deliveries_pkey"
        ),
    )
    operations.create_table(
        "outbox_events",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("reservation_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column(
            "event_type", sa.VARCHAR(length=60), autoincrement=False, nullable=False
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "published_at",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            "attempts",
            sa.INTEGER(),
            server_default=sa.text("0"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "available_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["reservations.id"],
            name="outbox_events_reservation_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="outbox_events_pkey"),
        sa.UniqueConstraint(
            "reservation_id", "event_type", name="uq_outbox_reservation_event"
        ),
    )
    operations.create_index(
        "ix_outbox_pending",
        "outbox_events",
        ["available_at"],
        unique=False,
        postgresql_where="(published_at IS NULL)",
        postgresql_include=[],
    )


class _Definition:
    """Build metadata from these same frozen DDL definitions without executing SQL."""

    def __init__(self):
        self.metadata = sa.MetaData()

    def create_table(self, name, *items, **options):
        return sa.Table(name, self.metadata, *items, **options)

    def create_index(self, name, table_name, columns, **options):
        if isinstance(options.get("postgresql_where"), str):
            options["postgresql_where"] = sa.text(options["postgresql_where"])
        return sa.Index(
            name,
            *(self.metadata.tables[table_name].c[column] for column in columns),
            **options,
        )


def schema():
    definition = _Definition()
    definitions(definition)
    return definition.metadata


def upgrade():
    definitions(op)
    policy = sa.table(
        "booking_queue_settings",
        sa.column("id", sa.Integer()),
        sa.column("enabled", sa.Boolean()),
        sa.column("recovery_pending", sa.Boolean()),
        sa.column("policy_version", sa.Integer()),
        sa.column("epoch", postgresql.UUID()),
        sa.column("capacity", sa.Integer()),
        sa.column("selection_seconds", sa.Integer()),
        sa.column("heartbeat_seconds", sa.Integer()),
        sa.column("waiting_grace_seconds", sa.Integer()),
        sa.column("updated_by", sa.String()),
    )
    op.bulk_insert(
        policy,
        [
            dict(
                id=1,
                enabled=False,
                recovery_pending=False,
                policy_version=1,
                epoch=uuid.uuid4(),
                capacity=10,
                selection_seconds=120,
                heartbeat_seconds=5,
                waiting_grace_seconds=60,
                updated_by="migration",
            )
        ],
    )


def downgrade():
    for table in (
        "outbox_events",
        "notification_deliveries",
        "audit_events",
        "reservations",
        "session_seats",
        "checkin_policy_events",
        "seats",
        "room_layouts",
        "login_sessions",
        "lab_sessions",
        "idempotency_records",
        "users",
        "rooms",
        "queue_policy_events",
        "events",
        "booking_queue_settings",
    ):
        op.drop_table(table)
