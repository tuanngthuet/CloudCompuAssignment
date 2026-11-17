import uuid
from datetime import datetime
from sqlalchemy import Boolean, Integer, String, ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, Index, DateTime, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.session import Base

class Identity:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

class User(Identity, Base):
    __tablename__ = 'users'
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default='student')
    avatar_key: Mapped[str | None] = mapped_column(Text)
    full_name: Mapped[str] = mapped_column(String(150), default='', server_default='')
    cccd: Mapped[str] = mapped_column(String(12), default='', server_default='')
    phone: Mapped[str] = mapped_column(String(20), default='', server_default='')
    email: Mapped[str] = mapped_column(String(254), default='', server_default='')
    status: Mapped[str] = mapped_column(String(20), default='ACTIVE', server_default='ACTIVE')
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pending_email: Mapped[str | None] = mapped_column(String(254))
    email_version: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    anonymization_notice_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anonymization_notice_delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("role IN ('student','staff','admin')", name='users_role_check'),
        CheckConstraint("status IN ('ACTIVE','LOCKED','ANONYMIZED')", name='users_status_check'),
        Index('uq_users_email', func.lower(func.btrim(email)), unique=True, postgresql_where=text("email <> ''")),
        Index('uq_users_cccd', 'cccd', unique=True, postgresql_where=text("cccd <> ''")),
    )

class LoginSession(Identity, Base):
    __tablename__ = 'login_sessions'
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class Room(Identity, Base):
    __tablename__ = 'rooms'
    name: Mapped[str] = mapped_column(String(120))
    image_key: Mapped[str | None] = mapped_column(Text)

class Seat(Identity, Base):
    __tablename__ = 'seats'
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('rooms.id'))
    seat_code: Mapped[str] = mapped_column(String(30))
    capacity: Mapped[int] = mapped_column(Integer, default=1, server_default='1')
    __table_args__ = (UniqueConstraint('room_id', 'seat_code'), CheckConstraint('capacity >= 1 AND capacity <= 100000', name='seat_capacity_range'))

class Event(Identity, Base):
    __tablename__ = 'events'
    name: Mapped[str] = mapped_column(String(100))
    session_type: Mapped[str | None] = mapped_column(String(10))
    __table_args__ = (CheckConstraint("session_type IS NULL OR session_type IN ('exam','practice')", name='session_type_values'),)
    description: Mapped[str] = mapped_column(Text, default='')
    venue: Mapped[str] = mapped_column(String(120), default='')
    address: Mapped[str] = mapped_column(String(300), default='')
    poster_key: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='ACTIVE', server_default='ACTIVE')
    lifecycle_reason: Mapped[str] = mapped_column(String(500), default='', server_default='')
    lifecycle_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lifecycle_actor: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id'))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id'))
    cancellation_reason: Mapped[str] = mapped_column(String(500), default='', server_default='')

class LabSession(Identity, Base):
    __tablename__ = 'lab_sessions'
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('events.id', ondelete='SET NULL'), index=True)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('rooms.id'))
    checkin_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text('false'))
    checkin_close_mode: Mapped[str] = mapped_column(String(10), default='end_at', server_default='end_at')
    checkin_closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checkin_revision: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    open_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    close_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint('open_at < close_at AND close_at <= start_at AND start_at < end_at'),)

class SessionSeat(Identity, Base):
    __tablename__ = 'session_seats'
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('lab_sessions.id'))
    seat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('seats.id'))
    __table_args__ = (UniqueConstraint('session_id','seat_id'),)

class Reservation(Identity, Base):
    slot: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    __tablename__ = 'reservations'
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'))
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('lab_sessions.id'))
    seat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('seats.id'))
    status: Mapped[str] = mapped_column(String(20))
    hold_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ticket_code: Mapped[str | None] = mapped_column(String(100), unique=True)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(['session_id','seat_id'], ['session_seats.session_id','session_seats.seat_id']),
        CheckConstraint("status IN ('HELD','CONFIRMED','CHECKED_IN','EXPIRED','CANCELLED')"),
        CheckConstraint("status NOT IN ('CONFIRMED','CHECKED_IN') OR ticket_code IS NOT NULL"),
        CheckConstraint("(status = 'CHECKED_IN') = (checked_in_at IS NOT NULL)"),
        Index('uq_active_user_session', 'user_id','session_id', unique=True, postgresql_where=text("status IN ('HELD','CONFIRMED','CHECKED_IN')")),
        CheckConstraint('slot >= 0', name='reservation_slot_nonnegative'),
        Index('uq_active_seat_session', 'seat_id','session_id','slot', unique=True, postgresql_where=text("status IN ('HELD','CONFIRMED','CHECKED_IN')")),
    )

class AuditEvent(Identity, Base):
    __tablename__ = 'audit_events'
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'))
    reservation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('reservations.id'))
    action: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())

from sqlalchemy.dialects.postgresql import JSONB
class RoomLayout(Base):
    __tablename__ = 'room_layouts'
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('rooms.id',ondelete='CASCADE'),primary_key=True)
    revision: Mapped[int] = mapped_column(default=1)
    layout: Mapped[dict] = mapped_column(JSONB)


