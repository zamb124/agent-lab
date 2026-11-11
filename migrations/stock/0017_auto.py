"""Auto-generated migration.

Created: 2026-11-11 10:00:34
"""

depends_on = "0016_wave_stops_line_sequence"


def upgrade(ctx):
    """Apply migration."""
    ctx.drop_index("stock_move_lines", "stock_move_lines_queue_idx")
    ctx.drop_index("stock_products", "stock_products_company_id_sku_idx")
    ctx.drop_table("stock_uom")
    ctx.drop_column("stock_products", "sku")
    ctx.drop_column("stock_products", "uom_id")
    ctx.drop_column("stock_products", "name")
    ctx.drop_column("stock_products", "weight")
    ctx.drop_column("stock_products", "volume")
    ctx.alter_column("stock_waves", "stops", default=None)
    ctx.create_index("stock_products", {
    'name': 'stock_products_company_id_product_id_idx',
    'fields': [
        'company_id',
        'product_id'
    ],
    'unique': False,
    'method': None
})


def downgrade(ctx):
    """Revert migration."""
    ctx.drop_index("stock_products", "stock_products_company_id_product_id_idx")
    ctx.add_column("stock_products", {
    'name': 'volume',
    'column_type': {
        'kind': 'decimal',
        'precision': 24,
        'scale': 6
    },
    'db_type': 'NUMERIC(24,6)',
    'nullable': True,
    'primary_key': False,
    'unique': False,
    'default': None,
    'auto_increment': False,
    'max_length': None,
    'max_digits': None,
    'decimal_places': None
})
    ctx.add_column("stock_products", {
    'name': 'weight',
    'column_type': {
        'kind': 'decimal',
        'precision': 24,
        'scale': 6
    },
    'db_type': 'NUMERIC(24,6)',
    'nullable': True,
    'primary_key': False,
    'unique': False,
    'default': None,
    'auto_increment': False,
    'max_length': None,
    'max_digits': None,
    'decimal_places': None
})
    ctx.add_column("stock_products", {
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
})
    ctx.add_column("stock_products", {
    'name': 'uom_id',
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
})
    ctx.add_column("stock_products", {
    'name': 'sku',
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
})
    ctx.create_table(
        "stock_uom",
        fields=[
                       {
                           'name': 'uom_id',
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
                           'name': 'category',
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
                           'name': 'factor',
                           'column_type': {
                               'kind': 'decimal',
                               'precision': 20,
                               'scale': 6
                           },
                           'db_type': 'NUMERIC(20,6)',
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
                           'name': 'is_reference',
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
                           'name': 'product_id',
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
                           'name': 'container_type_id',
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
                           'name': 'weight',
                           'column_type': {
                               'kind': 'decimal',
                               'precision': 20,
                               'scale': 6
                           },
                           'db_type': 'NUMERIC(20,6)',
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
                           'name': 'volume',
                           'column_type': {
                               'kind': 'decimal',
                               'precision': 20,
                               'scale': 6
                           },
                           'db_type': 'NUMERIC(20,6)',
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
                             'name': 'stock_uom_company_id_name_idx',
                             'fields': [
                                 'company_id',
                                 'name'
                             ],
                             'unique': True,
                             'method': None,
                             'where': 'product_id IS NULL'
                         },
                         {
                             'name': 'stock_uom_company_id_product_id_name_idx',
                             'fields': [
                                 'company_id',
                                 'product_id',
                                 'name'
                             ],
                             'unique': True,
                             'method': None,
                             'where': 'product_id IS NOT NULL'
                         }
                     ],
    )
    ctx.create_index("stock_products", {
    'name': 'stock_products_company_id_sku_idx',
    'fields': [
        'company_id',
        'sku'
    ],
    'unique': True,
    'method': None
})
    ctx.create_index("stock_move_lines", {
    'name': 'stock_move_lines_queue_idx',
    'fields': [
        'company_id',
        'warehouse_id',
        'state',
        'stop_order',
        'sequence'
    ],
    'unique': False,
    'method': None
})
