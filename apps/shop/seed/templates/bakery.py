"""Эталонная витрина «Пекарня «Хлеб да соль»» — ремесленная пекарня.

Показывает: самовывоз и доставку без зала, бесплатные опции (нарезка),
платную упаковку и надпись на торте, вечернюю распродажу выпечки
и бесплатную доставку от суммы заказа.
"""

from apps.shop.models.enums import (
    ModifierPriceMode,
    ModifierSelectionMode,
    ShopDeliveryType,
    ShopKind,
    ShopOrderStatus,
)
from apps.shop.seed.spec import (
    DemoCategorySpec,
    DemoModifierGroupSpec,
    DemoOptionSpec,
    DemoOrderItemSpec,
    DemoOrderSpec,
    DemoProductSpec,
    DemoPromoSpec,
    DemoShopSpec,
)

_PASTRY_KEYS = ("almond", "cinnamon", "eclair", "cookie", "potato")

BAKERY = DemoShopSpec(
    key="bakery",
    kind=ShopKind.BAKERY,
    name='Пекарня «Хлеб да соль»',
    description=(
        "Ремесленная пекарня: хлеб на закваске, слоёная выпечка из печи "
        "и торты на заказ. Всё готовим ночью — к открытию свежее."
    ),
    phone="+7 (495) 200-30-40",
    city="Москва",
    address="ул. Маросейка, 9",
    timezone="Europe/Moscow",
    theme={"accent_color": "#d98324", "preset": "grid", "mode": "light"},
    working_hours={
        "0": "07:00-20:00",
        "1": "07:00-20:00",
        "2": "07:00-20:00",
        "3": "07:00-20:00",
        "4": "07:00-20:00",
        "5": "07:00-20:00",
        "6": "08:00-20:00",
    },
    delivery_enabled=True,
    pickup_enabled=True,
    onsite_enabled=False,
    delivery_zone={},
    delivery_fee_minor=20000,
    min_order_minor=80000,
    prep_minutes=30,
    courier_mode="scooter",
    cover_photo="cover.jpg",
    badges=(
        {"key": "hit", "label": "Хит", "icon": "local_fire_department"},
        {"key": "new", "label": "Новинка", "icon": "new_releases"},
        {"key": "vegan", "label": "Веган", "icon": "eco"},
        {"key": "sign", "label": "Фирменное", "icon": "star"},
    ),
    categories=(
        DemoCategorySpec(key="bread", name="Хлеб"),
        DemoCategorySpec(key="pastry", name="Выпечка"),
        DemoCategorySpec(key="desserts", name="Десерты и торты"),
        DemoCategorySpec(key="drinks", name="Напитки"),
    ),
    modifier_groups=(
        DemoModifierGroupSpec(
            key="slice",
            name="Нарезка",
            selection_mode=ModifierSelectionMode.SINGLE,
            price_mode=ModifierPriceMode.DELTA,
            min_selected=1,
            max_selected=1,
            options=(
                DemoOptionSpec(key="whole", name="Целый батон", price_minor=0, is_default=True),
                DemoOptionSpec(key="sliced", name="Нарезать", price_minor=0),
            ),
        ),
        DemoModifierGroupSpec(
            key="pack",
            name="Упаковка",
            selection_mode=ModifierSelectionMode.SINGLE,
            price_mode=ModifierPriceMode.DELTA,
            min_selected=1,
            max_selected=1,
            options=(
                DemoOptionSpec(key="plain", name="Обычная", price_minor=0, is_default=True),
                DemoOptionSpec(key="gift", name="Подарочная коробка", price_minor=15000),
            ),
        ),
        DemoModifierGroupSpec(
            key="writing",
            name="Надпись на торте",
            selection_mode=ModifierSelectionMode.SINGLE,
            price_mode=ModifierPriceMode.DELTA,
            min_selected=1,
            max_selected=1,
            options=(
                DemoOptionSpec(key="no", name="Без надписи", price_minor=0, is_default=True),
                DemoOptionSpec(key="yes", name="Добавить надпись", price_minor=30000),
            ),
        ),
    ),
    products=(
        DemoProductSpec(
            key="borodino", category_key="bread", name="Бородинский",
            price_minor=28000, portion="600 г", photo="borodino.jpg",
            description="Ржаной на закваске, с кориандром и солодом. Нарежем под тосты или по просьбе.",
            badges=("hit",),
            modifier_group_keys=("slice", "pack"),
        ),
        DemoProductSpec(
            key="campagne", category_key="bread", name="Кампань",
            price_minor=34000, portion="700 г", photo="campagne.jpg",
            description="Пшенично-ржаной деревенский хлеб на трёхдневной закваске.",
            badges=("sign", "vegan"),
            modifier_group_keys=("slice", "pack"),
        ),
        DemoProductSpec(
            key="brioche", category_key="bread", name="Бриошь",
            price_minor=25000, portion="400 г", photo="brioche.jpg",
            description="Сдобный хлеб на сливочном масле — к джему и фуа-гра.",
            modifier_group_keys=("slice",),
        ),
        DemoProductSpec(
            key="baguette", category_key="bread", name="Багет",
            price_minor=16000, portion="250 г", photo="baguette.jpg",
            description="Хрустящий с тонким мякишем, печём к утру и к вечеру.",
            badges=("vegan",),
            modifier_group_keys=("slice",),
        ),
        DemoProductSpec(
            key="almond", category_key="pastry", name="Круассан миндальный",
            price_minor=29000, portion="110 г", photo="almond.jpg",
            description="Двойной выпечки: франжипан внутри и хлопья миндаля сверху.",
            badges=("hit",),
            modifier_group_keys=("pack",),
        ),
        DemoProductSpec(
            key="cinnamon", category_key="pastry", name="Синнабон",
            price_minor=26000, portion="120 г", photo="cinnamon.jpg",
            description="С корицей и сливочным крем-чизом — подаём тёплым.",
            badges=("hit",),
            modifier_group_keys=("pack",),
        ),
        DemoProductSpec(
            key="eclair", category_key="pastry", name="Эклер ванильный",
            price_minor=22000, portion="80 г", photo="eclair.jpg",
            description="Заварной крем с бурбонской ванилью и глазурь.",
            modifier_group_keys=("pack",),
        ),
        DemoProductSpec(
            key="cookie", category_key="pastry", name="Печенье овсяное",
            price_minor=12000, portion="70 г", photo="cookie.jpg",
            description="С изюмом и корицей — к чаю и какао.",
            badges=("vegan",),
        ),
        DemoProductSpec(
            key="potato", category_key="pastry", name="Пирожное «Картошка»",
            price_minor=15000, portion="80 г", photo="potato.jpg",
            description="По ГОСТу: бисквитная крошка, сливочный крем, какао.",
        ),
        DemoProductSpec(
            key="honeycake", category_key="desserts", name="Медовик",
            price_minor=29000, portion="140 г", photo="honeycake.jpg",
            description="Тонкие медовые коржи и сметанный крем — пропитан насквозь.",
            badges=("hit", "sign"),
        ),
        DemoProductSpec(
            key="napoleon", category_key="desserts", name="Торт «Наполеон»",
            price_minor=490000, portion="1,2 кг", photo="napoleon.jpg",
            description="Классика на заказ: 14 слоёв слоёного теста и заварной крем. Печём за сутки.",
            badges=("sign",),
            modifier_group_keys=("writing", "pack"),
        ),
        DemoProductSpec(
            key="lemontart", category_key="desserts", name="Тарт лимонный",
            price_minor=27000, portion="110 г", photo="lemontart.jpg",
            description="Лимонный курд на песочной основе и подпаленная меренга.",
            badges=("new",),
        ),
        DemoProductSpec(
            key="cacao", category_key="drinks", name="Какао",
            price_minor=21000, portion="300 мл", photo="cacao.jpg",
            description="Тёмный шоколад на молоке — без сиропов и смесей.",
        ),
        DemoProductSpec(
            key="lemonade", category_key="drinks", name="Лимонад домашний",
            price_minor=19000, portion="400 мл", photo="lemonade.jpg",
            description="Цитрусовый лимонад с розмарином, наливаем холодным.",
            badges=("vegan",),
        ),
    ),
    promos=(
        DemoPromoSpec(
            key="evening25",
            name="−25% на выпечку после 19:00",
            condition={"type": "always"},
            action={"type": "percent_items", "pct": 25, "product_ids": list(_PASTRY_KEYS)},
            window={"time_from": "19:00", "time_to": "20:00"},
            priority=10,
        ),
        DemoPromoSpec(
            key="freedel",
            name="Бесплатная доставка от 1500 ₽",
            condition={"type": "min_total", "minor": 150000},
            action={"type": "free_delivery"},
            priority=1,
        ),
    ),
    tables=(),
    orders=(
        DemoOrderSpec(
            status=ShopOrderStatus.DONE,
            delivery_type=ShopDeliveryType.PICKUP,
            items=(
                DemoOrderItemSpec(product_key="baguette", qty=2),
                DemoOrderItemSpec(
                    product_key="almond",
                    selections=(("pack", "gift"),),
                ),
                DemoOrderItemSpec(product_key="eclair"),
            ),
            customer_name="Мария Примерова",
            customer_phone="+7 900 000-00-55",
            age_hours=5.0,
            history_minutes=(3, 18, 42),
            comment="Заберу к 18:00",
        ),
        DemoOrderSpec(
            status=ShopOrderStatus.NEW,
            delivery_type=ShopDeliveryType.DELIVERY,
            items=(
                DemoOrderItemSpec(
                    product_key="napoleon",
                    selections=(("writing", "yes"), ("pack", "gift")),
                ),
            ),
            customer_name="Игорь Образцов",
            customer_phone="+7 900 000-00-73",
            address="Москва, ул. Маросейка, 12, кв. 3",
            age_hours=0.4,
            history_minutes=(),
            comment="Надпись: «С днём рождения, Катя!»",
        ),
    ),
)
