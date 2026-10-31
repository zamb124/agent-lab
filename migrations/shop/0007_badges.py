"""Shop: метки позиции («Хит», «Острое», «Веган»…) — ShopProduct.badges JSONB."""

depends_on = "0006_portion"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        "ALTER TABLE shop_products "
        "ADD COLUMN IF NOT EXISTS badges jsonb NOT NULL DEFAULT '[]'::jsonb"
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute("ALTER TABLE shop_products DROP COLUMN IF EXISTS badges")
