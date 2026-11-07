"""Эталонная витрина «Кофейня «Свет»» — спешелти-кофейня.

Показывает: зал со столами и QR-заказом (8 столов), доставку и самовывоз,
модификаторы напитков (размер/молоко/сиропы/шот), счастливые часы на десерты
и механику «шестой кофе в подарок».
"""

from apps.shop.models.enums import (
    ModifierPriceMode,
    ModifierSelectionMode,
    PromoStacking,
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
    DemoTableSpec,
)

_COFFEE_KEYS = ("espresso", "americano", "cappuccino", "latte", "flatwhite", "raf", "filter")
_DRINK_MODS = ("size", "milk", "syrup", "shot")

CAFE = DemoShopSpec(
    key="cafe",
    kind=ShopKind.CAFE,
    name='Кофейня «Свет»',
    description=(
        "Спешелти-кофейня у метро. Зерно свежей обжарки, альтернативное молоко, "
        "завтраки весь день и десерты собственного производства."
    ),
    phone="+7 (495) 100-20-30",
    city="Москва",
    address="ул. Покровка, 17",
    timezone="Europe/Moscow",
    theme={"accent_color": "#c98f4e", "preset": "menu", "mode": "dark"},
    working_hours={
        "0": "08:00-21:00",
        "1": "08:00-21:00",
        "2": "08:00-21:00",
        "3": "08:00-21:00",
        "4": "08:00-21:00",
        "5": "09:00-22:00",
        "6": "09:00-22:00",
    },
    delivery_enabled=True,
    pickup_enabled=True,
    onsite_enabled=True,
    delivery_zone={},
    delivery_fee_minor=15000,
    min_order_minor=50000,
    prep_minutes=15,
    courier_mode="foot",
    cover_photo="cover.jpg",
    badges=(
        {"key": "hit", "label": "Хит", "icon": "local_fire_department"},
        {"key": "new", "label": "Новинка", "icon": "new_releases"},
        {"key": "vegan", "label": "Веган", "icon": "eco"},
        {"key": "barista", "label": "Выбор бариста", "icon": "workspace_premium"},
    ),
    categories=(
        DemoCategorySpec(key="coffee", name="Кофе"),
        DemoCategorySpec(key="notcoffee", name="Не кофе"),
        DemoCategorySpec(key="breakfast", name="Завтраки"),
        DemoCategorySpec(key="desserts", name="Десерты"),
        DemoCategorySpec(key="sandwich", name="Сэндвичи и боулы"),
    ),
    modifier_groups=(
        DemoModifierGroupSpec(
            key="size",
            name="Объём",
            selection_mode=ModifierSelectionMode.SINGLE,
            price_mode=ModifierPriceMode.DELTA,
            min_selected=1,
            max_selected=1,
            options=(
                DemoOptionSpec(key="s250", name="250 мл", price_minor=0, is_default=True),
                DemoOptionSpec(key="m350", name="350 мл", price_minor=4000),
                DemoOptionSpec(key="l450", name="450 мл", price_minor=8000),
            ),
        ),
        DemoModifierGroupSpec(
            key="milk",
            name="Молоко",
            selection_mode=ModifierSelectionMode.SINGLE,
            price_mode=ModifierPriceMode.DELTA,
            min_selected=1,
            max_selected=1,
            options=(
                DemoOptionSpec(key="cow", name="Обычное 3,2%", price_minor=0, is_default=True),
                DemoOptionSpec(key="oat", name="Овсяное", price_minor=7000),
                DemoOptionSpec(key="almond", name="Миндальное", price_minor=7000),
                DemoOptionSpec(key="nolact", name="Безлактозное", price_minor=5000),
            ),
        ),
        DemoModifierGroupSpec(
            key="syrup",
            name="Сиропы",
            selection_mode=ModifierSelectionMode.MULTI,
            price_mode=ModifierPriceMode.DELTA,
            min_selected=0,
            max_selected=3,
            options=(
                DemoOptionSpec(key="vanilla", name="Ваниль", price_minor=6000),
                DemoOptionSpec(key="caramel", name="Карамель", price_minor=6000),
                DemoOptionSpec(key="lavender", name="Лаванда", price_minor=6000),
                DemoOptionSpec(key="raspb", name="Малина", price_minor=6000),
            ),
        ),
        DemoModifierGroupSpec(
            key="shot",
            name="Добавить",
            selection_mode=ModifierSelectionMode.MULTI,
            price_mode=ModifierPriceMode.DELTA,
            min_selected=0,
            max_selected=2,
            options=(
                DemoOptionSpec(key="esp", name="Эспрессо-шот", price_minor=8000),
                DemoOptionSpec(key="cream", name="Сливки", price_minor=4000),
            ),
        ),
    ),
    products=(
        DemoProductSpec(
            key="espresso", category_key="coffee", name="Эспрессо",
            price_minor=19000, portion="40 мл", photo="espresso.jpg",
            description="Двойной шот на зерне Бразилия/Эфиопия. Плотный, с нотами какао и косточковых.",
            modifier_group_keys=("milk", "shot"),
        ),
        DemoProductSpec(
            key="americano", category_key="coffee", name="Американо",
            price_minor=22000, portion="250 мл", photo="americano.jpg",
            description="Мягкий и чистый: двойной эспрессо, разбавленный горячей водой.",
            modifier_group_keys=_DRINK_MODS,
        ),
        DemoProductSpec(
            key="cappuccino", category_key="coffee", name="Капучино",
            price_minor=32000, portion="250 мл", photo="cappuccino.jpg",
            description="Классика 1:1:1 — эспрессо, молоко и густая пена.",
            badges=("hit",),
            modifier_group_keys=_DRINK_MODS,
        ),
        DemoProductSpec(
            key="latte", category_key="coffee", name="Латте",
            price_minor=33000, portion="300 мл", photo="latte.jpg",
            description="Нежный молочный вкус, бариста рисует латте-арт на каждой чашке.",
            badges=("hit",),
            modifier_group_keys=_DRINK_MODS,
        ),
        DemoProductSpec(
            key="flatwhite", category_key="coffee", name="Флэт уайт",
            price_minor=34000, portion="200 мл", photo="flatwhite.jpg",
            description="Крепче капучино: двойной ристретто и тонкая микропена.",
            badges=("barista",),
            modifier_group_keys=_DRINK_MODS,
        ),
        DemoProductSpec(
            key="raf", category_key="coffee", name="Раф ванильный",
            price_minor=36000, portion="300 мл", photo="raf.jpg",
            description="Эспрессо со сливками и ванильным сахаром — наш фирменный.",
            badges=("hit", "barista"),
            modifier_group_keys=_DRINK_MODS,
        ),
        DemoProductSpec(
            key="filter", category_key="coffee", name="Фильтр-кофе",
            price_minor=25000, portion="300 мл", photo="filter.jpg",
            description="Завариваем в пуровере, спрашивайте актуальный лот у бариста.",
            modifier_group_keys=("size",),
        ),
        DemoProductSpec(
            key="matcha", category_key="notcoffee", name="Матча-латте",
            price_minor=35000, portion="300 мл", photo="matcha.jpg",
            description="Церемониальная матча на молоке — взбитая до бархатной пены.",
            badges=("new", "vegan"),
            modifier_group_keys=("size", "milk"),
        ),
        DemoProductSpec(
            key="oolong", category_key="notcoffee", name="Чай молочный улун",
            price_minor=26000, portion="400 мл", photo="oolong.jpg",
            description="Завариваем в чайнике: карамельные и сливочные ноты.",
        ),
        DemoProductSpec(
            key="cacao", category_key="notcoffee", name="Какао с зефиром",
            price_minor=29000, portion="300 мл", photo="cacao.jpg",
            description="Бельгийский шоколад 54%, взбиваем на пару до глянца.",
            modifier_group_keys=("size", "milk"),
        ),
        DemoProductSpec(
            key="bowl", category_key="breakfast", name="Боул с лососем",
            price_minor=52000, portion="320 г", photo="bowl.jpg",
            description="Киноа, лосось слабой соли, авокадо, огурец и кунжутная заправка.",
            badges=("vegan",),
        ),
        DemoProductSpec(
            key="croissant", category_key="breakfast", name="Круассан с пастрами",
            price_minor=39000, portion="210 г", photo="croissant.jpg",
            description="Слоёный круассан, говядина пастрами, руккола и соус горчица-мёд.",
            badges=("hit",),
        ),
        DemoProductSpec(
            key="syrniki", category_key="breakfast", name="Сырники",
            price_minor=38000, portion="3 шт / 240 г", photo="syrniki.jpg",
            description="Из фермерского творога, со сметаной и ягодным соусом.",
        ),
        DemoProductSpec(
            key="avocado", category_key="breakfast", name="Тост с авокадо",
            price_minor=42000, portion="260 г", photo="avocado.jpg",
            description="Зерновой хлеб, авокадо, яйцо пашот и хлопья чили.",
            badges=("vegan",),
        ),
        DemoProductSpec(
            key="cheesecake", category_key="desserts", name="Чизкейк Сан-Себастьян",
            price_minor=33000, portion="120 г", photo="cheesecake.jpg",
            description="Запечённый баскский чизкейк с карамельной корочкой и кремовым центром.",
        ),
        DemoProductSpec(
            key="cookie", category_key="desserts", name="Мисо-куки",
            price_minor=19000, portion="60 г", photo="cookie.jpg",
            description="Шоколадное печенье с белым мисо — солёно-карамельный акцент.",
            badges=("new",),
        ),
        DemoProductSpec(
            key="tiramisu", category_key="desserts", name="Тирамису",
            price_minor=34000, portion="130 г", photo="tiramisu.jpg",
            description="Классический: савоярди, маскарпоне, эспрессо и какао.",
        ),
        DemoProductSpec(
            key="sandwich", category_key="sandwich", name="Сэндвич с ростбифом",
            price_minor=49000, portion="280 г", photo="sandwich.jpg",
            description="Чиабатта, ростбиф, карамельный лук, руккола и хреновина.",
        ),
    ),
    promos=(
        DemoPromoSpec(
            key="coffee6",
            name="Шестой кофе в подарок",
            condition={"type": "min_qty", "n": 6, "product_ids": list(_COFFEE_KEYS)},
            action={
                "type": "n_plus_m_free",
                "n": 5,
                "m": 1,
                "product_ids": list(_COFFEE_KEYS),
            },
            priority=10,
        ),
        DemoPromoSpec(
            key="dessert20",
            name="Счастливые часы: −20% на десерты",
            condition={"type": "always"},
            action={
                "type": "percent_items",
                "pct": 20,
                "product_ids": ["cheesecake", "cookie", "tiramisu"],
            },
            window={"time_from": "15:00", "time_to": "18:00"},
            priority=5,
        ),
    ),
    tables=(
        DemoTableSpec(key="t1", label="Стол 1"),
        DemoTableSpec(key="t2", label="Стол 2"),
        DemoTableSpec(key="t3", label="Стол 3"),
        DemoTableSpec(key="t4", label="Стол 4"),
        DemoTableSpec(key="w1", label="У окна 1"),
        DemoTableSpec(key="w2", label="У окна 2"),
        DemoTableSpec(key="b1", label="Бар 1"),
        DemoTableSpec(key="b2", label="Бар 2"),
    ),
    orders=(
        DemoOrderSpec(
            status=ShopOrderStatus.NEW,
            delivery_type=ShopDeliveryType.ONSITE,
            items=(
                DemoOrderItemSpec(
                    product_key="latte",
                    selections=(("size", "s250"), ("milk", "oat"), ("syrup", "vanilla")),
                ),
                DemoOrderItemSpec(product_key="croissant"),
            ),
            customer_name="Анна Примерова",
            customer_phone="+7 900 000-00-42",
            table_key="t3",
            age_hours=0.7,
            history_minutes=(),
        ),
        DemoOrderSpec(
            status=ShopOrderStatus.DONE,
            delivery_type=ShopDeliveryType.DELIVERY,
            items=(
                DemoOrderItemSpec(
                    product_key="raf",
                    selections=(("size", "m350"),),
                ),
                DemoOrderItemSpec(product_key="tiramisu"),
            ),
            customer_name="Дмитрий Образцов",
            customer_phone="+7 900 000-00-17",
            address="Москва, ул. Покровка, 24, кв. 8",
            age_hours=22.0,
            history_minutes=(2, 9, 22, 41),
            comment="Позвонить за 10 минут",
        ),
    ),
)
