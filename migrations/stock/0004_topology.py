"""Auto-generated migration.

Created: 2026-09-25 22:04:43
"""

depends_on = "0003_add_allow_negative_to_stock_locations"

# Колонки со ссылками на location_id виртуальных локаций (FK нет — текстовый
# детерминированный id). Перечислены все колонки stock-схемы с location_id.
_LOCATION_REF_COLUMNS = (
    ("stock_quants", ("location_id",)),
    ("stock_moves", ("location_id", "location_dest_id")),
    ("stock_move_lines", ("location_id", "location_dest_id", "container_id")),
    ("stock_value_layers", ("location_id", "location_dest_id")),
    ("stock_barcodes", ("entity_id",)),
    ("stock_decisions", ("chosen_location_id",)),
    (
        "stock_operation_types",
        ("default_source_location_id", "default_dest_location_id"),
    ),
    ("stock_putaway_rules", ("location_in_id", "location_out_id")),
    ("stock_warehouses", ("stock_location_id", "view_location_id")),
    ("stock_locations", ("parent_id",)),
)


def _rename_virtual_location_ids(ctx, pairs) -> None:
    """Каскадный rename детерминированных id виртуальных локаций.

    Без rename `init_company_stock` создаст дубли с новыми id поверх
    мигрированных строк. Regex `^[^:]*:suffix$` требует ровно одно двоеточие —
    новые id вида `{company}:partner:{role}` не задеваются повторными replace.
    """
    for old_suffix, new_suffix in pairs:
        row_pattern = f"^[^:]*{old_suffix}$"
        segment_pattern = f"/[^/:]*{old_suffix}/"
        for table, columns in _LOCATION_REF_COLUMNS:
            for column in columns:
                ctx.execute(
                    f"UPDATE {table} SET {column} = regexp_replace({column}, '{old_suffix}$', '{new_suffix}') WHERE {column} ~ '{row_pattern}'"
                )
        ctx.execute(
            f"UPDATE stock_locations SET parent_path = regexp_replace(parent_path, '(/[^/:]*){old_suffix}(/)', '\\1{new_suffix}\\2', 'g') WHERE parent_path ~ '{segment_pattern}'"
        )
        ctx.execute(
            "UPDATE stock_decisions SET candidate_location_ids = ("
            "SELECT COALESCE(jsonb_agg(to_jsonb(mapped)), '[]'::jsonb) FROM ("
            f"SELECT CASE WHEN v ~ '{row_pattern}' THEN regexp_replace(v, '{old_suffix}$', '{new_suffix}') ELSE v END AS mapped "
            "FROM jsonb_array_elements_text(candidate_location_ids) elem(v)"
            ") sub) WHERE EXISTS ("
            f"SELECT 1 FROM jsonb_array_elements_text(candidate_location_ids) elem(v) WHERE v ~ '{row_pattern}'"
            ")"
        )
        ctx.execute(
            f"UPDATE stock_locations SET location_id = regexp_replace(location_id, '{old_suffix}$', '{new_suffix}') WHERE location_id ~ '{row_pattern}' AND NOT EXISTS ("
            f"SELECT 1 FROM stock_locations dup WHERE dup.location_id = regexp_replace(stock_locations.location_id, '{old_suffix}$', '{new_suffix}'))"
        )


