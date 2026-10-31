"""Shop: собственный набор меток позиций — Shop.badges JSONB [{key,label,icon}]."""

depends_on = "0007_badges"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        "ALTER TABLE shop_shops "
        "ADD COLUMN IF NOT EXISTS badges jsonb NOT NULL DEFAULT '[]'::jsonb"
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute("ALTER TABLE shop_shops DROP COLUMN IF EXISTS badges")
