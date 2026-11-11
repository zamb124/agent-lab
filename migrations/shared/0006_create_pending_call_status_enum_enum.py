"""Auto-generated migration.

Created: 2026-11-11 21:27:24
"""

depends_on = "0005_catalog"


def upgrade(ctx):
    """Apply migration."""
    ctx.create_enum_type('pending_call_status_enum', [
    'pending',
    'consumed',
    'expired',
    'canceled'
])
    ctx.create_enum_type('pending_join_status_enum', [
    'pending',
    'fired',
    'expired'
])
    ctx.create_table(
        "a2a_pending_joins",
        fields=[
            {
                'name': 'join_group',
                'column_type': {
                    'kind': 'string',
                    'length': 255
                },
                'db_type': None,
                'nullable': False,
                'primary_key': True,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 255,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'service',
                'column_type': {
                    'kind': 'string',
                    'length': 64
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 64,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'company_id',
                'column_type': {
                    'kind': 'string',
                    'length': 255
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 255,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'join_task',
                'column_type': {
                    'kind': 'string',
                    'length': 255
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 255,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'join_kwargs',
                'column_type': {
                    'kind': 'json_binary'
                },
                'db_type': 'JSONB',
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'join_total',
                'column_type': {
                    'kind': 'big_integer'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'join_remaining',
                'column_type': {
                    'kind': 'big_integer'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'status',
                'column_type': {
                    'kind': 'enum',
                    'name': 'pending_join_status_enum',
                    'values': [
                        'pending',
                        'fired',
                        'expired'
                    ]
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'pending'",
                'auto_increment': False,
                'max_length': 32,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'deadline_at',
                'column_type': {
                    'kind': 'date_time'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'created_at',
                'column_type': {
                    'kind': 'date_time'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'updated_at',
                'column_type': {
                    'kind': 'date_time'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            }
        ],
        indexes=[
            {
                'name': 'a2a_pending_joins_service_status_deadline_at_idx',
                'fields': [
                    'service',
                    'status',
                    'deadline_at'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'a2a_pending_joins_service_idx',
                'fields': [
                    'service'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'a2a_pending_joins_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'a2a_pending_joins_status_idx',
                'fields': [
                    'status'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'a2a_pending_joins_deadline_at_idx',
                'fields': [
                    'deadline_at'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "a2a_pending_calls",
        fields=[
            {
                'name': 'a2a_task_id',
                'column_type': {
                    'kind': 'string',
                    'length': 255
                },
                'db_type': None,
                'nullable': False,
                'primary_key': True,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 255,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'service',
                'column_type': {
                    'kind': 'string',
                    'length': 64
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 64,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'company_id',
                'column_type': {
                    'kind': 'string',
                    'length': 255
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 255,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'user_id',
                'column_type': {
                    'kind': 'string',
                    'length': 255
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 255,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'base_url',
                'column_type': {
                    'kind': 'text'
                },
                'db_type': 'TEXT',
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'continuation_task',
                'column_type': {
                    'kind': 'string',
                    'length': 255
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 255,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'continuation_kwargs',
                'column_type': {
                    'kind': 'json_binary'
                },
                'db_type': 'JSONB',
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'callback_token_hash',
                'column_type': {
                    'kind': 'string',
                    'length': 64
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 64,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'join_group',
                'column_type': {
                    'kind': 'string',
                    'length': 255
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 255,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'parent_task_id',
                'column_type': {
                    'kind': 'string',
                    'length': 255
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 255,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'status',
                'column_type': {
                    'kind': 'enum',
                    'name': 'pending_call_status_enum',
                    'values': [
                        'pending',
                        'consumed',
                        'expired',
                        'canceled'
                    ]
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'pending'",
                'auto_increment': False,
                'max_length': 32,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'deadline_at',
                'column_type': {
                    'kind': 'date_time'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'consumed_at',
                'column_type': {
                    'kind': 'date_time'
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'created_at',
                'column_type': {
                    'kind': 'date_time'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'updated_at',
                'column_type': {
                    'kind': 'date_time'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            }
        ],
        indexes=[
            {
                'name': 'a2a_pending_calls_status_deadline_at_idx',
                'fields': [
                    'status',
                    'deadline_at'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'a2a_pending_calls_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'a2a_pending_calls_parent_task_id_idx',
                'fields': [
                    'parent_task_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'a2a_pending_calls_join_group_idx',
                'fields': [
                    'join_group'
                ],
                'unique': False,
                'method': None
            }
        ],
    )


def downgrade(ctx):
    """Revert migration."""
    ctx.drop_table("a2a_pending_calls")
    ctx.drop_table("a2a_pending_joins")
    ctx.drop_enum_type('pending_join_status_enum')
    ctx.drop_enum_type('pending_call_status_enum')
