"""Упаковки товара в ``stock_uom`` — AUoM-строки вместо своей таблицы.

``stock_product_packagings`` («короб 24 шт» → ``quantity``) была
дублирующей сущностью: то же самое в SAP EWM хранится как
альтернативная ЕИ товара (AUoM). Теперь упаковка — это ``stock_uom``
со scoped ``product_id`` и ``factor = количество × factor базовой ЕИ``:
``UnitOfMeasure.convert`` переводит «3 коробки» в базовые единицы без
особого кода, скан GTIN-14 в ``stock_barcodes`` указывает прямо на
строку uom. Плюс поля ``container_type_id``/``weight``/``volume``.

Уникальность: ``(company_id, name)`` — только для глобальных ЕИ
(``product_id IS NULL``); ``(company_id, product_id, name)`` — для
упаковок. Id упаковок сохранены (``uom_id = packaging_id``) — записи
``stock_barcodes`` с ``entity_type='packaging'`` не требуют переписки.
"""

depends_on = "0013_barcode_index_only"


def upgrade(ctx):
    """Колонки uom → частичные уники → backfill упаковок → drop."""
    ctx.add_column("stock_uom", {
        'name': 'product_id',
        'column_type': {'kind': 'string', 'length': 64},
        'db_type': None, 'nullable': True, 'primary_key': False,
        'unique': False, 'default': None, 'auto_increment': False,
        'max_length': 64, 'max_digits': None, 'decimal_places': None,
    })
    ctx.add_column("stock_uom", {
        'name': 'container_type_id',
        'column_type': {'kind': 'string', 'length': 64},
        'db_type': None, 'nullable': True, 'primary_key': False,
        'unique': False, 'default': None, 'auto_increment': False,
        'max_length': 64, 'max_digits': None, 'decimal_places': None,
    })
    ctx.add_column("stock_uom", {
        'name': 'weight',
        'column_type': {'kind': 'decimal', 'precision': 20, 'scale': 6},
        'db_type': 'NUMERIC(20,6)', 'nullable': True, 'primary_key': False,
        'unique': False, 'default': None, 'auto_increment': False,
        'max_length': None, 'max_digits': None, 'decimal_places': None,
    })
    ctx.add_column("stock_uom", {
        'name': 'volume',
        'column_type': {'kind': 'decimal', 'precision': 20, 'scale': 6},
        'db_type': 'NUMERIC(20,6)', 'nullable': True, 'primary_key': False,
        'unique': False, 'default': None, 'auto_increment': False,
        'max_length': None, 'max_digits': None, 'decimal_places': None,
    })
    ctx.alter_column("stock_uom", "name",
                     column_type={'kind': 'string', 'length': 128},
                     max_length=128)
    ctx.drop_index("stock_uom", "stock_uom_company_id_name_idx")
    # factor упаковки = «базовых единиц в упаковке» × factor базовой ЕИ
    ctx.execute(
        "INSERT INTO stock_uom"
        " (uom_id, company_id, name, category, factor, is_reference,"
        "  product_id, container_type_id, weight, volume)"
        " SELECT p.packaging_id, p.company_id, p.name, bu.category,"
        " p.quantity * bu.factor, false, p.product_id,"
        " p.container_type_id, p.weight, p.volume"
        " FROM stock_product_packagings p"
        " JOIN stock_products pr ON pr.company_id = p.company_id"
        "  AND pr.product_id = p.product_id"
        " JOIN stock_uom bu ON bu.company_id = p.company_id"
        "  AND bu.uom_id = pr.uom_id"
        " ON CONFLICT (uom_id) DO NOTHING"
    )
    ctx.drop_table("stock_product_packagings")
    ctx.create_index("stock_uom", {
        'name': 'stock_uom_company_id_name_idx',
        'fields': ['company_id', 'name'],
        'unique': True, 'method': None, 'where': 'product_id IS NULL',
    })
    ctx.create_index("stock_uom", {
        'name': 'stock_uom_company_id_product_id_name_idx',
        'fields': ['company_id', 'product_id', 'name'],
        'unique': True, 'method': None, 'where': 'product_id IS NOT NULL',
    })


