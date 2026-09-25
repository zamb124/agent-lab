"""Auto-generated migration.

Created: 2026-09-22 21:03:47
"""

depends_on = None


def upgrade(ctx):
    """Apply migration."""
    ctx.create_enum_type('work_item_comment_role_enum', [
    'operator',
    'user',
    'system',
    'agent'
])
    ctx.create_enum_type('work_item_kind_enum', [
    'generic',
    'operator_handoff',
    'agent_job',
    'crm_activity'
])
    ctx.create_enum_type('work_item_priority_enum', [
    'low',
    'normal',
    'high',
    'urgent'
])
    ctx.create_enum_type('work_item_state_enum', [
    'open',
    'in_progress',
    'blocked',
    'done',
    'cancelled',
    'failed'
])
    ctx.create_table(
        "work_queues",
        fields=[
            {
                'name': 'work_queue_id',
                'column_type': {
                    'kind': 'string',
                    'length': 64
                },
                'db_type': None,
                'nullable': False,
                'primary_key': True,
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
                    'length': 100
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 100,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'name',
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
                'name': 'slug',
                'column_type': {
                    'kind': 'string',
                    'length': 120
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 120,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'owner_user_id',
                'column_type': {
                    'kind': 'string',
                    'length': 100
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 100,
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
            },
            {
                'name': 'description',
                'column_type': {
                    'kind': 'text'
                },
                'db_type': 'TEXT',
                'nullable': True,
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
                'name': 'work_queues_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'work_queues_company_id_slug_idx',
                'fields': [
                    'company_id',
                    'slug'
                ],
                'unique': True,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "work_items",
        fields=[
            {
                'name': 'work_item_id',
                'column_type': {
                    'kind': 'string',
                    'length': 64
                },
                'db_type': None,
                'nullable': False,
                'primary_key': True,
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
                    'length': 100
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 100,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'title',
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
                'name': 'created_by',
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
            },
            {
                'name': 'namespace',
                'column_type': {
                    'kind': 'string',
                    'length': 100
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 100,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'description',
                'column_type': {
                    'kind': 'text'
                },
                'db_type': 'TEXT',
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "''",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'kind',
                'column_type': {
                    'kind': 'string',
                    'length': 32
                },
                'db_type': 'TEXT',
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'generic'",
                'auto_increment': False,
                'max_length': 32,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'state',
                'column_type': {
                    'kind': 'string',
                    'length': 32
                },
                'db_type': 'TEXT',
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'open'",
                'auto_increment': False,
                'max_length': 32,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'board_id',
                'column_type': {
                    'kind': 'string',
                    'length': 64
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 64,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'board_column_id',
                'column_type': {
                    'kind': 'string',
                    'length': 64
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 64,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'priority',
                'column_type': {
                    'kind': 'string',
                    'length': 16
                },
                'db_type': 'TEXT',
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'normal'",
                'auto_increment': False,
                'max_length': 16,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'due_date',
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
                'name': 'labels',
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
                'name': 'assignment',
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
                'name': 'blocking',
                'column_type': {
                    'kind': 'boolean'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': 'FALSE',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'interaction',
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
            },
            {
                'name': 'hooks',
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
                'name': 'resolution',
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
            },
            {
                'name': 'links',
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
                'name': 'variables',
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
                'name': 'attachments',
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
                'name': 'interaction_policy',
                'column_type': {
                    'kind': 'unknown'
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
            }
        ],
        indexes=[
            {
                'name': 'work_items_company_id_state_idx',
                'fields': [
                    'company_id',
                    'state'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'work_items_company_id_board_id_idx',
                'fields': [
                    'company_id',
                    'board_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'work_items_company_id_namespace_idx',
                'fields': [
                    'company_id',
                    'namespace'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'work_items_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'work_items_state_idx',
                'fields': [
                    'state'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "work_item_comments",
        fields=[
            {
                'name': 'comment_id',
                'column_type': {
                    'kind': 'string',
                    'length': 64
                },
                'db_type': None,
                'nullable': False,
                'primary_key': True,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 64,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'work_item_id',
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
                    'length': 100
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 100,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'author',
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
                'name': 'role',
                'column_type': {
                    'kind': 'string',
                    'length': 16
                },
                'db_type': 'TEXT',
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'system'",
                'auto_increment': False,
                'max_length': 16,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'text',
                'column_type': {
                    'kind': 'text'
                },
                'db_type': 'TEXT',
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "''",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'files',
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
            }
        ],
        indexes=[
            {
                'name': 'work_item_comments_work_item_id_idx',
                'fields': [
                    'work_item_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'work_item_comments_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "work_boards",
        fields=[
            {
                'name': 'board_id',
                'column_type': {
                    'kind': 'string',
                    'length': 64
                },
                'db_type': None,
                'nullable': False,
                'primary_key': True,
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
                    'length': 100
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 100,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'name',
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
            },
            {
                'name': 'namespace',
                'column_type': {
                    'kind': 'string',
                    'length': 100
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 100,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'board_key',
                'column_type': {
                    'kind': 'string',
                    'length': 120
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'generic'",
                'auto_increment': False,
                'max_length': 120,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'columns',
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
            }
        ],
        indexes=[
            {
                'name': 'work_boards_company_id_namespace_idx',
                'fields': [
                    'company_id',
                    'namespace'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'work_boards_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )


def downgrade(ctx):
    """Revert migration."""
    ctx.drop_table("work_boards")
    ctx.drop_table("work_item_comments")
    ctx.drop_table("work_items")
    ctx.drop_table("work_queues")
    ctx.drop_enum_type('work_item_state_enum')
    ctx.drop_enum_type('work_item_priority_enum')
    ctx.drop_enum_type('work_item_kind_enum')
    ctx.drop_enum_type('work_item_comment_role_enum')
