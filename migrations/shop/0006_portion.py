"""Shop: порция/выход блюда («400 г», «0.5 л», «12 шт») — ShopProduct.portion."""

depends_on = "0005_promos"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        "ALTER TABLE shop_products "
        "ADD COLUMN IF NOT EXISTS portion varchar(50) NOT NULL DEFAULT ''"
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute("ALTER TABLE shop_products DROP COLUMN IF EXISTS portion")
