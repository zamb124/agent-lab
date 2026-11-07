"""Shop: точка магазина и детали адреса доставки заказа."""

depends_on = "0017_shop_features"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        "ALTER TABLE shop_shops "
        "ADD COLUMN IF NOT EXISTS lat double precision, "
        "ADD COLUMN IF NOT EXISTS lng double precision"
    )
    ctx.execute(
        "ALTER TABLE shop_orders "
        "ADD COLUMN IF NOT EXISTS delivery_flat varchar(32) NOT NULL DEFAULT '', "
        "ADD COLUMN IF NOT EXISTS delivery_entrance varchar(32) NOT NULL DEFAULT '', "
        "ADD COLUMN IF NOT EXISTS delivery_floor varchar(32) NOT NULL DEFAULT '', "
        "ADD COLUMN IF NOT EXISTS delivery_intercom varchar(64) NOT NULL DEFAULT ''"
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute(
        "ALTER TABLE shop_shops "
        "DROP COLUMN IF EXISTS lat, DROP COLUMN IF EXISTS lng"
    )
    ctx.execute(
        "ALTER TABLE shop_orders "
        "DROP COLUMN IF EXISTS delivery_flat, "
        "DROP COLUMN IF EXISTS delivery_entrance, "
        "DROP COLUMN IF EXISTS delivery_floor, "
        "DROP COLUMN IF EXISTS delivery_intercom"
    )
