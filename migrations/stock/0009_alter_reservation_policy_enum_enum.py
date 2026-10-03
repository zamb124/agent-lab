"""Auto-generated migration.

Created: 2026-09-26 13:46:19
"""

depends_on = "0008_auto"


def upgrade(ctx):
    """Apply migration."""
    ctx.alter_enum_type(
        'reservation_policy_enum',
        old_values=[
                       'at_confirm',
                       'manual',
                       'by_date'
                   ],
        new_values=[
                       'at_confirm',
                       'manual'
                   ],
    )
    # by_date удалён: пересоздание типа, мёртвое значение маппится в manual.
    # DEFAULT сначала сбрасываем — он привязан к старому типу.
    ctx.execute(
        "ALTER TABLE stock_operation_types ALTER COLUMN reservation_policy DROP DEFAULT"
    )
    ctx.execute(
        "ALTER TYPE reservation_policy_enum RENAME TO reservation_policy_enum_old"
    )
    ctx.execute(
        "CREATE TYPE reservation_policy_enum AS ENUM ('at_confirm', 'manual')"
    )
    ctx.execute(
        "ALTER TABLE stock_operation_types ALTER COLUMN reservation_policy TYPE reservation_policy_enum USING (CASE reservation_policy::text WHEN 'by_date' THEN 'manual' ELSE reservation_policy::text END)::reservation_policy_enum"
    )
    ctx.execute(
        "ALTER TABLE stock_operation_types ALTER COLUMN reservation_policy SET DEFAULT 'manual'::reservation_policy_enum"
    )
    ctx.execute("DROP TYPE reservation_policy_enum_old")
    ctx.add_column("stock_putaway_rules", {
    'name': 'owner_entity_id',
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
    ctx.add_column("stock_putaway_rules", {
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
})
    ctx.add_column("stock_reorder_rules", {
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


def downgrade(ctx):
    """Revert migration."""
    ctx.drop_column("stock_reorder_rules", "route_id")
    ctx.drop_column("stock_putaway_rules", "is_active")
    ctx.drop_column("stock_putaway_rules", "owner_entity_id")
    ctx.alter_enum_type(
        'reservation_policy_enum',
        old_values=[
                       'at_confirm',
                       'manual'
                   ],
        new_values=[
                       'at_confirm',
                       'manual',
                       'by_date'
                   ],
    )
    ctx.execute(
        "ALTER TABLE stock_operation_types ALTER COLUMN reservation_policy DROP DEFAULT"
    )
    ctx.execute(
        "ALTER TYPE reservation_policy_enum RENAME TO reservation_policy_enum_old"
    )
    ctx.execute(
        "CREATE TYPE reservation_policy_enum AS ENUM ('at_confirm', 'manual', 'by_date')"
    )
    ctx.execute(
        "ALTER TABLE stock_operation_types ALTER COLUMN reservation_policy TYPE reservation_policy_enum USING reservation_policy::text::reservation_policy_enum"
    )
    ctx.execute(
        "ALTER TABLE stock_operation_types ALTER COLUMN reservation_policy SET DEFAULT 'manual'::reservation_policy_enum"
    )
    ctx.execute("DROP TYPE reservation_policy_enum_old")
