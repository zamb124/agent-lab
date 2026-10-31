"""Shop: per-shop Telegram-бот — токен и секрет webhook для привязки чата."""

depends_on = "0002_trgm_search"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        "ALTER TABLE shop_shops "
        "ADD COLUMN IF NOT EXISTS telegram_bot_token varchar(128) NULL, "
        "ADD COLUMN IF NOT EXISTS telegram_webhook_secret varchar(128) NULL"
    )


def downgrade(ctx):
    """Revert migration."""
    ctx.execute(
        "ALTER TABLE shop_shops "
        "DROP COLUMN IF EXISTS telegram_bot_token, "
        "DROP COLUMN IF EXISTS telegram_webhook_secret"
    )
