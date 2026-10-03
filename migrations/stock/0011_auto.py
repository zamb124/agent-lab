"""Слияние stock_product_templates в stock_products (аудит лаконичности).

Шаблон был строго 1:1 с продуктом (create_product создавал пару) —
отдельная сущность не несла бизнес-смысла. Все поля карточки
(tracking, valuation_method, стоимость, габариты, сроки годности,
removal_strategy) переезжают на сам продукт; таблица шаблонов и
связь ``template_id`` удаляются.

Перенос данных: новые колонки добавляются, UPDATE по
``p.template_id = t.product_template_id`` копирует карточку, затем
``SET NOT NULL`` на обязательные поля — сирот без шаблона быть не
может (иначе миграция честно упадёт на SET NOT NULL).

Created: 2026-09-26
"""

depends_on = "0010_create_stock_putaway_strategy_enum_enum"

_NEW_DECIMAL = {
    'kind': 'decimal',
    'precision': 24,
    'scale': 6,
}
_NEW_INT = {'kind': 'big_integer'}


def upgrade(ctx):
    """Apply migration."""
    # 1. Новые колонки карточки на stock_products.
    #    С дефолтом — сразу NOT NULL (Postgres бэкфиллит дефолтом);
    #    name/valuation_method — сперва nullable, NOT NULL после переноса.
    ctx.add_column("stock_products", {
        'name': 'tracking',
        'column_type': {
            'kind': 'enum',
            'name': 'stock_tracking_enum',
            'values': ['none', 'lot', 'serial'],
        },
        'db_type': None,
        'nullable': False,
        'primary_key': False,
        'unique': False,
        'default': "'none'",
        'auto_increment': False,
        'max_length': None,
        'max_digits': None,
        'decimal_places': None,
    })
    ctx.add_column("stock_products", {
        'name': 'is_storable',
        'column_type': {'kind': 'boolean'},
        'db_type': None,
        'nullable': False,
        'primary_key': False,
        'unique': False,
        'default': 'TRUE',
        'auto_increment': False,
        'max_length': None,
        'max_digits': None,
        'decimal_places': None,
    })
    ctx.add_column("stock_products", {
        'name': 'category',
        'column_type': {'kind': 'string', 'length': 128},
        'db_type': None,
        'nullable': False,
        'primary_key': False,
        'unique': False,
        'default': "''",
        'auto_increment': False,
        'max_length': 128,
        'max_digits': None,
        'decimal_places': None,
    })
    ctx.add_column("stock_products", {
        'name': 'standard_price',
        'column_type': _NEW_DECIMAL,
        'db_type': 'NUMERIC(24,6)',
        'nullable': False,
        'primary_key': False,
        'unique': False,
        'default': '0',
        'auto_increment': False,
        'max_length': None,
        'max_digits': None,
        'decimal_places': None,
    })
    ctx.add_column("stock_products", {
        'name': 'use_expiration',
        'column_type': {'kind': 'boolean'},
        'db_type': None,
        'nullable': False,
        'primary_key': False,
        'unique': False,
        'default': 'FALSE',
        'auto_increment': False,
        'max_length': None,
        'max_digits': None,
        'decimal_places': None,
    })
    ctx.add_column("stock_products", {
        'name': 'name',
        'column_type': {'kind': 'string', 'length': 255},
        'db_type': None,
        'nullable': True,
        'primary_key': False,
        'unique': False,
        'default': None,
        'auto_increment': False,
        'max_length': 255,
        'max_digits': None,
        'decimal_places': None,
    })
    ctx.add_column("stock_products", {
        'name': 'valuation_method',
        'column_type': {
            'kind': 'enum',
            'name': 'valuation_method_enum',
            'values': ['standard', 'average', 'fifo', 'unvalued'],
        },
        'db_type': None,
        'nullable': True,
        'primary_key': False,
        'unique': False,
        'default': None,
        'auto_increment': False,
        'max_length': None,
        'max_digits': None,
        'decimal_places': None,
    })
    for col in ('weight', 'volume'):
        ctx.add_column("stock_products", {
            'name': col,
            'column_type': _NEW_DECIMAL,
            'db_type': 'NUMERIC(24,6)',
            'nullable': True,
            'primary_key': False,
            'unique': False,
            'default': None,
            'auto_increment': False,
            'max_length': None,
            'max_digits': None,
            'decimal_places': None,
        })
    for col in (
        'expiration_days', 'best_before_days', 'removal_days', 'alert_days'
    ):
        ctx.add_column("stock_products", {
            'name': col,
            'column_type': _NEW_INT,
            'db_type': None,
            'nullable': True,
            'primary_key': False,
            'unique': False,
            'default': None,
            'auto_increment': False,
            'max_length': None,
            'max_digits': None,
            'decimal_places': None,
        })
    ctx.add_column("stock_products", {
        'name': 'removal_strategy',
        'column_type': {
            'kind': 'enum',
            'name': 'stock_removal_strategy_enum',
            'values': ['fifo', 'fefo', 'lifo', 'least_containers', 'closest'],
        },
        'db_type': None,
        'nullable': True,
        'primary_key': False,
        'unique': False,
        'default': None,
        'auto_increment': False,
        'max_length': None,
        'max_digits': None,
        'decimal_places': None,
    })
    # 2. Перенос карточки 1:1 из шаблона по template_id.
    ctx.execute(
        "UPDATE stock_products p SET "
        "name = t.name, tracking = t.tracking, is_storable = t.is_storable, "
        "category = t.category, valuation_method = t.valuation_method, "
        "standard_price = t.standard_price, weight = t.weight, "
        "volume = t.volume, use_expiration = t.use_expiration, "
        "expiration_days = t.expiration_days, "
        "best_before_days = t.best_before_days, "
        "removal_days = t.removal_days, alert_days = t.alert_days, "
        "removal_strategy = t.removal_strategy "
        "FROM stock_product_templates t "
        "WHERE p.template_id = t.product_template_id"
    )
    # 3. Обязательные поля — NOT NULL после переноса: сирота без
    #    шаблона — честный сбой, а не молчаливый дефолт.
    ctx.execute("ALTER TABLE stock_products ALTER COLUMN name SET NOT NULL")
    ctx.execute(
        "ALTER TABLE stock_products ALTER COLUMN valuation_method SET NOT NULL"
    )
    ctx.alter_column("stock_products", "name", nullable=False)
    ctx.alter_column("stock_products", "valuation_method", nullable=False)
    # 4. Связь и таблица-шаблон больше не нужны.
    ctx.drop_index("stock_products", "stock_products_company_id_template_id_idx")
    ctx.drop_column("stock_products", "template_id")
    ctx.drop_table("stock_product_templates")


