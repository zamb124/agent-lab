"""Auto-generated migration.

Created: 2026-11-02 21:23:20
"""

depends_on = "0002_create_provider_litserve_models_table"


def upgrade(ctx):
    """Apply migration."""
    ctx.create_enum_type('customer_identity_provider_enum', [
    'telegram',
    'max',
    'yandex',
    'vk',
    'sber',
    'phone',
    'emulator'
])
    ctx.create_enum_type('customer_status_enum', [
    'active',
    'disabled'
])
    ctx.create_enum_type('phone_verification_method_enum', [
    'telegram_contact',
    'max_contact',
    'yandex_id',
    'vk_id',
    'sber_id',
    'sms_code',
    'emulator'
])
    ctx.create_table(
        "customers",
        fields=[
            {
                'name': 'customer_id',
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
                'name': 'phone_e164',
                'column_type': {
                    'kind': 'string',
                    'length': 32
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
                'name': 'name',
                'column_type': {
                    'kind': 'string',
                    'length': 200
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 200,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'status',
                'column_type': {
                    'kind': 'enum',
                    'name': 'customer_status_enum',
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
                'name': 'last_login_at',
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
                'name': 'customers_phone_e164_idx',
                'fields': [
                    'phone_e164'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "customer_identities",
        fields=[
            {
                'name': 'identity_id',
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
                'name': 'customer_id',
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
                'name': 'provider',
                'column_type': {
                    'kind': 'enum',
                    'name': 'customer_identity_provider_enum',
                    'values': [
                        'telegram',
                        'max',
                        'yandex',
                        'vk',
                        'sber',
                        'phone',
                        'emulator'
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
                'name': 'provider_user_id',
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
                'name': 'verified_phone_e164',
                'column_type': {
                    'kind': 'string',
                    'length': 32
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
                'name': 'verification_method',
                'column_type': {
                    'kind': 'enum',
                    'name': 'phone_verification_method_enum',
                    'values': [
                        'telegram_contact',
                        'max_contact',
                        'yandex_id',
                        'vk_id',
                        'sber_id',
                        'sms_code',
                        'emulator'
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
                'name': 'scope_company_id',
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
                'name': 'customer_identities_provider_provider_user_id_idx',
                'fields': [
                    'provider',
                    'provider_user_id'
                ],
                'unique': True,
                'method': None
            },
            {
                'name': 'customer_identities_customer_id_idx',
                'fields': [
                    'customer_id'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'customer_identities_verified_phone_e164_idx',
                'fields': [
                    'verified_phone_e164'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.alter_column("object_storages", "provider", default="'seaweedfs'")


def downgrade(ctx):
    """Revert migration."""
    ctx.drop_table("customer_identities")
    ctx.drop_table("customers")
    ctx.drop_enum_type('phone_verification_method_enum')
    ctx.drop_enum_type('customer_status_enum')
    ctx.drop_enum_type('customer_identity_provider_enum')
