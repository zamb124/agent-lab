"""Shop: витринная лента — полки, баннеры, подписки на возврат, КБЖУ.

``shop_shelves`` — секции ленты («Новинки», «Хиты», подборки, апсейл
корзины); ``shop_banners`` — сторис-карточки верха ленты;
``shop_back_in_stock`` — подписки «сообщить о появлении»;
``shop_products.nutrition`` и ``shop_modifier_options`` (``photo_file_id``,
``nutrition_delta``) — полоса КБЖУ и иллюстрированные опции карточки.
"""

depends_on = "0015_demo_template"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        "CREATE TYPE shop_shelf_kind_enum AS ENUM "
        "('manual','category','new','hits','comeback','usual','upsell')"
    )
    ctx.execute(
        "CREATE TYPE shop_shelf_layout_enum AS ENUM ('rail','rows','grid','hero')"
    )
    ctx.execute(
        "CREATE TYPE shop_shelf_placement_enum AS ENUM ('feed','cart')"
    )
    ctx.execute(
        "CREATE TABLE IF NOT EXISTS shop_shelves ("
        "shop_shelf_id varchar(64) PRIMARY KEY, "
        "shop_id varchar(64) NOT NULL, "
        "kind shop_shelf_kind_enum NOT NULL DEFAULT 'manual', "
        "layout shop_shelf_layout_enum NOT NULL DEFAULT 'rail', "
        "placement shop_shelf_placement_enum NOT NULL DEFAULT 'feed', "
        "title varchar(120) NOT NULL DEFAULT '', "
        "subtitle varchar(200) NOT NULL DEFAULT '', "
        "product_ids jsonb NOT NULL DEFAULT '[]', "
        "category_id varchar(64), "
        "item_limit bigint NOT NULL DEFAULT 10, "
        "sort bigint NOT NULL DEFAULT 0, "
        "is_active boolean NOT NULL DEFAULT true, "
        "created_at timestamptz NOT NULL, "
        "updated_at timestamptz NOT NULL"
        ")"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_shelves_shop_id_placement_sort_idx "
        "ON shop_shelves (shop_id, placement, sort)"
    )
    ctx.execute(
        "CREATE TABLE IF NOT EXISTS shop_banners ("
        "shop_banner_id varchar(64) PRIMARY KEY, "
        "shop_id varchar(64) NOT NULL, "
        "title varchar(120) NOT NULL DEFAULT '', "
        "subtitle varchar(200) NOT NULL DEFAULT '', "
        "image_file_id varchar(64), "
        "link varchar(300) NOT NULL DEFAULT '', "
        "display_window jsonb NOT NULL DEFAULT '{}', "
        "sort bigint NOT NULL DEFAULT 0, "
        "is_active boolean NOT NULL DEFAULT true, "
        "created_at timestamptz NOT NULL, "
        "updated_at timestamptz NOT NULL"
        ")"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_banners_shop_id_sort_idx "
        "ON shop_banners (shop_id, sort)"
    )
    ctx.execute(
        "CREATE TABLE IF NOT EXISTS shop_back_in_stock ("
        "shop_back_in_stock_id varchar(64) PRIMARY KEY, "
        "product_id varchar(64) NOT NULL, "
        "customer_id varchar(64) NOT NULL, "
        "notified_at timestamptz, "
        "created_at timestamptz NOT NULL"
        ")"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_back_in_stock_product_id_idx "
        "ON shop_back_in_stock (product_id)"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS shop_back_in_stock_customer_id_idx "
        "ON shop_back_in_stock (customer_id)"
    )
    ctx.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS shop_back_in_stock_product_customer_uniq "
        "ON shop_back_in_stock (product_id, customer_id)"
    )
    ctx.execute(
        "ALTER TABLE shop_shops "
        "ADD COLUMN IF NOT EXISTS features jsonb NOT NULL DEFAULT '{}'"
    )
    ctx.execute(
        "ALTER TABLE shop_products "
        "ADD COLUMN IF NOT EXISTS nutrition jsonb NOT NULL DEFAULT '{}'"
    )
    ctx.execute(
        "ALTER TABLE shop_modifier_options "
        "ADD COLUMN IF NOT EXISTS photo_file_id varchar(64)"
    )
    ctx.execute(
        "ALTER TABLE shop_modifier_options "
        "ADD COLUMN IF NOT EXISTS nutrition_delta jsonb NOT NULL DEFAULT '{}'"
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute("ALTER TABLE shop_modifier_options DROP COLUMN IF EXISTS nutrition_delta")
    ctx.execute("ALTER TABLE shop_modifier_options DROP COLUMN IF EXISTS photo_file_id")
    ctx.execute("ALTER TABLE shop_products DROP COLUMN IF EXISTS nutrition")
    ctx.execute("ALTER TABLE shop_shops DROP COLUMN IF EXISTS features")
    ctx.execute("DROP TABLE IF EXISTS shop_back_in_stock")
    ctx.execute("DROP TABLE IF EXISTS shop_banners")
    ctx.execute("DROP TABLE IF EXISTS shop_shelves")
    ctx.execute("DROP TYPE IF EXISTS shop_shelf_placement_enum")
    ctx.execute("DROP TYPE IF EXISTS shop_shelf_layout_enum")
    ctx.execute("DROP TYPE IF EXISTS shop_shelf_kind_enum")
