"""Shop: лояльность — ``shop_loyalty_programs`` + ``shop_loyalty_accounts``.

Программа «N-я покупка — награда»: ``orders_goal`` done-заказов открывают
награду (скидка фиксом или процентом). Аккаунт покупателя —
``(shop_id, customer_id)`` уникален; атомарные инкременты одним UPDATE.
Заказ хранит снапшот применённой скидки в ``loyalty_reward_minor``.
"""

depends_on = "0020_order_feedback"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        "CREATE TABLE IF NOT EXISTS shop_loyalty_programs ("
        "shop_loyalty_program_id varchar(64) PRIMARY KEY, "
        "shop_id varchar(64) NOT NULL, "
        "orders_goal integer NOT NULL, "
        "reward_kind varchar(32) NOT NULL, "
        "reward_value integer NOT NULL, "
        "created_at timestamptz NOT NULL, "
        "updated_at timestamptz NOT NULL"
        ")"
    )
    ctx.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS shop_loyalty_programs_shop_uniq "
        "ON shop_loyalty_programs (shop_id)"
    )
    ctx.execute(
        "CREATE TABLE IF NOT EXISTS shop_loyalty_accounts ("
        "shop_loyalty_account_id varchar(64) PRIMARY KEY, "
        "shop_id varchar(64) NOT NULL, "
        "customer_id varchar(64) NOT NULL, "
        "progress integer NOT NULL DEFAULT 0, "
        "rewards_available integer NOT NULL DEFAULT 0, "
        "created_at timestamptz NOT NULL, "
        "updated_at timestamptz NOT NULL"
        ")"
    )
    ctx.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS shop_loyalty_accounts_uniq "
        "ON shop_loyalty_accounts (shop_id, customer_id)"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_loyalty_accounts_customer_idx "
        "ON shop_loyalty_accounts (customer_id)"
    )
    ctx.execute(
        "ALTER TABLE shop_orders ADD COLUMN IF NOT EXISTS "
        "loyalty_reward_minor integer NOT NULL DEFAULT 0"
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute("DROP TABLE IF EXISTS shop_loyalty_accounts")
    ctx.execute("DROP TABLE IF EXISTS shop_loyalty_programs")
    ctx.execute("ALTER TABLE shop_orders DROP COLUMN IF EXISTS loyalty_reward_minor")
