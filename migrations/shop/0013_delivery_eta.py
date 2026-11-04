"""Shop: ETA доставки — ``prep_minutes``/``courier_mode`` витрины и снапшот в заказе."""

depends_on = "0012_delivery_zone"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        "ALTER TABLE shop_shops "
        "ADD COLUMN IF NOT EXISTS prep_minutes integer NOT NULL DEFAULT 15, "
        "ADD COLUMN IF NOT EXISTS courier_mode varchar(16) NOT NULL DEFAULT 'scooter'"
    )
    ctx.execute(
        "ALTER TABLE shop_orders "
        "ADD COLUMN IF NOT EXISTS delivery_eta_minutes integer"
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute(
        "ALTER TABLE shop_shops "
        "DROP COLUMN IF EXISTS prep_minutes, DROP COLUMN IF EXISTS courier_mode"
    )
    ctx.execute("ALTER TABLE shop_orders DROP COLUMN IF EXISTS delivery_eta_minutes")
