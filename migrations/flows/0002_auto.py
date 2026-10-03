"""Auto-generated migration.

Created: 2026-09-26 13:15:00
"""

depends_on = "0001_initial"


def upgrade(ctx):
    """Apply migration."""
    ctx.alter_column("activity_attempts", "activity_attempt_id", column_type={
    'kind': 'text'
})
    ctx.alter_column("activity_attempts", "activity_id", column_type={
    'kind': 'text'
})
    ctx.alter_column("activity_tasks", "activity_id", column_type={
    'kind': 'text'
})
    ctx.alter_column("activity_tasks", "idempotency_key", column_type={
    'kind': 'text'
})
    ctx.alter_column("tools", "input_mapping", column_type={
    'kind': 'json_binary'
}, db_type='JSONB')
    ctx.alter_column("tools", "output_mapping", column_type={
    'kind': 'json_binary'
}, db_type='JSONB')
    ctx.alter_column("tools", "state_mapping", column_type={
    'kind': 'json_binary'
}, db_type='JSONB')


def downgrade(ctx):
    """Revert migration."""
    pass
