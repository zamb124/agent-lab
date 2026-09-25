"""Auto-generated migration.

Created: 2026-09-25 11:59:24
"""

depends_on = None


def upgrade(ctx):
    """Apply migration."""
    ctx.execute("CREATE EXTENSION IF NOT EXISTS vector")
    ctx.create_enum_type('ai_capability_enum', [
    'llm_chat',
    'llm_summarize',
    'llm_format_markdown',
    'llm_codegen',
    'llm_vision',
    'embedding',
    'rerank',
    'image_gen',
    'voice_stt',
    'voice_tts',
    'voice_vad'
])
    ctx.create_enum_type('audio_transcription_status_enum', [
    'idle',
    'processing',
    'done',
    'failed'
])
    ctx.create_enum_type('auth_provider_enum', [
    'yandex',
    'google',
    'github',
    'apple',
    'demo'
])
    ctx.create_enum_type('calendar_autolink_status_enum', [
    'linked',
    'unsupported',
    'needs_oauth',
    'needs_password',
    'failed',
    'disabled'
])
    ctx.create_enum_type('calendar_event_source_enum', [
    'platform',
    'crm',
    'sync',
    'flows',
    'google',
    'yandex',
    'mailru',
    'caldav'
])
    ctx.create_enum_type('calendar_event_status_enum', [
    'confirmed',
    'tentative',
    'cancelled'
])
    ctx.create_enum_type('datasource_executor_kind_enum', [
    'platform',
    'mcp',
    'flow'
])
    ctx.create_enum_type('datasource_ssl_mode_enum', [
    'disable',
    'require',
    'verify-full'
])
    ctx.create_enum_type('embed_status_enum', [
    'active',
    'disabled'
])
    ctx.create_enum_type('file_status_enum', [
    'uploading',
    'uploaded',
    'ready',
    'failed',
    'deleted'
])
    ctx.create_enum_type('guest_build_status_enum', [
    'none',
    'building',
    'ready',
    'failed'
])
    ctx.create_enum_type('guest_invoke_kind_enum', [
    'cli',
    'a2a'
])
    ctx.create_enum_type('guest_language_enum', [
    'python',
    'node'
])
    ctx.create_enum_type('integration_provider_enum', [
    'google',
    'yandex',
    'mailru',
    'caldav',
    'amocrm'
])
    ctx.create_enum_type('namespace_kind_enum', [
    'company_workspace',
    'personal',
    'technical'
])
    ctx.create_enum_type('platform_schedule_type_enum', [
    'cron',
    'interval',
    'one_time'
])
    ctx.create_enum_type('scheduled_task_status_enum', [
    'pending',
    'paused',
    'executed',
    'cancelled',
    'failed'
])
    ctx.create_enum_type('tariff_plan_enum', [
    'free',
    'basic',
    'premium',
    'enterprise'
])
    ctx.create_enum_type('usage_type_enum', [
    'tool_call',
    'llm_request',
    'embedding_request',
    'rerank_request',
    'agent_execution',
    'flow_execution',
    'file_upload',
    'storage_usage'
])
    ctx.create_enum_type('user_status_enum', [
    'active',
    'inactive',
    'banned'
])
    ctx.create_table(
        "users",
        fields=[
            {
                'name': 'user_id',
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
                'name': 'name',
                'column_type': {
                    'kind': 'string',
                    'length': 200
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 200,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'first_name',
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
                'name': 'last_name',
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
                'name': 'status',
                'column_type': {
                    'kind': 'enum',
                    'name': 'user_status_enum',
                    'values': [
                        'active',
                        'inactive',
                        'banned'
                    ]
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'active'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'groups',
                'column_type': {
                    'kind': 'array',
                    'item': {
                        'kind': 'string'
                    }
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
                'name': 'companies',
                'column_type': {
                    'kind': 'json'
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
                'name': 'active_company_id',
                'column_type': {
                    'kind': 'string'
                },
                'db_type': None,
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
                'name': 'emails',
                'column_type': {
                    'kind': 'array',
                    'item': {
                        'kind': 'string'
                    }
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
                'name': 'phones',
                'column_type': {
                    'kind': 'array',
                    'item': {
                        'kind': 'string'
                    }
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
                'name': 'messengers',
                'column_type': {
                    'kind': 'json'
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
                'name': 'avatar_url',
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
                'name': 'bio',
                'column_type': {
                    'kind': 'string',
                    'length': 4000
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 4000,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'ui_preferences',
                'column_type': {
                    'kind': 'json'
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
                'name': 'attributes',
                'column_type': {
                    'kind': 'json'
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
                'name': 'password_hash',
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
    )
    ctx.create_table(
        "user_providers",
        fields=[
            {
                'name': 'user_provider_id',
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
                'name': 'user_id',
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
                'name': 'provider_user_id',
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
                'name': 'provider_name',
                'column_type': {
                    'kind': 'enum',
                    'name': 'auth_provider_enum',
                    'values': [
                        'yandex',
                        'google',
                        'github',
                        'apple',
                        'demo'
                    ]
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
                'name': 'email',
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
                'name': 'avatar_url',
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
                'name': 'metadata',
                'column_type': {
                    'kind': 'json'
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
                'name': 'user_providers_user_id_idx',
                'fields': [
                    'user_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'user_providers_provider_user_id_idx',
                'fields': [
                    'provider_user_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "usage",
        fields=[
            {
                'name': 'usage_id',
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
                'name': 'user_id',
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
                'name': 'company_id',
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
                'name': 'session_id',
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
                'name': 'usage_type',
                'column_type': {
                    'kind': 'enum',
                    'name': 'usage_type_enum',
                    'values': [
                        'tool_call',
                        'llm_request',
                        'embedding_request',
                        'rerank_request',
                        'agent_execution',
                        'flow_execution',
                        'file_upload',
                        'storage_usage'
                    ]
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
                'name': 'resource_name',
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
                'name': 'cost',
                'column_type': {
                    'kind': 'double'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': '0.0',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'quantity',
                'column_type': {
                    'kind': 'big_integer'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': '1',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'metadata',
                'column_type': {
                    'kind': 'json'
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
                'name': 'timestamp',
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
                'name': 'usage_user_id_idx',
                'fields': [
                    'user_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'usage_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'usage_usage_type_idx',
                'fields': [
                    'usage_type'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'usage_resource_name_idx',
                'fields': [
                    'resource_name'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'usage_timestamp_idx',
                'fields': [
                    'timestamp'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "storage_routes",
        fields=[
            {
                'name': 'storage_route_id',
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
                'name': 'company_id',
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
                'name': 'source_kind',
                'column_type': {
                    'kind': 'string'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'default'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'storage_id',
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
                'name': 'storage_routes_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'storage_routes_source_kind_idx',
                'fields': [
                    'source_kind'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'storage_routes_storage_id_idx',
                'fields': [
                    'storage_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "storage_migrations",
        fields=[
            {
                'name': 'storage_migration_id',
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
                'name': 'company_id',
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
                'name': 'source_storage_id',
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
                'name': 'target_storage_id',
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
                'name': 'state',
                'column_type': {
                    'kind': 'string'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'running'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'files_total',
                'column_type': {
                    'kind': 'big_integer'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': '0',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'files_moved',
                'column_type': {
                    'kind': 'big_integer'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': '0',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'bytes_moved',
                'column_type': {
                    'kind': 'big_integer'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': '0',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'last_error',
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
            },
            {
                'name': 'cursor',
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
                'name': 'storage_migrations_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'storage_migrations_source_storage_id_idx',
                'fields': [
                    'source_storage_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'storage_migrations_state_idx',
                'fields': [
                    'state'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
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
        "scheduler_tasks",
        fields=[
            {
                'name': 'schedule_task_id',
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
                'name': 'schedule_id',
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
                'name': 'target_service',
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
                'name': 'task_name',
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
                'name': 'queue_name',
                'column_type': {
                    'kind': 'string',
                    'length': 128
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 128,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'schedule_type',
                'column_type': {
                    'kind': 'enum',
                    'name': 'platform_schedule_type_enum',
                    'values': [
                        'cron',
                        'interval',
                        'one_time'
                    ]
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 32,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'cron',
                'column_type': {
                    'kind': 'string',
                    'length': 128
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 128,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'interval_seconds',
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
                'name': 'run_at',
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
                'name': 'timezone',
                'column_type': {
                    'kind': 'string',
                    'length': 64
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'UTC'",
                'auto_increment': False,
                'max_length': 64,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'payload',
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
                'name': 'status',
                'column_type': {
                    'kind': 'enum',
                    'name': 'scheduled_task_status_enum',
                    'values': [
                        'pending',
                        'paused',
                        'executed',
                        'cancelled',
                        'failed'
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
                'name': 'created_by_user_id',
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
                'name': 'last_run_at',
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
                'name': 'next_run_at',
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
                'name': 'error_message',
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
                'name': 'scheduler_tasks_company_id_status_idx',
                'fields': [
                    'company_id',
                    'status'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'scheduler_tasks_company_id_target_service_idx',
                'fields': [
                    'company_id',
                    'target_service'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'scheduler_tasks_company_id_task_name_idx',
                'fields': [
                    'company_id',
                    'task_name'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'scheduler_tasks_company_id_next_run_at_idx',
                'fields': [
                    'company_id',
                    'next_run_at'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'scheduler_tasks_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'scheduler_tasks_schedule_id_idx',
                'fields': [
                    'schedule_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'scheduler_tasks_target_service_idx',
                'fields': [
                    'target_service'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'scheduler_tasks_task_name_idx',
                'fields': [
                    'task_name'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'scheduler_tasks_schedule_type_idx',
                'fields': [
                    'schedule_type'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'scheduler_tasks_status_idx',
                'fields': [
                    'status'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'scheduler_tasks_created_by_user_id_idx',
                'fields': [
                    'created_by_user_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'scheduler_tasks_next_run_at_idx',
                'fields': [
                    'next_run_at'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "push_subscriptions",
        fields=[
            {
                'name': 'push_subscription_id',
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
                'name': 'user_id',
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
                'name': 'endpoint',
                'column_type': {
                    'kind': 'string',
                    'length': 2048
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': True,
                'default': None,
                'auto_increment': False,
                'max_length': 2048,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'keys',
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
                'name': 'user_agent',
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
            },
            {
                'name': 'platform',
                'column_type': {
                    'kind': 'string',
                    'length': 50
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 50,
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
                'name': 'last_used_at',
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
                'name': 'push_subscriptions_user_id_endpoint_idx',
                'fields': [
                    'user_id',
                    'endpoint'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'push_subscriptions_user_id_idx',
                'fields': [
                    'user_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'push_subscriptions_last_used_at_idx',
                'fields': [
                    'last_used_at'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "pronunciation_rules",
        fields=[
            {
                'name': 'pronunciation_rule_id',
                'column_type': {
                    'kind': 'string',
                    'length': 36
                },
                'db_type': None,
                'nullable': False,
                'primary_key': True,
                'unique': False,
                'default': "''",
                'auto_increment': False,
                'max_length': 36,
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
                'name': 'kind',
                'column_type': {
                    'kind': 'unknown'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 16,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'pattern',
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
                'name': 'replacement',
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
                'name': 'language',
                'column_type': {
                    'kind': 'string',
                    'length': 16
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 16,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'case_sensitive',
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
                'name': 'word_boundary',
                'column_type': {
                    'kind': 'boolean'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': 'TRUE',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'providers',
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
                'name': 'voices',
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
                'name': 'enabled',
                'column_type': {
                    'kind': 'boolean'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': 'TRUE',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'note',
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
                'name': 'pronunciation_rules_company_id_enabled_idx',
                'fields': [
                    'company_id',
                    'enabled'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'pronunciation_rules_enabled_idx',
                'fields': [
                    'enabled'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'pronunciation_rules_language_idx',
                'fields': [
                    'language'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'pronunciation_rules_created_at_idx',
                'fields': [
                    'created_at'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'pronunciation_rules_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "platform_short_links",
        fields=[
            {
                'name': 'code',
                'column_type': {
                    'kind': 'string',
                    'length': 32
                },
                'db_type': None,
                'nullable': False,
                'primary_key': True,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 32,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'kind',
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
                'name': 'payload',
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
                'name': 'expires_at',
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
            }
        ],
        indexes=[
            {
                'name': 'platform_short_links_kind_idx',
                'fields': [
                    'kind'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'platform_short_links_expires_at_idx',
                'fields': [
                    'expires_at'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "object_storages",
        fields=[
            {
                'name': 'storage_id',
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
                'name': 'company_id',
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
                'name': 'name',
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
                'name': 'provider',
                'column_type': {
                    'kind': 'string'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'minio'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'endpoint_url',
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
                'name': 'region_name',
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
                'name': 'bucket_name',
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
                'name': 'path_style',
                'column_type': {
                    'kind': 'boolean'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': 'TRUE',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'access_key_id',
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
                'name': 'secret_access_key_encrypted',
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
                'name': 'credentials_version',
                'column_type': {
                    'kind': 'big_integer'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': '1',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'state',
                'column_type': {
                    'kind': 'string'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'verifying'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'verified_at',
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
                'name': 'object_storages_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'object_storages_state_idx',
                'fields': [
                    'state'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "namespaces",
        fields=[
            {
                'name': 'company_id',
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
                'name': 'namespace_id',
                'column_type': {
                    'kind': 'string'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': True,
                'unique': False,
                'default': "''",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'name',
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
                'name': 'description',
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
                'name': 'is_default',
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
                'name': 'kind',
                'column_type': {
                    'kind': 'enum',
                    'name': 'namespace_kind_enum',
                    'values': [
                        'company_workspace',
                        'personal',
                        'technical'
                    ]
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'company_workspace'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'owner_user_id',
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
                'name': 'crm_settings',
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
                'name': 'sync_settings',
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
                'name': 'namespaces_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'namespaces_name_idx',
                'fields': [
                    'name'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "mailbox_sync_cursors",
        fields=[
            {
                'name': 'mailbox_binding_id',
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
                'name': 'folder',
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
                'name': 'uidvalidity',
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
                'name': 'last_uid',
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
                'name': 'backfill_completed',
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
                'name': 'oldest_uid',
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
                'name': 'last_reconcile_at',
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
                'name': 'last_synced_at',
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
                'name': 'last_attempt_at',
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
                'name': 'last_error_kind',
                'column_type': {
                    'kind': 'text'
                },
                'db_type': 'TEXT',
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 32,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'last_error_at',
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
                'name': 'last_error_message',
                'column_type': {
                    'kind': 'string',
                    'length': 1024
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 1024,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'mailbox_sync_cursor_id',
                'column_type': {
                    'kind': 'string',
                    'length': 512
                },
                'db_type': None,
                'nullable': False,
                'primary_key': True,
                'unique': False,
                'default': "''",
                'auto_increment': False,
                'max_length': 512,
                'max_digits': None,
                'decimal_places': None
            }
        ],
        indexes=[
            {
                'name': 'mailbox_sync_cursors_mailbox_binding_id_folder_idx',
                'fields': [
                    'mailbox_binding_id',
                    'folder'
                ],
                'unique': True,
                'method': None
            },
            {
                'name': 'mailbox_sync_cursors_mailbox_binding_id_idx',
                'fields': [
                    'mailbox_binding_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'mailbox_sync_cursors_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'mailbox_sync_cursors_last_synced_at_idx',
                'fields': [
                    'last_synced_at'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "mailbox_folders",
        fields=[
            {
                'name': 'mailbox_binding_id',
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
                'name': 'folder_name',
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
                'name': 'role',
                'column_type': {
                    'kind': 'text'
                },
                'db_type': 'TEXT',
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'other'",
                'auto_increment': False,
                'max_length': 32,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'delimiter',
                'column_type': {
                    'kind': 'string',
                    'length': 16
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 16,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'flags',
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
                'name': 'selectable',
                'column_type': {
                    'kind': 'boolean'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': 'TRUE',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'message_count',
                'column_type': {
                    'kind': 'big_integer'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': '0',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'unseen_count',
                'column_type': {
                    'kind': 'big_integer'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': '0',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'namespace_prefix',
                'column_type': {
                    'kind': 'string',
                    'length': 255
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "''",
                'auto_increment': False,
                'max_length': 255,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'capabilities',
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
                'name': 'sort_index',
                'column_type': {
                    'kind': 'big_integer'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': '0',
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
                'name': 'mailbox_folder_id',
                'column_type': {
                    'kind': 'string',
                    'length': 512
                },
                'db_type': None,
                'nullable': False,
                'primary_key': True,
                'unique': False,
                'default': "''",
                'auto_increment': False,
                'max_length': 512,
                'max_digits': None,
                'decimal_places': None
            }
        ],
        indexes=[
            {
                'name': 'mailbox_folders_mailbox_binding_id_folder_name_idx',
                'fields': [
                    'mailbox_binding_id',
                    'folder_name'
                ],
                'unique': True,
                'method': None
            },
            {
                'name': 'mailbox_folders_mailbox_binding_id_idx',
                'fields': [
                    'mailbox_binding_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'mailbox_folders_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "mailbox_bindings",
        fields=[
            {
                'name': 'mailbox_binding_id',
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
                'name': 'company_mail_connection_id',
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
                'name': 'kind',
                'column_type': {
                    'kind': 'text'
                },
                'db_type': 'TEXT',
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 32,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'email_address',
                'column_type': {
                    'kind': 'string',
                    'length': 320
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 320,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'local_part',
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
                'name': 'sync_enabled',
                'column_type': {
                    'kind': 'boolean'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': 'TRUE',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'is_default',
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
                'name': 'calendar_color',
                'column_type': {
                    'kind': 'string',
                    'length': 32
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'default'",
                'auto_increment': False,
                'max_length': 32,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'calendar_autolink_status',
                'column_type': {
                    'kind': 'enum',
                    'name': 'calendar_autolink_status_enum',
                    'values': [
                        'linked',
                        'unsupported',
                        'needs_oauth',
                        'needs_password',
                        'failed',
                        'disabled'
                    ]
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'disabled'",
                'auto_increment': False,
                'max_length': 32,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'calendar_autolink_detail',
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
            },
            {
                'name': 'password_encrypted',
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
                'name': 'mailbox_bindings_company_id_email_address_idx',
                'fields': [
                    'company_id',
                    'email_address'
                ],
                'unique': True,
                'method': None
            },
            {
                'name': 'mailbox_bindings_company_id_local_part_idx',
                'fields': [
                    'company_id',
                    'local_part'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'mailbox_bindings_company_id_user_id_is_default_idx',
                'fields': [
                    'company_id',
                    'user_id',
                    'is_default'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'mailbox_bindings_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'mailbox_bindings_company_mail_connection_id_idx',
                'fields': [
                    'company_mail_connection_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'mailbox_bindings_user_id_idx',
                'fields': [
                    'user_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "mail_messages",
        fields=[
            {
                'name': 'mail_message_id',
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
                'name': 'mailbox_binding_id',
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
                'name': 'folder',
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
                'name': 'uid',
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
                'name': 'thread_id',
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
                'name': 'synced_at',
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
                'name': 'user_id',
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
                'name': 'message_id',
                'column_type': {
                    'kind': 'string',
                    'length': 998
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 998,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'subject',
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
                'name': 'from_address',
                'column_type': {
                    'kind': 'string',
                    'length': 998
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "''",
                'auto_increment': False,
                'max_length': 998,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'to_addresses',
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
                'name': 'cc_addresses',
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
                'name': 'date_at',
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
                'name': 'unread',
                'column_type': {
                    'kind': 'boolean'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': 'TRUE',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'flagged',
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
                'name': 'answered',
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
                'name': 'draft',
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
                'name': 'has_attachments',
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
                'name': 'snippet',
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
                'name': 'body_text',
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
            },
            {
                'name': 'body_html',
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
                'name': 'in_reply_to',
                'column_type': {
                    'kind': 'string',
                    'length': 998
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 998,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'references',
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
            },
            {
                'name': 'rag_document_id',
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
                'name': 'rag_namespace',
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
                'name': 'rag_index_status',
                'column_type': {
                    'kind': 'text'
                },
                'db_type': 'TEXT',
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'skipped'",
                'auto_increment': False,
                'max_length': 32,
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
                'name': 'mail_messages_mailbox_binding_id_folder_uid_idx',
                'fields': [
                    'mailbox_binding_id',
                    'folder',
                    'uid'
                ],
                'unique': True,
                'method': None
            },
            {
                'name': 'mail_messages_mailbox_binding_id_folder_date_at_idx',
                'fields': [
                    'mailbox_binding_id',
                    'folder',
                    'date_at'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'mail_messages_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'mail_messages_mailbox_binding_id_idx',
                'fields': [
                    'mailbox_binding_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'mail_messages_thread_id_idx',
                'fields': [
                    'thread_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'mail_messages_user_id_idx',
                'fields': [
                    'user_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "llm_model_scores",
        fields=[
            {
                'name': 'llm_model_score_id',
                'column_type': {
                    'kind': 'string'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': True,
                'unique': False,
                'default': "''",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'provider',
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
                'name': 'model_id',
                'column_type': {
                    'kind': 'string',
                    'length': 512
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 512,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'capability',
                'column_type': {
                    'kind': 'enum',
                    'name': 'ai_capability_enum',
                    'values': [
                        'llm_chat',
                        'llm_summarize',
                        'llm_format_markdown',
                        'llm_codegen',
                        'llm_vision',
                        'embedding',
                        'rerank',
                        'image_gen',
                        'voice_stt',
                        'voice_tts',
                        'voice_vad'
                    ]
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
                'name': 'enabled',
                'column_type': {
                    'kind': 'boolean'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': 'TRUE',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'editorial_prior',
                'column_type': {
                    'kind': 'double'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': '0.0',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'note',
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
            },
            {
                'name': 'updated_by_user_id',
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
                'name': 'llm_model_scores_provider_idx',
                'fields': [
                    'provider'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'llm_model_scores_model_id_idx',
                'fields': [
                    'model_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'llm_model_scores_capability_idx',
                'fields': [
                    'capability'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'llm_model_scores_enabled_idx',
                'fields': [
                    'enabled'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'llm_model_scores_updated_at_idx',
                'fields': [
                    'updated_at'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "integration_credentials",
        fields=[
            {
                'name': 'credential_id',
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
                'name': 'provider',
                'column_type': {
                    'kind': 'enum',
                    'name': 'integration_provider_enum',
                    'values': [
                        'google',
                        'yandex',
                        'mailru',
                        'caldav',
                        'amocrm'
                    ]
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
                'name': 'mailbox_binding_id',
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
                'name': 'access_token',
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
                'name': 'refresh_token',
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
            },
            {
                'name': 'expires_at',
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
                'name': 'scope',
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
            },
            {
                'name': 'token_type',
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
                'name': 'metadata',
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
            }
        ],
        indexes=[
            {
                'name': 'integration_credentials_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'integration_credentials_user_id_idx',
                'fields': [
                    'user_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'integration_credentials_provider_idx',
                'fields': [
                    'provider'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'integration_credentials_service_idx',
                'fields': [
                    'service'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'integration_credentials_mailbox_binding_id_idx',
                'fields': [
                    'mailbox_binding_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "guest_runtimes",
        fields=[
            {
                'name': 'guest_runtime_id',
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
                'name': 'flow_id',
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
                'name': 'node_id',
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
                'name': 'company_id',
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
                'name': 'catalog_id',
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
                'name': 'language',
                'column_type': {
                    'kind': 'enum',
                    'name': 'guest_language_enum',
                    'values': [
                        'python',
                        'node'
                    ]
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
                'name': 'invoke_kind',
                'column_type': {
                    'kind': 'enum',
                    'name': 'guest_invoke_kind_enum',
                    'values': [
                        'cli',
                        'a2a'
                    ]
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
                'name': 'invoke_argv',
                'column_type': {
                    'kind': 'array',
                    'item': {
                        'kind': 'string'
                    }
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
                'name': 'invoke_listen_port',
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
                'name': 'egress_hosts',
                'column_type': {
                    'kind': 'array',
                    'item': {
                        'kind': 'string'
                    }
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
                'name': 'git_url',
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
            },
            {
                'name': 'source_sha',
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
                'name': 'image_digest',
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
            },
            {
                'name': 'image_bytes',
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
                'name': 'build_status',
                'column_type': {
                    'kind': 'enum',
                    'name': 'guest_build_status_enum',
                    'values': [
                        'none',
                        'building',
                        'ready',
                        'failed'
                    ]
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'none'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'build_error',
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
                'name': 'guest_runtimes_flow_id_idx',
                'fields': [
                    'flow_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'guest_runtimes_node_id_idx',
                'fields': [
                    'node_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'guest_runtimes_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'guest_runtimes_build_status_idx',
                'fields': [
                    'build_status'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "files",
        fields=[
            {
                'name': 'file_id',
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
                'name': 'original_name',
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
                'name': 's3_key',
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
                'name': 'storage_id',
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
                'name': 'storage_url',
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
            },
            {
                'name': 'content_type',
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
                'name': 'file_size',
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
                'name': 'checksum',
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
                'name': 'status',
                'column_type': {
                    'kind': 'enum',
                    'name': 'file_status_enum',
                    'values': [
                        'uploading',
                        'uploaded',
                        'ready',
                        'failed',
                        'deleted'
                    ]
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'uploading'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'uploaded_by',
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
                'name': 'metadata',
                'column_type': {
                    'kind': 'json'
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
                'name': 'tags',
                'column_type': {
                    'kind': 'array',
                    'item': {
                        'kind': 'string'
                    }
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
                'name': 'is_public',
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
                'name': 'download_url',
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
                'name': 'deleted_at',
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
                'name': 'retention_kind',
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
                'name': 'expires_at',
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
                'name': 'language',
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
                'name': 'sample_rate',
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
                'name': 'channels',
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
                'name': 'audio_format',
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
                'name': 'transcription_status',
                'column_type': {
                    'kind': 'enum',
                    'name': 'audio_transcription_status_enum',
                    'values': [
                        'idle',
                        'processing',
                        'done',
                        'failed'
                    ]
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'idle'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'transcription_text',
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
            },
            {
                'name': 'transcription_error',
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
            },
            {
                'name': 'transcription_provider',
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
            }
        ],
        indexes=[
            {
                'name': 'files_storage_id_idx',
                'fields': [
                    'storage_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'files_status_idx',
                'fields': [
                    'status'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'files_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'files_updated_at_idx',
                'fields': [
                    'updated_at'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'files_expires_at_idx',
                'fields': [
                    'expires_at'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "embed_configs",
        fields=[
            {
                'name': 'embed_id',
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
                'name': 'company_id',
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
                'name': 'name',
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
                'name': 'flow_id',
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
                'name': 'branch_id',
                'column_type': {
                    'kind': 'string'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'default'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'allowed_origins',
                'column_type': {
                    'kind': 'array',
                    'item': {
                        'kind': 'string'
                    }
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
                    'name': 'embed_status_enum',
                    'values': [
                        'active',
                        'disabled'
                    ]
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'active'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'presentation',
                'column_type': {
                    'kind': 'unknown'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'drawer'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'theme',
                'column_type': {
                    'kind': 'string'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'dark'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'position',
                'column_type': {
                    'kind': 'unknown'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'bottom-right'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'show_launcher',
                'column_type': {
                    'kind': 'boolean'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': 'TRUE',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'primary_color',
                'column_type': {
                    'kind': 'string'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'#6366f1'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'assistant_title',
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
                'name': 'interface_locale',
                'column_type': {
                    'kind': 'string'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'auto'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'placeholder',
                'column_type': {
                    'kind': 'string'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'Введите сообщение...'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'branding',
                'column_type': {
                    'kind': 'boolean'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': 'TRUE',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'landing_visible',
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
                'name': 'landing_card_image_url',
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
                'name': 'landing_sort_order',
                'column_type': {
                    'kind': 'big_integer'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': '0',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'guest_max_user_messages',
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
                'name': 'voice_enabled',
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
                'name': 'voice_default_on',
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
                'name': 'session_share_enabled',
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
                'name': 'preview_share_link',
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
                'name': 'conversation',
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
                'name': 'start_page_id',
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
                'name': 'usage_count',
                'column_type': {
                    'kind': 'big_integer'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': '0',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'last_used_at',
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
                'name': 'created_by',
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
                'name': 'embed_configs_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'embed_configs_flow_id_idx',
                'fields': [
                    'flow_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "datasource_connectors",
        fields=[
            {
                'name': 'datasource_connector_id',
                'column_type': {
                    'kind': 'string'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': True,
                'unique': False,
                'default': "''",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'connector_id',
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
                'name': 'description',
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
                'name': 'executor',
                'column_type': {
                    'kind': 'enum',
                    'name': 'datasource_executor_kind_enum',
                    'values': [
                        'platform',
                        'mcp',
                        'flow'
                    ]
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 32,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'icon',
                'column_type': {
                    'kind': 'string',
                    'length': 64
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'database'",
                'auto_increment': False,
                'max_length': 64,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'credential_schema',
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
                'name': 'operations',
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
                'name': 'mcp_server_id',
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
                'name': 'mcp_introspect_tool',
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
                'name': 'mcp_query_tool',
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
                'name': 'mcp_execute_tool',
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
                'name': 'flow_id',
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
                'name': 'flow_branch_id',
                'column_type': {
                    'kind': 'string',
                    'length': 255
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'default'",
                'auto_increment': False,
                'max_length': 255,
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
                'name': 'owner_user_id',
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
                'name': 'datasource_connectors_company_id_connector_id_idx',
                'fields': [
                    'company_id',
                    'connector_id'
                ],
                'unique': True,
                'method': None
            },
            {
                'name': 'datasource_connectors_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "datasource_connections",
        fields=[
            {
                'name': 'datasource_id',
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
                'name': 'connector_id',
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
                'name': 'host',
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
                'name': 'port',
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
                'name': 'database_name',
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
                'name': 'username',
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
                'name': 'password_encrypted',
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
            },
            {
                'name': 'ssl_mode',
                'column_type': {
                    'kind': 'enum',
                    'name': 'datasource_ssl_mode_enum',
                    'values': [
                        'disable',
                        'require',
                        'verify-full'
                    ]
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'require'",
                'auto_increment': False,
                'max_length': 32,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'allowed_operations',
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
                'name': 'statement_timeout_ms',
                'column_type': {
                    'kind': 'big_integer'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': '15000',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'max_rows',
                'column_type': {
                    'kind': 'big_integer'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': '1000',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'mcp_server_id',
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
                'name': 'flow_id',
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
                'name': 'flow_branch_id',
                'column_type': {
                    'kind': 'string',
                    'length': 255
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'default'",
                'auto_increment': False,
                'max_length': 255,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'owner_user_id',
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
            }
        ],
        indexes=[
            {
                'name': 'datasource_connections_company_id_name_idx',
                'fields': [
                    'company_id',
                    'name'
                ],
                'unique': True,
                'method': None
            },
            {
                'name': 'datasource_connections_company_id_connector_id_idx',
                'fields': [
                    'company_id',
                    'connector_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'datasource_connections_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "cookie_consents",
        fields=[
            {
                'name': 'cookie_consent_id',
                'column_type': {
                    'kind': 'string',
                    'length': 36
                },
                'db_type': None,
                'nullable': False,
                'primary_key': True,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 36,
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
                'name': 'brand_host',
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
                'name': 'apex_domain',
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
                'name': 'decision',
                'column_type': {
                    'kind': 'unknown'
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
                'name': 'analytics_allowed',
                'column_type': {
                    'kind': 'boolean'
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
                'name': 'consent_text_version',
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
                'name': 'locale',
                'column_type': {
                    'kind': 'unknown'
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
                'name': 'request_id',
                'column_type': {
                    'kind': 'string',
                    'length': 128
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 128,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'user_agent',
                'column_type': {
                    'kind': 'string',
                    'length': 512
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 512,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'ip_hash',
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
                'name': 'supersedes_cookie_consent_id',
                'column_type': {
                    'kind': 'string',
                    'length': 36
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 36,
                'max_digits': None,
                'decimal_places': None
            }
        ],
        indexes=[
            {
                'name': 'cookie_consents_apex_domain_created_at_idx',
                'fields': [
                    'apex_domain',
                    'created_at'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'cookie_consents_created_at_idx',
                'fields': [
                    'created_at'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "company_voice_providers",
        fields=[
            {
                'name': 'company_voice_provider_id',
                'column_type': {
                    'kind': 'string'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': True,
                'unique': False,
                'default': "''",
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
                'name': 'kind',
                'column_type': {
                    'kind': 'unknown'
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
                'name': 'provider',
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
                'name': 'model',
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
                'name': 'voice',
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
                'name': 'language',
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
                'name': 'sample_rate',
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
                'name': 'threshold',
                'column_type': {
                    'kind': 'double'
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
                'name': 'response_format',
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
                'name': 'secrets',
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
                'name': 'company_voice_providers_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'company_voice_providers_kind_idx',
                'fields': [
                    'kind'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "company_mail_connections",
        fields=[
            {
                'name': 'company_mail_connection_id',
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
                'name': 'scope',
                'column_type': {
                    'kind': 'text'
                },
                'db_type': 'TEXT',
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'company'",
                'auto_increment': False,
                'max_length': 32,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'owner_user_id',
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
                'name': 'mail_domain',
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
                'name': 'provider',
                'column_type': {
                    'kind': 'text'
                },
                'db_type': 'TEXT',
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
                'name': 'imap_host',
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
                'name': 'imap_port',
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
                'name': 'smtp_host',
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
                'name': 'smtp_port',
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
                'name': 'use_ssl',
                'column_type': {
                    'kind': 'boolean'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': 'TRUE',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'supports_provision',
                'column_type': {
                    'kind': 'boolean'
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
                    'kind': 'text'
                },
                'db_type': 'TEXT',
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'active'",
                'auto_increment': False,
                'max_length': 32,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'ispmanager',
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
                'name': 'company_mail_connections_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': True,
                'method': None,
                'where': "scope = 'company'"
            },
            {
                'name': 'company_mail_connections_mail_domain_idx',
                'fields': [
                    'mail_domain'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'company_mail_connections_owner_user_id_idx',
                'fields': [
                    'owner_user_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "companies",
        fields=[
            {
                'name': 'company_id',
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
                'name': 'name',
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
                'name': 'subdomain',
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
                'name': 'owner_user_id',
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
                'name': 'members',
                'column_type': {
                    'kind': 'json'
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
                    'kind': 'string'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'active'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'metadata',
                'column_type': {
                    'kind': 'json'
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
                'name': 'tariff_plan',
                'column_type': {
                    'kind': 'enum',
                    'name': 'tariff_plan_enum',
                    'values': [
                        'free',
                        'basic',
                        'premium',
                        'enterprise'
                    ]
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'free'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'balance',
                'column_type': {
                    'kind': 'double'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': '50.0',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'monthly_budget',
                'column_type': {
                    'kind': 'double'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': '0.0',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'current_month_spent',
                'column_type': {
                    'kind': 'double'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': '0.0',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'billing_period_start',
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
                'name': 'companies_subdomain_idx',
                'fields': [
                    'subdomain'
                ],
                'unique': True,
                'method': None,
                'where': 'subdomain IS NOT NULL'
            }
        ],
    )
    ctx.create_table(
        "calendar_events",
        fields=[
            {
                'name': 'event_id',
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
                'name': 'source',
                'column_type': {
                    'kind': 'enum',
                    'name': 'calendar_event_source_enum',
                    'values': [
                        'platform',
                        'crm',
                        'sync',
                        'flows',
                        'google',
                        'yandex',
                        'mailru',
                        'caldav'
                    ]
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
                'name': 'source_id',
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
                'name': 'namespace',
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
                'name': 'kind',
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
                'name': 'title',
                'column_type': {
                    'kind': 'string',
                    'length': 1024
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 1024,
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
            },
            {
                'name': 'location',
                'column_type': {
                    'kind': 'string',
                    'length': 1024
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 1024,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'status',
                'column_type': {
                    'kind': 'enum',
                    'name': 'calendar_event_status_enum',
                    'values': [
                        'confirmed',
                        'tentative',
                        'cancelled'
                    ]
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'confirmed'",
                'auto_increment': False,
                'max_length': 32,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'timezone',
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
                'name': 'all_day',
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
                'name': 'start_at',
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
                'name': 'end_at',
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
                'name': 'attendees',
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
                'name': 'recurrence_rule',
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
            },
            {
                'name': 'recurrence_id',
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
                'name': 'series_id',
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
                'name': 'deep_link',
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
            },
            {
                'name': 'external_refs',
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
                'name': 'metadata',
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
                'name': 'mailbox_binding_id',
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
                'name': 'created_by_user_id',
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
                'name': 'updated_by_user_id',
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
                'name': 'calendar_events_company_id_source_source_id_idx',
                'fields': [
                    'company_id',
                    'source',
                    'source_id'
                ],
                'unique': True,
                'method': None
            },
            {
                'name': 'calendar_events_company_id_start_at_end_at_idx',
                'fields': [
                    'company_id',
                    'start_at',
                    'end_at'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'calendar_events_company_id_kind_start_at_idx',
                'fields': [
                    'company_id',
                    'kind',
                    'start_at'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'calendar_events_attendees_idx',
                'fields': [
                    'attendees'
                ],
                'unique': False,
                'method': 'gin'
            },
            {
                'name': 'calendar_events_external_refs_idx',
                'fields': [
                    'external_refs'
                ],
                'unique': False,
                'method': 'gin'
            },
            {
                'name': 'calendar_events_metadata_idx',
                'fields': [
                    'metadata'
                ],
                'unique': False,
                'method': 'gin'
            },
            {
                'name': 'calendar_events_source_idx',
                'fields': [
                    'source'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'calendar_events_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'calendar_events_namespace_idx',
                'fields': [
                    'namespace'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'calendar_events_kind_idx',
                'fields': [
                    'kind'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'calendar_events_status_idx',
                'fields': [
                    'status'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'calendar_events_start_at_idx',
                'fields': [
                    'start_at'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'calendar_events_end_at_idx',
                'fields': [
                    'end_at'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'calendar_events_recurrence_id_idx',
                'fields': [
                    'recurrence_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'calendar_events_series_id_idx',
                'fields': [
                    'series_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'calendar_events_mailbox_binding_id_idx',
                'fields': [
                    'mailbox_binding_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'calendar_events_created_by_user_id_idx',
                'fields': [
                    'created_by_user_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'calendar_events_updated_by_user_id_idx',
                'fields': [
                    'updated_by_user_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "auth_sessions",
        fields=[
            {
                'name': 'session_id',
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
                'name': 'user_id',
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
                'name': 'provider',
                'column_type': {
                    'kind': 'enum',
                    'name': 'auth_provider_enum',
                    'values': [
                        'yandex',
                        'google',
                        'github',
                        'apple',
                        'demo'
                    ]
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
                'name': 'access_token',
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
                'name': 'refresh_token',
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
                'name': 'expires_at',
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
                'name': 'last_activity',
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
                'name': 'metadata',
                'column_type': {
                    'kind': 'json'
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
                'name': 'auth_sessions_user_id_idx',
                'fields': [
                    'user_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "api_keys",
        fields=[
            {
                'name': 'key_id',
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
                'name': 'company_id',
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
                'name': 'name',
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
                'name': 'key_hash',
                'column_type': {
                    'kind': 'string'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': True,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'key_prefix',
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
                'name': 'scopes',
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
                'name': 'created_by',
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
                'name': 'revoked',
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
                'name': 'last_used',
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
                'name': 'api_keys_company_id_idx',
                'fields': [
                    'company_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'api_keys_created_by_idx',
                'fields': [
                    'created_by'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'api_keys_revoked_idx',
                'fields': [
                    'revoked'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'api_keys_created_at_idx',
                'fields': [
                    'created_at'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "ai_models",
        fields=[
            {
                'name': 'ai_model_id',
                'column_type': {
                    'kind': 'string'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': True,
                'unique': False,
                'default': "''",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'provider',
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
                'name': 'model_id',
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
                'name': 'capabilities',
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
                'name': 'input_modalities',
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
                'name': 'output_modalities',
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
                'name': 'supported_parameters',
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
                'name': 'context_length',
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
                'name': 'created',
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
                'name': 'native_dimension',
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
                'name': 'storage_dimension',
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
                'name': 'mrl_output_dimension',
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
                'name': 'supports_tools',
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
                'name': 'supports_structured_output',
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
                'name': 'is_free',
                'column_type': {
                    'kind': 'boolean'
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
                'name': 'free_reason',
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
                'name': 'free_policy',
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
                'name': 'pricing',
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
                'name': 'artificial_analysis',
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
                'name': 'availability_status',
                'column_type': {
                    'kind': 'unknown'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'unknown'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'metadata_status',
                'column_type': {
                    'kind': 'unknown'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'discovered'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'last_seen_at',
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
                'name': 'raw',
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
                'name': 'ai_models_provider_idx',
                'fields': [
                    'provider'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'ai_models_model_id_idx',
                'fields': [
                    'model_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )


def downgrade(ctx):
    """Revert migration."""
    ctx.drop_table("ai_models")
    ctx.drop_table("api_keys")
    ctx.drop_table("auth_sessions")
    ctx.drop_table("calendar_events")
    ctx.drop_table("companies")
    ctx.drop_table("company_mail_connections")
    ctx.drop_table("company_voice_providers")
    ctx.drop_table("cookie_consents")
    ctx.drop_table("datasource_connections")
    ctx.drop_table("datasource_connectors")
    ctx.drop_table("embed_configs")
    ctx.drop_table("files")
    ctx.drop_table("guest_runtimes")
    ctx.drop_table("integration_credentials")
    ctx.drop_table("llm_model_scores")
    ctx.drop_table("mail_messages")
    ctx.drop_table("mailbox_bindings")
    ctx.drop_table("mailbox_folders")
    ctx.drop_table("mailbox_sync_cursors")
    ctx.drop_table("namespaces")
    ctx.drop_table("object_storages")
    ctx.drop_table("platform_short_links")
    ctx.drop_table("pronunciation_rules")
    ctx.drop_table("push_subscriptions")
    ctx.drop_table("scheduler_tasks")
    ctx.drop_table("storage")
    ctx.drop_table("storage_migrations")
    ctx.drop_table("storage_routes")
    ctx.drop_table("usage")
    ctx.drop_table("user_providers")
    ctx.drop_table("users")
    ctx.drop_enum_type('user_status_enum')
    ctx.drop_enum_type('usage_type_enum')
    ctx.drop_enum_type('tariff_plan_enum')
    ctx.drop_enum_type('scheduled_task_status_enum')
    ctx.drop_enum_type('platform_schedule_type_enum')
    ctx.drop_enum_type('namespace_kind_enum')
    ctx.drop_enum_type('integration_provider_enum')
    ctx.drop_enum_type('guest_language_enum')
    ctx.drop_enum_type('guest_invoke_kind_enum')
    ctx.drop_enum_type('guest_build_status_enum')
    ctx.drop_enum_type('file_status_enum')
    ctx.drop_enum_type('embed_status_enum')
    ctx.drop_enum_type('datasource_ssl_mode_enum')
    ctx.drop_enum_type('datasource_executor_kind_enum')
    ctx.drop_enum_type('calendar_event_status_enum')
    ctx.drop_enum_type('calendar_event_source_enum')
    ctx.drop_enum_type('calendar_autolink_status_enum')
    ctx.drop_enum_type('auth_provider_enum')
    ctx.drop_enum_type('audio_transcription_status_enum')
    ctx.drop_enum_type('ai_capability_enum')