class QueueSettings(Base):
    __tablename__ = 'booking_queue_settings'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    recovery_pending: Mapped[bool] = mapped_column(Boolean, default=False)
    policy_version: Mapped[int] = mapped_column(Integer, default=1)
    epoch: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4)
    capacity: Mapped[int] = mapped_column(Integer, default=10)
    selection_seconds: Mapped[int] = mapped_column(Integer, default=120)
    heartbeat_seconds: Mapped[int] = mapped_column(Integer, default=5)
    waiting_grace_seconds: Mapped[int] = mapped_column(Integer, default=60)
    recovery_not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_by: Mapped[str] = mapped_column(String(100), default='migration')
    __table_args__ = (
        CheckConstraint('id = 1', name='queue_singleton'),
        CheckConstraint('capacity BETWEEN 1 AND 100', name='queue_capacity_range'),
        CheckConstraint('selection_seconds BETWEEN 1 AND 600', name='queue_selection_range'),
        CheckConstraint('heartbeat_seconds BETWEEN 1 AND 30', name='queue_heartbeat_range'),
        CheckConstraint('waiting_grace_seconds > heartbeat_seconds AND waiting_grace_seconds <= 600', name='queue_grace_range'),
    )


class QueuePolicyEvent(Identity, Base):
    __tablename__ = 'queue_policy_events'
    actor: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str] = mapped_column(String(500))
    before: Mapped[dict] = mapped_column(JSONB)
    after: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IdempotencyRecord(Base):
    """Committed mutation response, scoped to authenticated user and hashed key."""
    __tablename__ = 'idempotency_records'
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())


class OutboxEvent(Identity, Base):
    __tablename__ = 'outbox_events'
    reservation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('reservations.id'))
    event_type: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    __table_args__ = (
        UniqueConstraint('reservation_id', 'event_type', name='uq_outbox_reservation_event'),
        Index('ix_outbox_pending', 'available_at', postgresql_where=text('published_at IS NULL')),
    )


class NotificationDelivery(Base):
    __tablename__ = 'notification_deliveries'
    reservation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('reservations.id'), primary_key=True)
    notification_type: Mapped[str] = mapped_column(String(60), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default='PENDING', server_default='PENDING')
    provider_message_id: Mapped[str | None] = mapped_column(String(254))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("status IN ('PENDING','SENT','SKIPPED')", name='notification_status'),)


class CheckinPolicyEvent(Identity, Base):
    __tablename__ = 'checkin_policy_events'
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('lab_sessions.id', ondelete='CASCADE'), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id'))
    enabled: Mapped[bool] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(String(20), default='manual', server_default='manual')
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())


class StaffAssignment(Base):
    __tablename__ = 'staff_assignments'
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('lab_sessions.id', ondelete='CASCADE'), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    assigned_by: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())


class AdminAudit(Identity, Base):
    __tablename__ = 'admin_audits'
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(60))
    subject_id: Mapped[uuid.UUID] = mapped_column()
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())


class AuthChallenge(Identity, Base):
    __tablename__ = 'auth_challenges'
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    purpose: Mapped[str] = mapped_column(String(20))
    email: Mapped[str] = mapped_column(String(254))
    email_version: Mapped[int] = mapped_column(Integer)
    nonce: Mapped[str] = mapped_column(String(64))
    token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())


class RateLimit(Base):
    __tablename__ = 'rate_limits'
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer)


class EmailJob(Identity, Base):
    __tablename__ = 'email_jobs'
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'))
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('reservations.id'), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    recipient: Mapped[str] = mapped_column(String(254))
    context: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(30), default='PENDING', server_default='PENDING')
    provider_message_id: Mapped[str | None] = mapped_column(String(254), index=True)
    send_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    last_error: Mapped[str] = mapped_column(String(40), default='', server_default='')
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())


class PlatformEvent(Identity, Base):
    __tablename__ = 'platform_events'
    kind: Mapped[str] = mapped_column(String(30))
    subject_id: Mapped[uuid.UUID] = mapped_column()
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())


class WebhookInbox(Base):
    __tablename__ = 'webhook_inbox'
    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('email_jobs.id', ondelete='SET NULL'))
    provider_message_id: Mapped[str] = mapped_column(String(254))
    event: Mapped[str] = mapped_column(String(30))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailSuppression(Base):
    __tablename__ = 'email_suppressions'
    email: Mapped[str] = mapped_column(String(254), primary_key=True)
    reason: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())


class StorageObject(Base):
    __tablename__ = 'storage_objects'
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    state: Mapped[str] = mapped_column(String(20), default='STAGED', server_default='STAGED')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    quarantine_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failures: Mapped[int] = mapped_column(Integer, default=0, server_default='0')


class MaintenanceState(Base):
    __tablename__ = 'maintenance_states'
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    cursor: Mapped[str] = mapped_column(Text, default='', server_default='')
    lease_owner: Mapped[uuid.UUID | None] = mapped_column()
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
