"""Shop: `customer_id` на заказе — привязка к платформенному покупателю (customers.mdc)."""

depends_on = "0010_onsite_tables"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        "ALTER TABLE shop_orders "
        "ADD COLUMN IF NOT EXISTS customer_id varchar(64) NOT NULL DEFAULT ''"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_orders_customer_id_idx "
        "ON shop_orders (customer_id)"
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute("DROP INDEX IF EXISTS shop_orders_customer_id_idx")
    ctx.execute("ALTER TABLE shop_orders DROP COLUMN IF EXISTS customer_id")
