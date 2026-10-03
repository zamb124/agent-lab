"""Чистка мёртвых настроек и фолбеков (аудит лаконичности).

* `reflex_point_enum` → только 'putaway' (единственная живaя точка).
* `stock_partner_role_enum` → без 'contractor' (локаций таких нет).
* `stock_storage_types.verify_bin_scan` — удалён (скан ячейки всегда
  обязателен в потоках; колонка нигде не читалась).
* `stock_storage_types.putaway_strategies` — text[] → enum[]
  (значения 'fixed_bin' отбрасываются: фиксированная ячейка теперь
  выражается StockPutawayRule, а не шагом цепочки).
* `stock_storage_types.removal_strategy` — nullable: None = «наследует
  стратегию склада».
* `stock_warehouses.layout_preset` — удалён: пресет — параметр
  создания топологии, а не состояние склада.
* `stock_warehouses.removal_strategy` — NOT NULL: стратегия склада —
  обязательное последнее звено цепочки «товар → тип хранения → склад»;
  NULL бэкфиллятся в 'fifo' (единственное осмысленное значение
  для уже существующих рядов).

Created: 2026-09-26
"""

depends_on = "0009_alter_reservation_policy_enum_enum"


def upgrade(ctx):
    """Apply migration."""
    ctx.create_enum_type('stock_putaway_strategy_enum', [
    'existing_stock',
    'empty_bin',
    'nearest',
    'manual'
])
    ctx.alter_enum_type(
        'reflex_point_enum',
        old_values=[
                       'putaway',
                       'removal',
                       'qc_route',
                       'receipt_lines'
                   ],
        new_values=[
                       'putaway'
                   ],
    )
    # reflex_point_enum: пересоздание типа (Postgres не умеет DROP VALUE).
    ctx.execute(
        "ALTER TABLE stock_decisions ALTER COLUMN reflex_point DROP DEFAULT"
    )
    ctx.execute(
        "ALTER TYPE reflex_point_enum RENAME TO reflex_point_enum_old"
    )
    ctx.execute("CREATE TYPE reflex_point_enum AS ENUM ('putaway')")
    ctx.execute(
        "ALTER TABLE stock_decisions ALTER COLUMN reflex_point TYPE reflex_point_enum USING reflex_point::text::reflex_point_enum"
    )
    ctx.execute("DROP TYPE reflex_point_enum_old")
    ctx.alter_enum_type(
        'stock_partner_role_enum',
        old_values=[
                       'vendor',
                       'customer',
                       'contractor'
                   ],
        new_values=[
                       'vendor',
                       'customer'
                   ],
    )
    # stock_partner_role_enum: то же пересоздание.
    ctx.execute(
        "ALTER TABLE stock_locations ALTER COLUMN partner_role DROP DEFAULT"
    )
    ctx.execute(
        "ALTER TYPE stock_partner_role_enum RENAME TO stock_partner_role_enum_old"
    )
    ctx.execute(
        "CREATE TYPE stock_partner_role_enum AS ENUM ('vendor', 'customer')"
    )
    ctx.execute(
        "ALTER TABLE stock_locations ALTER COLUMN partner_role TYPE stock_partner_role_enum USING partner_role::text::stock_partner_role_enum"
    )
    ctx.execute("DROP TYPE stock_partner_role_enum_old")
    ctx.drop_column("stock_storage_types", "verify_bin_scan")
    # putaway_strategies: text[] → enum[]; мёртвое 'fixed_bin'
    # отбрасывается чисткой до каста (фиксированное место —
    # StockPutawayRule). Пустая цепочка = «авторазмещения нет».
    # UPDATE сначала: в USING подзапросы запрещены.
    ctx.execute(
        "UPDATE stock_storage_types SET putaway_strategies = COALESCE((SELECT array_agg(v) FROM unnest(putaway_strategies) AS v WHERE v = ANY (ARRAY['existing_stock','empty_bin','nearest','manual'])), '{}')"
    )
    ctx.execute(
        "ALTER TABLE stock_storage_types ALTER COLUMN putaway_strategies TYPE stock_putaway_strategy_enum[] USING putaway_strategies::text[]::stock_putaway_strategy_enum[]"
    )
    ctx.execute(
        "ALTER TABLE stock_storage_types ALTER COLUMN putaway_strategies DROP DEFAULT"
    )
    # collect-трекинг типа колонки (в execute-режиме — no-op выше).
    ctx.alter_column("stock_storage_types", "putaway_strategies", column_type={
    'kind': 'array',
    'item': {
        'kind': 'enum',
        'name': 'stock_putaway_strategy_enum',
        'values': [
            'existing_stock',
            'empty_bin',
            'nearest',
            'manual'
        ]
    }
})
    ctx.alter_column("stock_storage_types", "removal_strategy", nullable=True, default=None)
    # Стратегия склада обязательна: NULL бэкфиллим до SET NOT NULL.
    ctx.execute(
        "UPDATE stock_warehouses SET removal_strategy = 'fifo' WHERE removal_strategy IS NULL"
    )
    ctx.drop_column("stock_warehouses", "layout_preset")
    ctx.alter_column("stock_warehouses", "removal_strategy", nullable=False)
    ctx.drop_enum_type('stock_layout_preset_enum')


def downgrade(ctx):
    """Revert migration."""
    ctx.create_enum_type('stock_layout_preset_enum', [
    'simple',
    'standard',
    'distribution_center'
])
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
    ctx.alter_column("stock_warehouses", "removal_strategy", nullable=True)
    ctx.add_column("stock_storage_types", {
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
})
    # putaway_strategies обратно в text[]
    ctx.execute(
        "ALTER TABLE stock_storage_types ALTER COLUMN putaway_strategies TYPE text[] USING putaway_strategies::text[]"
    )
    ctx.drop_enum_type('stock_putaway_strategy_enum')
    # stock_partner_role_enum обратно
    ctx.execute(
        "ALTER TABLE stock_locations ALTER COLUMN partner_role DROP DEFAULT"
    )
    ctx.execute(
        "ALTER TYPE stock_partner_role_enum RENAME TO stock_partner_role_enum_old"
    )
    ctx.execute(
        "CREATE TYPE stock_partner_role_enum AS ENUM ('vendor', 'customer', 'contractor')"
    )
    ctx.execute(
        "ALTER TABLE stock_locations ALTER COLUMN partner_role TYPE stock_partner_role_enum USING partner_role::text::stock_partner_role_enum"
    )
    ctx.execute("DROP TYPE stock_partner_role_enum_old")
    # reflex_point_enum обратно
    ctx.execute(
        "ALTER TABLE stock_decisions ALTER COLUMN reflex_point DROP DEFAULT"
    )
    ctx.execute(
        "ALTER TYPE reflex_point_enum RENAME TO reflex_point_enum_old"
    )
    ctx.execute(
        "CREATE TYPE reflex_point_enum AS ENUM ('putaway', 'removal', 'qc_route', 'receipt_lines')"
    )
    ctx.execute(
        "ALTER TABLE stock_decisions ALTER COLUMN reflex_point TYPE reflex_point_enum USING reflex_point::text::reflex_point_enum"
    )
    ctx.execute("DROP TYPE reflex_point_enum_old")
