"""Shared: ``user_badges`` — платформенный бейдж сотрудника + ``badge`` в auth_provider_enum.

Тенантный credential ``(company_id, code)`` → ``user_id``: скан физического
носителя вместо пароля на любом терминале (ТСД, POS). Сессии минтит общий
``AuthService.login_badge`` → ``auth_sessions.provider = 'badge'``.
"""

depends_on = "0008_alter_pending_call_status_enum_enum"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        "ALTER TYPE auth_provider_enum ADD VALUE IF NOT EXISTS 'badge'"
    )
    ctx.create_table(
        "user_badges",
        fields=[
            {
                'name': 'badge_id',
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
                'name': 'code',
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
                'name': 'user_id',
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
                'name': 'user_badges_company_code_uniq',
                'fields': [
                    'company_id',
                    'code'
                ],
                'unique': True,
                'method': None
            },
            {
                'name': 'user_badges_company_user_idx',
                'fields': [
                    'company_id',
                    'user_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.drop_table("user_badges")
