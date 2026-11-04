"""Shop: `delivery_zone` — GeoJSON-полигон зоны доставки (shop.mdc)."""

depends_on = "0011_customer_id"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        "ALTER TABLE shop_shops "
        "ADD COLUMN IF NOT EXISTS delivery_zone jsonb NOT NULL DEFAULT '{}'::jsonb"
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute("ALTER TABLE shop_shops DROP COLUMN IF EXISTS delivery_zone")
