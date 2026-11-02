"""Shop: заказ «в заведении» — ShopTable, Shop.onsite_enabled, ShopOrder.table_label."""

depends_on = "0009_category_hierarchy"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        "ALTER TYPE shop_delivery_type_enum ADD VALUE IF NOT EXISTS 'onsite'"
    )
    ctx.execute(
        "ALTER TABLE shop_shops "
        "ADD COLUMN IF NOT EXISTS onsite_enabled boolean NOT NULL DEFAULT false"
    )
    ctx.execute(
        "ALTER TABLE shop_orders "
        "ADD COLUMN IF NOT EXISTS table_id varchar(64) NOT NULL DEFAULT ''"
    )
    ctx.execute(
        "ALTER TABLE shop_orders "
        "ADD COLUMN IF NOT EXISTS table_label varchar(64) NOT NULL DEFAULT ''"
    )
    ctx.execute(
        "CREATE TABLE IF NOT EXISTS shop_tables ("
        "shop_table_id varchar(64) PRIMARY KEY, "
        "shop_id varchar(64) NOT NULL, "
        "label varchar(64) NOT NULL, "
        "created_at timestamptz NOT NULL, "
        "updated_at timestamptz NOT NULL"
        ")"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_tables_shop_id_idx "
        "ON shop_tables (shop_id)"
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute("DROP TABLE IF EXISTS shop_tables")
    ctx.execute("ALTER TABLE shop_orders DROP COLUMN IF EXISTS table_label")
    ctx.execute("ALTER TABLE shop_orders DROP COLUMN IF EXISTS table_id")
    ctx.execute("ALTER TABLE shop_shops DROP COLUMN IF EXISTS onsite_enabled")
