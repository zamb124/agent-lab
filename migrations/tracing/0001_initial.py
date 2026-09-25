"""Auto-generated migration.

Created: 2026-09-22 21:03:47
"""

depends_on = None


def upgrade(ctx):
    """Apply migration."""
    ctx.create_table(
        "storage",
        fields=[
            {
                'name': 'key',
                'column_type': {
                    'kind': 'text'
                },
                'db_type': 'TEXT',
                'nullable': False,
                'primary_key': True,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'value',
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
                'name': 'expired_at',
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
            }
        ],
        indexes=[
            {
                'name': 'storage_updated_at_idx',
                'fields': [
                    'updated_at'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'storage_expired_at_idx',
                'fields': [
                    'expired_at'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "spans",
        fields=[
            {
                'name': 'span_id',
                'column_type': {
                    'kind': 'string'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': True,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'trace_id',
                'column_type': {
                    'kind': 'string'
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
                'name': 'operation_name',
                'column_type': {
                    'kind': 'string'
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
                'name': 'start_time',
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
                'name': 'service_name',
                'column_type': {
                    'kind': 'string'
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
                'name': 'parent_span_id',
                'column_type': {
                    'kind': 'string'
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
                'name': 'kind',
                'column_type': {
                    'kind': 'string'
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
                'name': 'end_time',
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
                'name': 'duration_ms',
                'column_type': {
                    'kind': 'big_integer'
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
                'name': 'status',
                'column_type': {
                    'kind': 'string'
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
                'name': 'status_message',
                'column_type': {
                    'kind': 'string'
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
                'name': 'company_id',
                'column_type': {
                    'kind': 'string'
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
                'name': 'namespace',
                'column_type': {
                    'kind': 'string'
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
                'name': 'user_id',
                'column_type': {
                    'kind': 'string'
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
                'name': 'user_name',
                'column_type': {
                    'kind': 'string'
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
                'name': 'user_groups',
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
                'name': 'session_auth',
                'column_type': {
                    'kind': 'string'
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
                'name': 'session_agent',
                'column_type': {
                    'kind': 'string'
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
                'name': 'channel',
                'column_type': {
                    'kind': 'string'
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
                'name': 'event_type',
                'column_type': {
                    'kind': 'string'
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
                'name': 'resource_type',
                'column_type': {
                    'kind': 'string'
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
                'name': 'resource_id',
                'column_type': {
                    'kind': 'string'
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
                'name': 'attributes',
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
                'name': 'events',
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
                'name': 'spans_company_id_resource_type_resource_id_start_time_idx',
                'fields': [
                    'company_id',
                    'resource_type',
                    'resource_id',
                    'start_time'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'spans_trace_id_idx',
                'fields': [
                    'trace_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'spans_start_time_idx',
                'fields': [
                    'start_time'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'spans_service_name_idx',
                'fields': [
                    'service_name'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'spans_parent_span_id_idx',
                'fields': [
                    'parent_span_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'spans_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'spans_namespace_idx',
                'fields': [
                    'namespace'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'spans_user_id_idx',
                'fields': [
                    'user_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'spans_session_auth_idx',
                'fields': [
                    'session_auth'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'spans_session_agent_idx',
                'fields': [
                    'session_agent'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'spans_event_type_idx',
                'fields': [
                    'event_type'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'spans_resource_type_idx',
                'fields': [
                    'resource_type'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'spans_resource_id_idx',
                'fields': [
                    'resource_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )


def downgrade(ctx):
    """Revert migration."""
    ctx.drop_table("spans")
    ctx.drop_table("storage")
