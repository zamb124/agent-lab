"""Auto-generated migration.

Created: 2026-09-26 12:33:18
"""

depends_on = "0005_create_stock_wave_state_enum_enum"


def upgrade(ctx):
    """Apply migration."""
    ctx.create_table(
        "stock_routes",
        fields=[
            {
                'name': 'route_id',
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
                'name': 'code',
                'column_type': {
                    'kind': 'string',
                    'length': 64
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "''",
                'auto_increment': False,
                'max_length': 64,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'is_active',
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
                'name': 'stock_routes_company_id_warehouse_id_idx',
                'fields': [
                    'company_id',
                    'warehouse_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "stock_route_steps",
        fields=[
            {
                'name': 'step_id',
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
                'name': 'route_id',
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
                'name': 'sequence',
                'column_type': {
                    'kind': 'big_integer'
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': '10',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'operation_type_id',
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
                'name': 'source_location_id',
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
                'name': 'dest_location_id',
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
                'name': 'stock_route_steps_company_id_route_id_idx',
                'fields': [
                    'company_id',
                    'route_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.add_column("stock_moves", {
    'name': 'route_id',
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
})
    ctx.add_column("stock_moves", {
    'name': 'move_origin_id',
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
})
    ctx.add_column("stock_moves", {
    'name': 'move_dest_id',
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
})


def downgrade(ctx):
    """Revert migration."""
    ctx.drop_column("stock_moves", "move_dest_id")
    ctx.drop_column("stock_moves", "move_origin_id")
    ctx.drop_column("stock_moves", "route_id")
    ctx.drop_table("stock_route_steps")
    ctx.drop_table("stock_routes")
