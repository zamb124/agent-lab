"""Shop: ``shop_shops.features`` — фича-флаги витрины.

Принцип «включил — получил функционал»: ``features`` JSONB держит
опциональные возможности директора магазина (``nutrition`` — полоса
КБЖУ в карточке, ``back_in_stock`` — подписки на возврат).
Дельта к 0016: миграция была применена до добавления колонки.
"""

depends_on = "0016_storefront_feed"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        "ALTER TABLE shop_shops "
        "ADD COLUMN IF NOT EXISTS features jsonb NOT NULL DEFAULT '{}'"
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute("ALTER TABLE shop_shops DROP COLUMN IF EXISTS features")