def downgrade(ctx):
    """Revert migration."""
    ctx.create_table(
        "stock_product_templates",
        fields=[
            {
                'name': 'product_template_id',
                'column_type': {'kind': 'string', 'length': 64},
                'db_type': None,
                'nullable': False,
                'primary_key': True,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 64,
                'max_digits': None,
                'decimal_places': None,
            },
            {
                'name': 'company_id',
                'column_type': {'kind': 'string', 'length': 100},
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 100,
                'max_digits': None,
                'decimal_places': None,
            },
            {
                'name': 'name',
                'column_type': {'kind': 'string', 'length': 255},
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 255,
                'max_digits': None,
                'decimal_places': None,
            },
            {
                'name': 'tracking',
                'column_type': {
                    'kind': 'enum',
                    'name': 'stock_tracking_enum',
                    'values': ['none', 'lot', 'serial'],
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "'none'",
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None,
            },
            {
                'name': 'is_storable',
                'column_type': {'kind': 'boolean'},
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': 'TRUE',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None,
            },
            {
                'name': 'category',
                'column_type': {'kind': 'string', 'length': 128},
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': "''",
                'auto_increment': False,
                'max_length': 128,
                'max_digits': None,
                'decimal_places': None,
            },
            {
                'name': 'valuation_method',
                'column_type': {
                    'kind': 'enum',
                    'name': 'valuation_method_enum',
                    'values': ['standard', 'average', 'fifo', 'unvalued'],
                },
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None,
            },
            {
                'name': 'standard_price',
                'column_type': _NEW_DECIMAL,
                'db_type': 'NUMERIC(24,6)',
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': '0',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None,
            },
            {
                'name': 'uom_id',
                'column_type': {'kind': 'string', 'length': 64},
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': 64,
                'max_digits': None,
                'decimal_places': None,
            },
            {
                'name': 'created_at',
                'column_type': {'kind': 'date_time'},
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None,
            },
            {
                'name': 'updated_at',
                'column_type': {'kind': 'date_time'},
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None,
            },
            {
                'name': 'weight',
                'column_type': _NEW_DECIMAL,
                'db_type': 'NUMERIC(24,6)',
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None,
            },
            {
                'name': 'volume',
                'column_type': _NEW_DECIMAL,
                'db_type': 'NUMERIC(24,6)',
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None,
            },
            {
                'name': 'use_expiration',
                'column_type': {'kind': 'boolean'},
                'db_type': None,
                'nullable': False,
                'primary_key': False,
                'unique': False,
                'default': 'FALSE',
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None,
            },
            {
                'name': 'expiration_days',
                'column_type': _NEW_INT,
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None,
            },
            {
                'name': 'best_before_days',
                'column_type': _NEW_INT,
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None,
            },
            {
                'name': 'removal_days',
                'column_type': _NEW_INT,
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None,
            },
            {
                'name': 'alert_days',
                'column_type': _NEW_INT,
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None,
            },
            {
                'name': 'removal_strategy',
                'column_type': {
                    'kind': 'enum',
                    'name': 'stock_removal_strategy_enum',
                    'values': [
                        'fifo', 'fefo', 'lifo', 'least_containers', 'closest'
                    ],
                },
                'db_type': None,
                'nullable': True,
                'primary_key': False,
                'unique': False,
                'default': None,
                'auto_increment': False,
                'max_length': None,
                'max_digits': None,
                'decimal_places': None,
            },
        ],
    )
    ctx.execute(
        "INSERT INTO stock_product_templates (product_template_id, company_id, "
        "name, tracking, is_storable, category, valuation_method, "
        "standard_price, uom_id, created_at, updated_at, weight, volume, "
        "use_expiration, expiration_days, best_before_days, removal_days, "
        "alert_days, removal_strategy) "
        "SELECT 'spt_' || product_id, company_id, name, tracking, is_storable, "
        "category, valuation_method, standard_price, uom_id, created_at, "
        "updated_at, weight, volume, use_expiration, expiration_days, "
        "best_before_days, removal_days, alert_days, removal_strategy "
        "FROM stock_products"
    )
    ctx.add_column("stock_products", {
        'name': 'template_id',
        'column_type': {'kind': 'string', 'length': 64},
        'db_type': None,
        'nullable': True,
        'primary_key': False,
        'unique': False,
        'default': None,
        'auto_increment': False,
        'max_length': 64,
        'max_digits': None,
        'decimal_places': None,
    })
    ctx.execute(
        "UPDATE stock_products SET template_id = 'spt_' || product_id"
    )
    ctx.execute(
        "ALTER TABLE stock_products ALTER COLUMN template_id SET NOT NULL"
    )
    ctx.alter_column("stock_products", "template_id", nullable=False)
    ctx.create_index("stock_products", {
        'name': 'stock_products_company_id_template_id_idx',
        'fields': ['company_id', 'template_id'],
        'unique': False,
        'method': None,
    })
    for col in (
        'name', 'tracking', 'is_storable', 'category', 'valuation_method',
        'standard_price', 'weight', 'volume', 'use_expiration',
        'expiration_days', 'best_before_days', 'removal_days', 'alert_days',
        'removal_strategy',
    ):
        ctx.drop_column("stock_products", col)
