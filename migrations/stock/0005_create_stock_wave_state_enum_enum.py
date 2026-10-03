"""Auto-generated migration.

Created: 2026-09-26 12:03:08
"""

depends_on = "0004_topology"


def upgrade(ctx):
    """Apply migration."""
    ctx.create_enum_type('stock_wave_state_enum', [
    'draft',
    'released',
    'done',
    'cancelled'
])
    ctx.create_table(
        "stock_waves",
        fields=[
            {
                'name': 'wave_id',
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
                'name': 'warehouse_id',
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
                'name': 'name',
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
                'name': 'state',
                'column_type': {
                    'kind': 'enum',
                    'name': 'stock_wave_state_enum',
                    'values': [
                        'draft',
                        'released',
                        'done',
                        'cancelled'
                    ]
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'draft'",
                'auto_increment': False,
                'max_length': 16,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'priority',
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
                'name': 'user_id',
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
                'name': 'line_count',
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
                'name': 'released_at',
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
                'name': 'done_at',
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
            }
        ],
        indexes=[
            {
                'name': 'stock_waves_company_id_warehouse_id_state_idx',
                'fields': [
                    'company_id',
                    'warehouse_id',
                    'state'
                ],
                'unique': False,
                'method': None
            }
        ],
    )


def downgrade(ctx):
    """Revert migration."""
    ctx.drop_table("stock_waves")
    ctx.drop_enum_type('stock_wave_state_enum')
