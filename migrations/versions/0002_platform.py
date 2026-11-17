"""Account security, scoped staff, lifecycle, email jobs and maintenance."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='0002_platform'
down_revision='0001_labseat'
branch_labels=None
depends_on=None


def upgrade():
    # Refuse duplicates rather than merging or discarding identity data.
    conn=op.get_bind()
    for expression in ["lower(btrim(email))", "cccd"]:
        if conn.scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM users WHERE {expression} <> '' GROUP BY {expression} HAVING count(*)>1)")):
            raise RuntimeError('Duplicate email/CCCD; resolve through authorized account review before migration')
    op.drop_constraint('users_role_check','users',type_='check')
    op.create_check_constraint('users_role_check','users',"role IN ('student','staff','admin')")
    op.create_table('email_suppressions',
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('reason', sa.String(length=30), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.PrimaryKeyConstraint('email')
    )
    op.create_table('maintenance_states',
    sa.Column('key', sa.String(length=40), nullable=False),
    sa.Column('cursor', sa.Text(), server_default='', nullable=False),
    sa.Column('lease_owner', sa.Uuid(), nullable=True),
    sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('platform_events',
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('subject_id', sa.Uuid(), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('rate_limits',
    sa.Column('key_hash', sa.String(length=64), nullable=False),
    sa.Column('window_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('key_hash')
    )
    op.create_table('storage_objects',
    sa.Column('key', sa.Text(), nullable=False),
    sa.Column('state', sa.String(length=20), server_default='STAGED', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.Column('quarantine_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('failures', sa.Integer(), server_default='0', nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('admin_audits',
    sa.Column('actor_id', sa.Uuid(), nullable=False),
    sa.Column('action', sa.String(length=60), nullable=False),
    sa.Column('subject_id', sa.Uuid(), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('auth_challenges',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('purpose', sa.String(length=20), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('email_version', sa.Integer(), nullable=False),
    sa.Column('nonce', sa.String(length=64), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_auth_challenges_user_id'), 'auth_challenges', ['user_id'], unique=False)
    op.create_table('staff_assignments',
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('assigned_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['lab_sessions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('session_id', 'user_id')
    )
    op.create_table('email_jobs',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('reservation_id', sa.Uuid(), nullable=True),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('recipient', sa.String(length=254), nullable=False),
    sa.Column('context', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=30), server_default='PENDING', nullable=False),
    sa.Column('provider_message_id', sa.String(length=254), nullable=True),
    sa.Column('send_started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('provider_event_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
    sa.Column('last_error', sa.String(length=40), server_default='', nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['reservation_id'], ['reservations.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_email_jobs_provider_message_id'), 'email_jobs', ['provider_message_id'], unique=False)
    op.create_index(op.f('ix_email_jobs_reservation_id'), 'email_jobs', ['reservation_id'], unique=False)
    op.create_table('webhook_inbox',
    sa.Column('fingerprint', sa.String(length=64), nullable=False),
    sa.Column('job_id', sa.Uuid(), nullable=True),
    sa.Column('provider_message_id', sa.String(length=254), nullable=False),
    sa.Column('event', sa.String(length=30), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['job_id'], ['email_jobs.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('fingerprint')
    )
    op.add_column('checkin_policy_events', sa.Column('source', sa.String(length=20), server_default='manual', nullable=False))
    op.add_column('checkin_policy_events', sa.Column('effective_at', sa.DateTime(timezone=True), nullable=True))
    op.alter_column('checkin_policy_events', 'actor_id',
               existing_type=sa.UUID(),
               nullable=True)
    op.add_column('events', sa.Column('status', sa.String(length=20), server_default='ACTIVE', nullable=False))
    op.add_column('events', sa.Column('lifecycle_reason', sa.String(length=500), server_default='', nullable=False))
    op.add_column('events', sa.Column('lifecycle_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('events', sa.Column('lifecycle_actor', sa.Uuid(), nullable=True))
    op.add_column('events', sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('events', sa.Column('cancelled_by', sa.Uuid(), nullable=True))
    op.add_column('events', sa.Column('cancellation_reason', sa.String(length=500), server_default='', nullable=False))
    op.create_foreign_key('events_cancelled_by_fkey', 'events', 'users', ['cancelled_by'], ['id'])
    op.create_foreign_key('events_lifecycle_actor_fkey', 'events', 'users', ['lifecycle_actor'], ['id'])
    op.add_column('lab_sessions', sa.Column('checkin_close_mode', sa.String(length=10), server_default='end_at', nullable=False))
    op.add_column('lab_sessions', sa.Column('checkin_closes_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('lab_sessions', sa.Column('checkin_revision', sa.Integer(), server_default='0', nullable=False))
    op.add_column('users', sa.Column('status', sa.String(length=20), server_default='ACTIVE', nullable=False))
    op.add_column('users', sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('pending_email', sa.String(length=254), nullable=True))
    op.add_column('users', sa.Column('email_version', sa.Integer(), server_default='0', nullable=False))
    op.add_column('users', sa.Column('last_activity_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False))
    op.add_column('users', sa.Column('anonymization_notice_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('anonymization_notice_delivered_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('uq_users_cccd', 'users', ['cccd'], unique=True, postgresql_where=sa.text("cccd <> ''"))
    op.create_index('uq_users_email', 'users', [sa.text('lower(btrim(email))')], unique=True, postgresql_where=sa.text("email <> ''"))

    # Existing schedules keep their manually controlled check-in semantics.
    op.execute("UPDATE lab_sessions SET checkin_close_mode='manual'")
    op.create_check_constraint('users_status_check','users',"status IN ('ACTIVE','LOCKED','ANONYMIZED')")


def downgrade():
    op.drop_constraint('users_status_check','users',type_='check')
    op.drop_constraint('users_role_check','users',type_='check')
    op.create_check_constraint('users_role_check','users',"role IN ('student','admin')")

    op.drop_index('uq_users_email', table_name='users', postgresql_where=sa.text("email <> ''"))
    op.drop_index('uq_users_cccd', table_name='users', postgresql_where=sa.text("cccd <> ''"))
    op.drop_column('users', 'anonymization_notice_delivered_at')
    op.drop_column('users', 'anonymization_notice_at')
    op.drop_column('users', 'last_activity_at')
    op.drop_column('users', 'email_version')
    op.drop_column('users', 'pending_email')
    op.drop_column('users', 'email_verified_at')
    op.drop_column('users', 'status')
    op.drop_column('lab_sessions', 'checkin_revision')
    op.drop_column('lab_sessions', 'checkin_closes_at')
    op.drop_column('lab_sessions', 'checkin_close_mode')
    op.drop_constraint('events_cancelled_by_fkey', 'events', type_='foreignkey')
    op.drop_constraint('events_lifecycle_actor_fkey', 'events', type_='foreignkey')
    op.drop_column('events', 'cancellation_reason')
    op.drop_column('events', 'cancelled_by')
    op.drop_column('events', 'cancelled_at')
    op.drop_column('events', 'lifecycle_actor')
    op.drop_column('events', 'lifecycle_at')
    op.drop_column('events', 'lifecycle_reason')
    op.drop_column('events', 'status')
    op.execute("DELETE FROM checkin_policy_events WHERE actor_id IS NULL")
    op.alter_column('checkin_policy_events', 'actor_id',
               existing_type=sa.UUID(),
               nullable=False)
    op.drop_column('checkin_policy_events', 'effective_at')
    op.drop_column('checkin_policy_events', 'source')
    op.drop_table('webhook_inbox')
    op.drop_index(op.f('ix_email_jobs_reservation_id'), table_name='email_jobs')
    op.drop_index(op.f('ix_email_jobs_provider_message_id'), table_name='email_jobs')
    op.drop_table('email_jobs')
    op.drop_table('staff_assignments')
    op.drop_index(op.f('ix_auth_challenges_user_id'), table_name='auth_challenges')
    op.drop_table('auth_challenges')
    op.drop_table('admin_audits')
    op.drop_table('storage_objects')
    op.drop_table('rate_limits')
    op.drop_table('platform_events')
    op.drop_table('maintenance_states')
    op.drop_table('email_suppressions')