def upgrade(ctx):
    """Apply migration."""
    ctx.create_enum_type('stock_container_kind_enum', [
    'pallet',
    'box',
    'bag',
    'tote',
    'cart',
    'other'
])
    ctx.create_enum_type('stock_container_policy_enum', [
    'loose_only',
    'any',
    'container_only'
])
    ctx.create_enum_type('stock_layout_preset_enum', [
    'simple',
    'standard',
    'distribution_center'
])
    ctx.create_enum_type('stock_move_line_kind_enum', [
    'quantity',
    'container',
    'count'
])
    ctx.create_enum_type('stock_move_line_state_enum', [
    'open',
    'done',
    'cancelled'
])
    ctx.create_enum_type('stock_partner_role_enum', [
    'vendor',
    'customer',
    'contractor'
])
    ctx.create_enum_type('stock_product_mixing_enum', [
    'mixed',
    'same_product',
    'empty_only'
])
    ctx.create_enum_type('stock_removal_strategy_enum', [
    'fifo',
    'fefo',
    'lifo',
    'least_containers',
    'closest'
])
    ctx.add_enum_value(
        'backorder_policy_enum', 'ask',
        fields=[
                   {
                       'table': 'stock_operation_types',
                       'field': {
                           'name': 'backorder_policy',
                           'column_type': {
                               'kind': 'enum',
                               'name': 'backorder_policy_enum',
                               'values': [
                                   'always',
                                   'never',
                                   'ask'
                               ]
                           },
                           'db_type': None,
                           'nullable': False,
                           'primary_key': False,
                           'unique': False,
                           'default': "'always'",
                           'auto_increment': False,
                           'max_length': None,
                           'max_digits': None,
                           'decimal_places': None
                       }
                   }
               ],
    )
    ctx.alter_enum_type(
        'stock_barcode_entity_type_enum',
        old_values=[
                       'product',
                       'location',
                       'package',
                       'lot',
                       'transfer'
                   ],
        new_values=[
                       'product',
                       'packaging',
                       'location',
                       'container',
                       'lot',
                       'transfer',
                       'resource'
                   ],
    )
    # package→packaging, +container/+resource: Postgres не умеет переименовывать
    # значения enum — пересоздание типа с маппингом данных.
    ctx.execute(
        "ALTER TYPE stock_barcode_entity_type_enum RENAME TO stock_barcode_entity_type_enum_old"
    )
    ctx.execute(
        "CREATE TYPE stock_barcode_entity_type_enum AS ENUM ('product', 'packaging', 'location', 'container', 'lot', 'transfer', 'resource')"
    )
    ctx.execute(
        "ALTER TABLE stock_barcodes ALTER COLUMN entity_type TYPE stock_barcode_entity_type_enum USING (CASE entity_type::text WHEN 'package' THEN 'packaging' WHEN 'container' THEN 'container' WHEN 'resource' THEN 'resource' ELSE entity_type::text END)::stock_barcode_entity_type_enum"
    )
    ctx.execute("DROP TYPE stock_barcode_entity_type_enum_old")
    ctx.alter_enum_type(
        'stock_location_usage_enum',
        old_values=[
                       'view',
                       'internal',
                       'supplier',
                       'customer',
                       'inventory',
                       'production',
                       'transit'
                   ],
        new_values=[
                       'view',
                       'bin',
                       'container',
                       'partner',
                       'transit',
                       'adjustment'
                   ],
    )
    # internal→bin, supplier/customer/production→partner, inventory→adjustment.
    ctx.execute(
        "ALTER TYPE stock_location_usage_enum RENAME TO stock_location_usage_enum_old"
    )
    ctx.execute(
        "CREATE TYPE stock_location_usage_enum AS ENUM ('view', 'bin', 'container', 'partner', 'transit', 'adjustment')"
    )
    ctx.execute(
        "ALTER TABLE stock_locations ALTER COLUMN usage TYPE stock_location_usage_enum USING (CASE usage::text WHEN 'internal' THEN 'bin' WHEN 'supplier' THEN 'partner' WHEN 'customer' THEN 'partner' WHEN 'inventory' THEN 'adjustment' WHEN 'production' THEN 'partner' ELSE usage::text END)::stock_location_usage_enum"
    )
    ctx.execute("DROP TYPE stock_location_usage_enum_old")
    ctx.create_table(
        "stock_storage_types",
        fields=[
            {
                'name': 'storage_type_id',
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
                'name': 'container_policy',
                'column_type': {
                    'kind': 'enum',
                    'name': 'stock_container_policy_enum',
                    'values': [
                        'loose_only',
                        'any',
                        'container_only'
                    ]
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'any'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'allowed_container_type_ids',
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
                'name': 'max_containers',
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
                'name': 'product_mixing',
                'column_type': {
                    'kind': 'enum',
                    'name': 'stock_product_mixing_enum',
                    'values': [
                        'mixed',
                        'same_product',
                        'empty_only'
                    ]
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'mixed'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'allow_mixed_lots',
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
                'name': 'max_weight',
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
            },
            {
                'name': 'max_volume',
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
            },
            {
                'name': 'putaway_strategies',
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
                'name': 'removal_strategy',
                'column_type': {
                    'kind': 'enum',
                    'name': 'stock_removal_strategy_enum',
                    'values': [
                        'fifo',
                        'fefo',
                        'lifo',
                        'least_containers',
                        'closest'
                    ]
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'fifo'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'verify_bin_scan',
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
                'name': 'cycle_count_days',
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
                'name': 'stock_storage_types_company_id_warehouse_id_name_idx',
                'fields': [
                    'company_id',
                    'warehouse_id',
                    'name'
                ],
                'unique': True,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "stock_resources",
        fields=[
            {
                'name': 'resource_id',
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
                'name': 'resource_type_id',
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
                'name': 'code',
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
                'name': 'barcode',
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
                'name': 'current_user_id',
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
                'name': 'logged_in_at',
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
                'name': 'stock_resources_company_id_warehouse_id_code_idx',
                'fields': [
                    'company_id',
                    'warehouse_id',
                    'code'
                ],
                'unique': True,
                'method': None
            },
            {
                'name': 'stock_resources_company_id_barcode_idx',
                'fields': [
                    'company_id',
                    'barcode'
                ],
                'unique': False,
                'method': None
            },
            {
                'name': 'stock_resources_company_id_current_user_id_idx',
                'fields': [
                    'company_id',
                    'current_user_id'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "stock_resource_types",
        fields=[
            {
                'name': 'resource_type_id',
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
                'name': 'allowed_container_type_ids',
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
                'name': 'handles_loose',
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
                'name': 'max_level',
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
                'name': 'max_load_weight',
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
            },
            {
                'name': 'storage_type_ids',
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
                'name': 'stock_resource_types_company_id_warehouse_id_name_idx',
                'fields': [
                    'company_id',
                    'warehouse_id',
                    'name'
                ],
                'unique': True,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "stock_product_packagings",
        fields=[
            {
                'name': 'packaging_id',
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
                'name': 'product_id',
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
                'name': 'quantity',
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
                'name': 'barcode',
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
                'name': 'stock_product_packagings_company_id_product_id_name_idx',
                'fields': [
                    'company_id',
                    'product_id',
                    'name'
                ],
                'unique': True,
                'method': None
            },
            {
                'name': 'stock_product_packagings_company_id_barcode_idx',
                'fields': [
                    'company_id',
                    'barcode'
                ],
                'unique': False,
                'method': None
            }
        ],
    )
    ctx.create_table(
        "stock_container_types",
        fields=[
            {
                'name': 'container_type_id',
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
                'name': 'kind',
                'column_type': {
                    'kind': 'enum',
                    'name': 'stock_container_kind_enum',
                    'values': [
                        'pallet',
                        'box',
                        'bag',
                        'tote',
                        'cart',
                        'other'
                    ]
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'other'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None
            },
            {
                'name': 'max_weight',
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
            },
            {
                'name': 'tare_weight',
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
            },
            {
                'name': 'max_volume',
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
            },
            {
                'name': 'length',
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
            },
            {
                'name': 'width',
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
            },
            {
                'name': 'height',
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
            },
            {
                'name': 'is_reusable',
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
                'name': 'allowed_parent_type_ids',
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
                'name': 'stock_container_types_company_id_warehouse_id_name_idx',
                'fields': [
                    'company_id',
                    'warehouse_id',
                    'name'
                ],
                'unique': True,
                'method': None
            }
        ],
    )
    ctx.drop_table("stock_package_types")
    ctx.drop_table("stock_packages")
    ctx.add_column("stock_locations", {
    'name': 'parent_path',
    'column_type': {
        'kind': 'string',
        'length': 2048
    },
    'db_type': None,
    'nullable': False,
    'primary_key': False,
    'unique': False,
    'default': "'/'",
    'auto_increment': False,
    'max_length': 2048,
    'max_digits': None,
    'decimal_places': None
})
    ctx.add_column("stock_locations", {
    'name': 'complete_name',
    'column_type': {
        'kind': 'string',
        'length': 512
    },
    'db_type': None,
    'nullable': False,
    'primary_key': False,
    'unique': False,
    'default': "''",
    'auto_increment': False,
    'max_length': 512,
    'max_digits': None,
    'decimal_places': None
})
    ctx.add_column("stock_locations", {
    'name': 'partner_role',
    'column_type': {
        'kind': 'enum',
        'name': 'stock_partner_role_enum',
        'values': [
            'vendor',
            'customer',
            'contractor'
        ]
    },
    'db_type': None,
    'nullable': True,
    'primary_key': False,
    'unique': False,
    'default': None,
    'auto_increment': False,
    'max_length': 32,
    'max_digits': None,
    'decimal_places': None
})
    # Роль partner-локации по старому детерминированному id ({company}:supplier).
    ctx.execute(
        "UPDATE stock_locations SET partner_role = 'vendor'::stock_partner_role_enum WHERE usage = 'partner' AND location_id LIKE '%:supplier'"
    )
    ctx.execute(
        "UPDATE stock_locations SET partner_role = 'customer'::stock_partner_role_enum WHERE usage = 'partner' AND location_id LIKE '%:customer'"
    )
    ctx.add_column("stock_locations", {
    'name': 'storage_type_id',
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
    ctx.add_column("stock_locations", {
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
})
    ctx.add_column("stock_locations", {
    'name': 'level',
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
})
    ctx.add_column("stock_locations", {
    'name': 'pick_sequence',
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
})
    ctx.add_column("stock_locations", {
    'name': 'putaway_blocked',
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
})
    ctx.add_column("stock_locations", {
    'name': 'removal_blocked',
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
})
    ctx.add_column("stock_locations", {
    'name': 'last_count_at',
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
})
    ctx.drop_column("stock_locations", "removal_method")
    ctx.add_column("stock_lots", {
    'name': 'best_before_at',
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
})
    ctx.add_column("stock_lots", {
    'name': 'removal_at',
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
})
    ctx.add_column("stock_lots", {
    'name': 'alert_at',
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
})
    ctx.add_column("stock_move_lines", {
    'name': 'transfer_id',
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
    ctx.add_column("stock_move_lines", {
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
})
    ctx.add_column("stock_move_lines", {
    'name': 'kind',
    'column_type': {
        'kind': 'enum',
        'name': 'stock_move_line_kind_enum',
        'values': [
            'quantity',
            'container',
            'count'
        ]
    },
    'db_type': None,
    'nullable': False,
    'primary_key': False,
    'unique': False,
    'default': "'quantity'",
    'auto_increment': False,
    'max_length': None,
    'max_digits': None,
    'decimal_places': None
})
    ctx.add_column("stock_move_lines", {
    'name': 'state',
    'column_type': {
        'kind': 'enum',
        'name': 'stock_move_line_state_enum',
        'values': [
            'open',
            'done',
            'cancelled'
        ]
    },
    'db_type': None,
    'nullable': False,
    'primary_key': False,
    'unique': False,
    'default': "'open'",
    'auto_increment': False,
    'max_length': None,
    'max_digits': None,
    'decimal_places': None
})
    ctx.add_column("stock_move_lines", {
    'name': 'container_id',
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
    ctx.add_column("stock_move_lines", {
    'name': 'assigned_user_id',
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
    ctx.add_column("stock_move_lines", {
    'name': 'resource_id',
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
    ctx.add_column("stock_move_lines", {
    'name': 'claimed_at',
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
})
    ctx.add_column("stock_move_lines", {
    'name': 'wave_id',
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
    ctx.add_column("stock_move_lines", {
    'name': 'sequence',
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
})
    ctx.add_column("stock_move_lines", {
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
})
    ctx.add_column("stock_move_lines", {
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
})
    ctx.add_column("stock_move_lines", {
    'name': 'done_by_user_id',
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
    ctx.drop_column("stock_move_lines", "package_id")
    ctx.drop_column("stock_move_lines", "result_package_id")
    ctx.add_column("stock_moves", {
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
})
    ctx.add_column("stock_moves", {
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
})
    ctx.add_column("stock_moves", {
    'name': 'date_deadline',
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
})
    ctx.drop_column("stock_moves", "predecessor_move_id")
    ctx.add_column("stock_operation_types", {
    'name': 'name_prefix',
    'column_type': {
        'kind': 'string',
        'length': 32
    },
    'db_type': None,
    'nullable': True,
    'primary_key': False,
    'unique': False,
    'default': None,
    'auto_increment': False,
    'max_length': 32,
    'max_digits': None,
    'decimal_places': None
})
    ctx.add_column("stock_operation_types", {
    'name': 'create_lots',
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
})
    ctx.add_column("stock_operation_types", {
    'name': 'use_existing_lots',
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
})
    ctx.add_column("stock_operation_types", {
    'name': 'return_operation_type_id',
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
    ctx.add_column("stock_product_templates", {
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
    ctx.add_column("stock_product_templates", {
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
    ctx.add_column("stock_product_templates", {
    'name': 'use_expiration',
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
})
    ctx.add_column("stock_product_templates", {
    'name': 'expiration_days',
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
})
    ctx.add_column("stock_product_templates", {
    'name': 'best_before_days',
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
})
    ctx.add_column("stock_product_templates", {
    'name': 'removal_days',
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
})
    ctx.add_column("stock_product_templates", {
    'name': 'alert_days',
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
})
    ctx.add_column("stock_product_templates", {
    'name': 'removal_strategy',
    'column_type': {
        'kind': 'enum',
        'name': 'stock_removal_strategy_enum',
        'values': [
            'fifo',
            'fefo',
            'lifo',
            'least_containers',
            'closest'
        ]
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
})
    ctx.add_column("stock_quants", {
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
})
    ctx.add_column("stock_quants", {
    'name': 'inventory_counted_at',
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
})
    ctx.add_column("stock_quants", {
    'name': 'inventory_user_id',
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
    ctx.add_column("stock_quants", {
    'name': 'removal_at',
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
})
    ctx.drop_column("stock_quants", "package_id")
    ctx.add_column("stock_transfers", {
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
})
    ctx.add_column("stock_transfers", {
    'name': 'date_deadline',
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
})
    ctx.add_column("stock_warehouses", {
    'name': 'layout_preset',
    'column_type': {
        'kind': 'enum',
        'name': 'stock_layout_preset_enum',
        'values': [
            'simple',
            'standard',
            'distribution_center'
        ]
    },
    'db_type': None,
    'nullable': False,
    'primary_key': False,
    'unique': False,
    'default': "'simple'",
    'auto_increment': False,
    'max_length': None,
    'max_digits': None,
    'decimal_places': None
})
    ctx.add_column("stock_warehouses", {
    'name': 'removal_strategy',
    'column_type': {
        'kind': 'enum',
        'name': 'stock_removal_strategy_enum',
        'values': [
            'fifo',
            'fefo',
            'lifo',
            'least_containers',
            'closest'
        ]
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
})
    ctx.create_index("stock_locations", {
    'name': 'stock_locations_company_id_parent_path_idx',
    'fields': [
        'company_id',
        'parent_path'
    ],
    'unique': False,
    'method': None
})
    ctx.create_index("stock_move_lines", {
    'name': 'stock_move_lines_company_id_warehouse_id_state_idx',
    'fields': [
        'company_id',
        'warehouse_id',
        'state'
    ],
    'unique': False,
    'method': None
})
    ctx.create_index("stock_move_lines", {
    'name': 'stock_move_lines_company_id_assigned_user_id_state_idx',
    'fields': [
        'company_id',
        'assigned_user_id',
        'state'
    ],
    'unique': False,
    'method': None
})
    ctx.create_index("stock_move_lines", {
    'name': 'stock_move_lines_company_id_container_id_idx',
    'fields': [
        'company_id',
        'container_id'
    ],
    'unique': False,
    'method': None
})
    ctx.create_index("stock_quants", {
    'name': 'stock_quants_company_id_warehouse_id_product_id_idx',
    'fields': [
        'company_id',
        'warehouse_id',
        'product_id'
    ],
    'unique': False,
    'method': None
})
    # Rename в конце: все колонки уже созданы (container_id, parent_path …).
    _rename_virtual_location_ids(
        ctx,
        (
            (":supplier", ":partner:vendor"),
            (":customer", ":partner:customer"),
            (":inventory", ":adjustment"),
        ),
    )
    # Материализация parent_path/complete_name/level для legacy-строк:
    # колонки новые, иерархия восстанавливается по parent_id-цепочке.
    ctx.execute(
        "WITH RECURSIVE tree AS ("
        "SELECT location_id, company_id, ('/' || location_id || '/')::text AS path, name::text AS cname, 1 AS lvl "
        "FROM stock_locations WHERE parent_id IS NULL "
        "UNION ALL "
        "SELECT c.location_id, c.company_id, t.path || c.location_id || '/', t.cname || '/' || c.name, t.lvl + 1 "
        "FROM stock_locations c JOIN tree t ON c.parent_id = t.location_id AND c.company_id = t.company_id "
        "WHERE t.lvl < 100"
        ") "
        "UPDATE stock_locations l SET parent_path = t.path, complete_name = t.cname "
        "FROM tree t WHERE l.location_id = t.location_id AND l.company_id = t.company_id"
    )


def downgrade(ctx):
    """Revert migration."""
    # Rename в начале: parent_path и прочие колонки ещё существуют.
    _rename_virtual_location_ids(
        ctx,
        (
            (":partner:vendor", ":supplier"),
            (":partner:customer", ":customer"),
            (":adjustment", ":inventory"),
        ),
    )
    ctx.drop_index("stock_quants", "stock_quants_company_id_warehouse_id_product_id_idx")
    ctx.drop_index("stock_move_lines", "stock_move_lines_company_id_container_id_idx")
    ctx.drop_index("stock_move_lines", "stock_move_lines_company_id_assigned_user_id_state_idx")
    ctx.drop_index("stock_move_lines", "stock_move_lines_company_id_warehouse_id_state_idx")
    ctx.drop_index("stock_locations", "stock_locations_company_id_parent_path_idx")
    ctx.drop_column("stock_warehouses", "removal_strategy")
    ctx.drop_column("stock_warehouses", "layout_preset")
    ctx.drop_column("stock_transfers", "date_deadline")
    ctx.drop_column("stock_transfers", "priority")
    ctx.add_column("stock_quants", {
    'name': 'package_id',
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
    ctx.drop_column("stock_quants", "removal_at")
    ctx.drop_column("stock_quants", "inventory_user_id")
    ctx.drop_column("stock_quants", "inventory_counted_at")
    ctx.drop_column("stock_quants", "warehouse_id")
    ctx.drop_column("stock_product_templates", "removal_strategy")
    ctx.drop_column("stock_product_templates", "alert_days")
    ctx.drop_column("stock_product_templates", "removal_days")
    ctx.drop_column("stock_product_templates", "best_before_days")
    ctx.drop_column("stock_product_templates", "expiration_days")
    ctx.drop_column("stock_product_templates", "use_expiration")
    ctx.drop_column("stock_product_templates", "volume")
    ctx.drop_column("stock_product_templates", "weight")
    ctx.drop_column("stock_operation_types", "return_operation_type_id")
    ctx.drop_column("stock_operation_types", "use_existing_lots")
    ctx.drop_column("stock_operation_types", "create_lots")
    ctx.drop_column("stock_operation_types", "name_prefix")
    ctx.add_column("stock_moves", {
    'name': 'predecessor_move_id',
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
    ctx.drop_column("stock_moves", "date_deadline")
    ctx.drop_column("stock_moves", "priority")
    ctx.drop_column("stock_moves", "warehouse_id")
    ctx.add_column("stock_move_lines", {
    'name': 'result_package_id',
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
    ctx.add_column("stock_move_lines", {
    'name': 'package_id',
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
    ctx.drop_column("stock_move_lines", "done_by_user_id")
    ctx.drop_column("stock_move_lines", "done_at")
    ctx.drop_column("stock_move_lines", "priority")
    ctx.drop_column("stock_move_lines", "sequence")
    ctx.drop_column("stock_move_lines", "wave_id")
    ctx.drop_column("stock_move_lines", "claimed_at")
    ctx.drop_column("stock_move_lines", "resource_id")
    ctx.drop_column("stock_move_lines", "assigned_user_id")
    ctx.drop_column("stock_move_lines", "container_id")
    ctx.drop_column("stock_move_lines", "state")
    ctx.drop_column("stock_move_lines", "kind")
    ctx.drop_column("stock_move_lines", "warehouse_id")
    ctx.drop_column("stock_move_lines", "transfer_id")
    ctx.drop_column("stock_lots", "alert_at")
    ctx.drop_column("stock_lots", "removal_at")
    ctx.drop_column("stock_lots", "best_before_at")
    ctx.add_column("stock_locations", {
    'name': 'removal_method',
    'column_type': {
        'kind': 'string',
        'length': 32
    },
    'db_type': None,
    'nullable': False,
    'primary_key': False,
    'unique': False,
    'default': "'fifo'",
    'auto_increment': False,
    'max_length': 32,
    'max_digits': None,
    'decimal_places': None
})
    ctx.drop_column("stock_locations", "last_count_at")
    ctx.drop_column("stock_locations", "removal_blocked")
    ctx.drop_column("stock_locations", "putaway_blocked")
    ctx.drop_column("stock_locations", "pick_sequence")
    ctx.drop_column("stock_locations", "level")
    ctx.drop_column("stock_locations", "container_type_id")
    ctx.drop_column("stock_locations", "storage_type_id")
    ctx.drop_column("stock_locations", "partner_role")
    ctx.drop_column("stock_locations", "complete_name")
    ctx.drop_column("stock_locations", "parent_path")
    ctx.create_table(
        "stock_packages",
        fields=[
                       {
                           'name': 'package_id',
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
                           'name': 'package_type_id',
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
                           'name': 'parent_package_id',
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
                           'name': 'location_id',
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
                           'name': 'barcode',
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
                             'name': 'stock_packages_company_id_barcode_idx',
                             'fields': [
                                 'company_id',
                                 'barcode'
                             ],
                             'unique': False,
                             'method': None
                         }
                     ],
    )
    ctx.create_table(
        "stock_package_types",
        fields=[
                       {
                           'name': 'package_type_id',
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
                             'name': 'stock_package_types_company_id_name_idx',
                             'fields': [
                                 'company_id',
                                 'name'
                             ],
                             'unique': True,
                             'method': None
                         }
                     ],
    )
    ctx.drop_table("stock_container_types")
    ctx.drop_table("stock_product_packagings")
    ctx.drop_table("stock_resource_types")
    ctx.drop_table("stock_resources")
    ctx.drop_table("stock_storage_types")
    ctx.alter_enum_type(
        'stock_location_usage_enum',
        old_values=[
                       'view',
                       'bin',
                       'container',
                       'partner',
                       'transit',
                       'adjustment'
                   ],
        new_values=[
                       'view',
                       'internal',
                       'supplier',
                       'customer',
                       'inventory',
                       'production',
                       'transit'
                   ],
    )
    # Откат enum — пересоздание типа; partner_role уже удалён, потому
    # partner-строки различаются по суффиксу детерминированного id
    # (rename выше вернул ':supplier'/':customer'/':inventory').
    ctx.execute(
        "ALTER TYPE stock_location_usage_enum RENAME TO stock_location_usage_enum_old"
    )
    ctx.execute(
        "CREATE TYPE stock_location_usage_enum AS ENUM ('view', 'internal', 'supplier', 'customer', 'inventory', 'production', 'transit')"
    )
    ctx.execute(
        "ALTER TABLE stock_locations ALTER COLUMN usage TYPE stock_location_usage_enum USING (CASE WHEN usage::text = 'partner' AND location_id ~ ':customer$' THEN 'customer' WHEN usage::text = 'partner' AND location_id ~ ':production$' THEN 'production' WHEN usage::text = 'partner' THEN 'supplier' WHEN usage::text = 'bin' THEN 'internal' WHEN usage::text = 'container' THEN 'internal' WHEN usage::text = 'adjustment' THEN 'inventory' ELSE usage::text END)::stock_location_usage_enum"
    )
    ctx.execute("DROP TYPE stock_location_usage_enum_old")
    ctx.alter_enum_type(
        'stock_barcode_entity_type_enum',
        old_values=[
                       'product',
                       'packaging',
                       'location',
                       'container',
                       'lot',
                       'transfer',
                       'resource'
                   ],
        new_values=[
                       'product',
                       'location',
                       'package',
                       'lot',
                       'transfer'
                   ],
    )
    ctx.execute(
        "ALTER TYPE stock_barcode_entity_type_enum RENAME TO stock_barcode_entity_type_enum_old"
    )
    ctx.execute(
        "CREATE TYPE stock_barcode_entity_type_enum AS ENUM ('product', 'location', 'package', 'lot', 'transfer')"
    )
    ctx.execute(
        "ALTER TABLE stock_barcodes ALTER COLUMN entity_type TYPE stock_barcode_entity_type_enum USING (CASE entity_type::text WHEN 'packaging' THEN 'package' WHEN 'container' THEN 'location' WHEN 'resource' THEN 'location' ELSE entity_type::text END)::stock_barcode_entity_type_enum"
    )
    ctx.execute("DROP TYPE stock_barcode_entity_type_enum_old")
    # Postgres не удаляет значения enum — rebuild типа с отображением 'ask'→'always'.
    ctx.execute(
        "ALTER TYPE backorder_policy_enum RENAME TO backorder_policy_enum_old"
    )
    ctx.execute(
        "CREATE TYPE backorder_policy_enum AS ENUM ('always', 'never')"
    )
    ctx.execute(
        "ALTER TABLE stock_operation_types ALTER COLUMN backorder_policy DROP DEFAULT"
    )
    ctx.execute(
        "ALTER TABLE stock_operation_types ALTER COLUMN backorder_policy TYPE backorder_policy_enum USING (CASE backorder_policy::text WHEN 'ask' THEN 'always' ELSE backorder_policy::text END)::backorder_policy_enum"
    )
    ctx.execute(
        "ALTER TABLE stock_operation_types ALTER COLUMN backorder_policy SET DEFAULT 'always'::backorder_policy_enum"
    )
    ctx.execute("DROP TYPE backorder_policy_enum_old")
    ctx.drop_enum_type('stock_removal_strategy_enum')
    ctx.drop_enum_type('stock_product_mixing_enum')
    ctx.drop_enum_type('stock_partner_role_enum')
    ctx.drop_enum_type('stock_move_line_state_enum')
    ctx.drop_enum_type('stock_move_line_kind_enum')
    ctx.drop_enum_type('stock_layout_preset_enum')
    ctx.drop_enum_type('stock_container_policy_enum')
    ctx.drop_enum_type('stock_container_kind_enum')
