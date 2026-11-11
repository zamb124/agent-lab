"""Auto-generated migration.

Created: 2026-11-11 22:32:42
"""

depends_on = "0007_retire_silero_tts"


def upgrade(ctx):
    """Apply migration."""
    ctx.alter_enum_type(
        'pending_call_status_enum',
        old_values=[
                       'pending',
                       'consumed',
                       'expired',
                       'canceled'
                   ],
        new_values=[
                       'pending',
                       'resolved',
                       'consumed',
                       'expired',
                       'canceled'
                   ],
    )
    ctx.execute(
        "ALTER TYPE pending_call_status_enum ADD VALUE IF NOT EXISTS 'resolved'"
    )
    ctx.add_column("a2a_pending_calls", {
    'name': 'dedup_key',
    'column_type': {
        'kind': 'string',
        'length': 512
    },
    'db_type': None,
    'nullable': True,
    'primary_key': False,
    'unique': False,
    'default': None,
    'auto_increment': False,
    'max_length': 512,
    'max_digits': None,
    'decimal_places': None
})
    ctx.add_column("a2a_pending_calls", {
    'name': 'result_payload',
    'column_type': {
        'kind': 'json_binary'
    },
    'db_type': 'JSONB',
    'nullable': True,
    'primary_key': False,
    'unique': False,
    'default': None,
    'auto_increment': False,
    'max_length': None,
    'max_digits': None,
    'decimal_places': None
})
    ctx.create_index("a2a_pending_calls", {
    'name': 'a2a_pending_calls_service_dedup_key_idx',
    'fields': [
        'service',
        'dedup_key'
    ],
    'unique': False,
    'method': None
})


def downgrade(ctx):
    """Revert migration."""
    ctx.drop_index("a2a_pending_calls", "a2a_pending_calls_service_dedup_key_idx")
    ctx.drop_column("a2a_pending_calls", "result_payload")
    ctx.drop_column("a2a_pending_calls", "dedup_key")
    ctx.alter_enum_type(
        'pending_call_status_enum',
        old_values=[
                       'pending',
                       'resolved',
                       'consumed',
                       'expired',
                       'canceled'
                   ],
        new_values=[
                       'pending',
                       'consumed',
                       'expired',
                       'canceled'
                   ],
    )
    ctx.execute(
        "ALTER TABLE a2a_pending_calls ALTER COLUMN status DROP DEFAULT"
    )
    ctx.execute(
        "ALTER TYPE pending_call_status_enum RENAME TO pending_call_status_enum_old"
    )
    ctx.execute(
        "CREATE TYPE pending_call_status_enum AS ENUM ('pending', 'consumed', 'expired', 'canceled')"
    )
    ctx.execute(
        "ALTER TABLE a2a_pending_calls ALTER COLUMN status TYPE pending_call_status_enum USING status::text::pending_call_status_enum"
    )
    ctx.execute(
        "ALTER TABLE a2a_pending_calls ALTER COLUMN status SET DEFAULT 'pending'::pending_call_status_enum"
    )
    ctx.execute("DROP TYPE pending_call_status_enum_old")