def downgrade(ctx):
    """Вернуть таблицу упаковок и залить её из uom-строк."""
    ctx.create_table(
        "stock_product_packagings",
        fields=[
                       {
                           'name': 'packaging_id',
                           'column_type': {
                               'kind': 'string',
                               'length': 64
                           },
                           'db_type': None,
                           'nullable': False,
                           'primary_key': True,
                           'unique': False,
                           'default': None,
                           'auto_increment': False,
                           'max_length': 64,
                           'max_digits': None,
                           'decimal_places': None
                       },
                       {
                           'name': 'company_id',
                           'column_type': {
                               'kind': 'string',
                               'length': 100
                           },
                           'db_type': None,
                           'nullable': False,
                           'primary_key': False,
                           'unique': False,
                           'default': None,
                           'auto_increment': False,
                           'max_length': 100,
                           'max_digits': None,
                           'decimal_places': None
                       },
                       {
                           'name': 'product_id',
                           'column_type': {
                               'kind': 'string',
                               'length': 64
                           },
                           'db_type': None,
                           'nullable': False,
                           'primary_key': False,
                           'unique': False,
                           'default': None,
                           'auto_increment': False,
                           'max_length': 64,
                           'max_digits': None,
                           'decimal_places': None
                       },
                       {
                           'name': 'name',
                           'column_type': {
                               'kind': 'string',
                               'length': 128
                           },
                           'db_type': None,
                           'nullable': False,
                           'primary_key': False,
                           'unique': False,
                           'default': None,
                           'auto_increment': False,
                           'max_length': 128,
                           'max_digits': None,
                           'decimal_places': None
                       },
                       {
                           'name': 'quantity',
                           'column_type': {
                               'kind': 'decimal',
                               'precision': 20,
                               'scale': 6
                           },
                           'db_type': 'NUMERIC(20,6)',
                           'nullable': False,
                           'primary_key': False,
                           'unique': False,
                           'default': None,
                           'auto_increment': False,
                           'max_length': None,
                           'max_digits': None,
                           'decimal_places': None
                       },
                       {
                           'name': 'container_type_id',
                           'column_type': {
                               'kind': 'string',
                               'length': 64
                           },
                           'db_type': None,
                           'nullable': True,
                           'primary_key': False,
                           'unique': False,
                           'default': None,
                           'auto_increment': False,
                           'max_length': 64,
                           'max_digits': None,
                           'decimal_places': None
                       },
                       {
                           'name': 'weight',
                           'column_type': {
                               'kind': 'decimal',
                               'precision': 20,
                               'scale': 6
                           },
                           'db_type': 'NUMERIC(20,6)',
                           'nullable': True,
                           'primary_key': False,
                           'unique': False,
                           'default': None,
                           'auto_increment': False,
                           'max_length': None,
                           'max_digits': None,
                           'decimal_places': None
                       },
                       {
                           'name': 'volume',
                           'column_type': {
                               'kind': 'decimal',
                               'precision': 20,
                               'scale': 6
                           },
                           'db_type': 'NUMERIC(20,6)',
                           'nullable': True,
                           'primary_key': False,
                           'unique': False,
                           'default': None,
                           'auto_increment': False,
                           'max_length': None,
                           'max_digits': None,
                           'decimal_places': None
                       },
                       {
                           'name': 'created_at',
                           'column_type': {
                               'kind': 'date_time'
                           },
                           'db_type': None,
                           'nullable': False,
                           'primary_key': False,
                           'unique': False,
                           'default': None,
                           'auto_increment': False,
                           'max_length': None,
                           'max_digits': None,
                           'decimal_places': None
                       },
                       {
                           'name': 'updated_at',
                           'column_type': {
                               'kind': 'date_time'
                           },
                           'db_type': None,
                           'nullable': False,
                           'primary_key': False,
                           'unique': False,
                           'default': None,
                           'auto_increment': False,
                           'max_length': None,
                           'max_digits': None,
                           'decimal_places': None
                       }
                   ],
        indexes=[
                         {
                             'name': 'stock_product_packagings_company_id_product_id_name_idx',
                             'fields': [
                                 'company_id',
                                 'product_id',
                                 'name'
                             ],
                             'unique': True,
                             'method': None
                         }
                     ],
    )
    ctx.execute(
        "INSERT INTO stock_product_packagings"
        " (packaging_id, company_id, product_id, name, quantity,"
        "  container_type_id, weight, volume, created_at, updated_at)"
        " SELECT u.uom_id, u.company_id, u.product_id, u.name,"
        " u.factor / bu.factor, u.container_type_id, u.weight, u.volume,"
        " now(), now()"
        " FROM stock_uom u"
        " JOIN stock_products pr ON pr.company_id = u.company_id"
        "  AND pr.product_id = u.product_id"
        " JOIN stock_uom bu ON bu.company_id = u.company_id"
        "  AND bu.uom_id = pr.uom_id"
        " WHERE u.product_id IS NOT NULL"
    )
    ctx.execute(
        "DELETE FROM stock_uom WHERE product_id IS NOT NULL"
    )
    ctx.drop_index("stock_uom", "stock_uom_company_id_product_id_name_idx")
    ctx.drop_index("stock_uom", "stock_uom_company_id_name_idx")
    ctx.drop_column("stock_uom", "volume")
    ctx.drop_column("stock_uom", "weight")
    ctx.drop_column("stock_uom", "container_type_id")
    ctx.drop_column("stock_uom", "product_id")
    ctx.create_index("stock_uom", {
        'name': 'stock_uom_company_id_name_idx',
        'fields': ['company_id', 'name'],
        'unique': True, 'method': None,
    })
