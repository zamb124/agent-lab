"""Эталонная витрина «Пиццерия «Печь»» — доставка и самовывоз.

Показывает: дерево категорий (Пицца → Классические/Авторские), полигон
зоны доставки, все режимы модификаторов (single delta, multi с лимитом,
nested-группа «сыр в борт», remove-группа «убрать ингредиент»), комбо
и акции 2+1, бесплатная доставка и эксклюзивная фиксированная цена.
"""

from apps.shop.models.enums import (
    ModifierGroupKind,
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
    DemoOrderGeoSpec,
    DemoOrderItemSpec,
    DemoOrderSpec,
    DemoProductSpec,
    DemoPromoSpec,
    DemoShopSpec,
)

_PIZZA_KEYS = ("margherita", "pepperoni", "fourcheez", "hawaiian", "bbq", "mushroom", "meat", "truffle", "burrata")
_PIZZA_MODS = ("size", "dough", "crust", "topping", "remove")

PIZZA = DemoShopSpec(
    key="pizza",
    kind=ShopKind.RESTAURANT,
    name='Пиццерия «Печь»',
    description=(
        "Неаполитанская пицца из дровяной печи: тесто 48 часов холодной "
        "ферментации, фиор ди латте и томаты сан-марцано. Доставляем горячей."
    ),
    phone="+7 (495) 300-40-50",
    city="Москва",
    address="Столешников пер., 5",
    timezone="Europe/Moscow",
    theme={"accent_color": "#e2553f", "preset": "menu", "mode": "dark"},
    working_hours={
        "0": "10:00-23:00",
        "1": "10:00-23:00",
        "2": "10:00-23:00",
        "3": "10:00-23:00",
        "4": "10:00-23:00",
        "5": "10:00-23:00",
        "6": "10:00-23:00",
    },
    delivery_enabled=True,
    pickup_enabled=True,
    onsite_enabled=False,
    delivery_zone={
        "type": "Polygon",
        "coordinates": [
            [
                [37.590, 55.735],
                [37.655, 55.735],
                [37.670, 55.755],
                [37.660, 55.775],
                [37.630, 55.785],
                [37.600, 55.780],
                [37.585, 55.760],
                [37.590, 55.735],
            ]
        ],
    },
    delivery_fee_minor=14900,
    min_order_minor=60000,
    prep_minutes=25,
    courier_mode="scooter",
    cover_photo="cover.jpg",
    badges=(
        {"key": "hit", "label": "Хит", "icon": "local_fire_department"},
        {"key": "new", "label": "Новинка", "icon": "new_releases"},
        {"key": "spicy", "label": "Острое", "icon": "local_fire_department"},
        {"key": "chef", "label": "От шефа", "icon": "cooking"},
    ),
    categories=(
        DemoCategorySpec(
            key="pizza", name="Пицца",
            children=(
                DemoCategorySpec(key="classic", name="Классические"),
                DemoCategorySpec(key="author", name="Авторские"),
            ),
        ),
        DemoCategorySpec(key="combo", name="Комбо"),
        DemoCategorySpec(key="snacks", name="Закуски"),
        DemoCategorySpec(key="sauces", name="Соусы"),
        DemoCategorySpec(key="drinks", name="Напитки"),
        DemoCategorySpec(key="desserts", name="Десерты"),
    ),
    modifier_groups=(
        DemoModifierGroupSpec(
            key="size",
            name="Размер пиццы",
            selection_mode=ModifierSelectionMode.SINGLE,
            price_mode=ModifierPriceMode.DELTA,
            min_selected=1,
            max_selected=1,
            options=(
                DemoOptionSpec(key="s25", name="25 см", price_minor=0, is_default=True),
                DemoOptionSpec(key="m33", name="33 см", price_minor=20000),
                DemoOptionSpec(key="l40", name="40 см", price_minor=40000),
            ),
        ),
        DemoModifierGroupSpec(
            key="dough",
            name="Тесто",
            selection_mode=ModifierSelectionMode.SINGLE,
            price_mode=ModifierPriceMode.DELTA,
            min_selected=1,
            max_selected=1,
            options=(
                DemoOptionSpec(key="classic", name="Классическое", price_minor=0, is_default=True),
                DemoOptionSpec(key="thin", name="Тонкое", price_minor=0),
            ),
        ),
        DemoModifierGroupSpec(
            key="crust",
            name="Борт",
            selection_mode=ModifierSelectionMode.SINGLE,
            price_mode=ModifierPriceMode.DELTA,
            min_selected=1,
            max_selected=1,
            options=(
                DemoOptionSpec(key="plain", name="Классический", price_minor=0, is_default=True),
                DemoOptionSpec(
                    key="cheese", name="Сырный", price_minor=14900,
                    nested_group_key="cheese_in",
                ),
                DemoOptionSpec(key="meat", name="Мясной", price_minor=19900),
            ),
        ),
        DemoModifierGroupSpec(
            key="cheese_in",
            name="Сыр в борт",
            selection_mode=ModifierSelectionMode.SINGLE,
            price_mode=ModifierPriceMode.DELTA,
            min_selected=1,
            max_selected=1,
            options=(
                DemoOptionSpec(key="mozz", name="Моцарелла", price_minor=0, is_default=True),
                DemoOptionSpec(key="dorblu", name="Дорблю", price_minor=5000),
                DemoOptionSpec(key="cheddar", name="Чеддер", price_minor=3000),
            ),
        ),
        DemoModifierGroupSpec(
            key="topping",
            name="Дополнительные топпинги",
            selection_mode=ModifierSelectionMode.MULTI,
            price_mode=ModifierPriceMode.DELTA,
            min_selected=0,
            max_selected=6,
            options=(
                DemoOptionSpec(key="mozz", name="Моцарелла", price_minor=7900),
                DemoOptionSpec(key="pep", name="Пепперони", price_minor=9900),
                DemoOptionSpec(key="bacon", name="Бекон", price_minor=9900),
                DemoOptionSpec(key="mush", name="Шампиньоны", price_minor=6900),
                DemoOptionSpec(key="arugula", name="Руккола", price_minor=5900),
                DemoOptionSpec(key="parm", name="Пармезан", price_minor=8900),
            ),
        ),
        DemoModifierGroupSpec(
            key="remove",
            name="Убрать ингредиент",
            kind=ModifierGroupKind.REMOVE,
            selection_mode=ModifierSelectionMode.MULTI,
            price_mode=ModifierPriceMode.DELTA,
            min_selected=0,
            max_selected=4,
            options=(
                DemoOptionSpec(key="onion", name="Лук"),
                DemoOptionSpec(key="pepper", name="Болгарский перец"),
                DemoOptionSpec(key="olives", name="Маслины"),
                DemoOptionSpec(key="mush", name="Грибы"),
            ),
        ),
        DemoModifierGroupSpec(
            key="pizza_pick",
            name="Пицца в комбо",
            selection_mode=ModifierSelectionMode.SINGLE,
            price_mode=ModifierPriceMode.DELTA,
            min_selected=1,
            max_selected=1,
            options=(
                DemoOptionSpec(key="marg", name="Маргарита", price_minor=0, is_default=True),
                DemoOptionSpec(key="pep", name="Пепперони", price_minor=5000),
                DemoOptionSpec(key="four", name="Четыре сыра", price_minor=5000),
                DemoOptionSpec(key="bbq", name="BBQ-цыплёнок", price_minor=5000),
            ),
        ),
        DemoModifierGroupSpec(
            key="drink_pick",
            name="Напиток в комбо",
            selection_mode=ModifierSelectionMode.SINGLE,
            price_mode=ModifierPriceMode.DELTA,
            min_selected=1,
            max_selected=1,
            options=(
                DemoOptionSpec(key="cola", name="Кола 0,5", price_minor=0, is_default=True),
                DemoOptionSpec(key="mors", name="Морс клюквенный", price_minor=0),
                DemoOptionSpec(key="lemon", name="Лимонад", price_minor=2000),
            ),
        ),
        DemoModifierGroupSpec(
            key="sauce_pick",
            name="Соус к крылышкам",
            selection_mode=ModifierSelectionMode.SINGLE,
            price_mode=ModifierPriceMode.DELTA,
            min_selected=1,
            max_selected=1,
            options=(
                DemoOptionSpec(key="cheese", name="Сырный", price_minor=0, is_default=True),
                DemoOptionSpec(key="garlic", name="Чесночный", price_minor=0),
                DemoOptionSpec(key="hot", name="Острый", price_minor=3000),
            ),
        ),
    ),
    products=(
        DemoProductSpec(
            key="margherita", category_key="classic", name="Маргарита",
            price_minor=49000, portion="25 см / 380 г", photo="margherita.jpg",
            description="Томатный соус сан-марцано, фиор ди латте, базилик и оливковое масло.",
            modifier_group_keys=_PIZZA_MODS,
        ),
        DemoProductSpec(
            key="pepperoni", category_key="classic", name="Пепперони",
            price_minor=59000, portion="25 см / 400 г", photo="pepperoni.jpg",
            description="Двойная порция пикантной пепперони и моцарелла.",
            badges=("hit",),
            modifier_group_keys=_PIZZA_MODS,
        ),
        DemoProductSpec(
            key="fourcheez", category_key="classic", name="Четыре сыра",
            price_minor=64000, portion="25 см / 420 г", photo="fourcheez.jpg",
            description="Моцарелла, горгонзола, пармезан и чеддер с мёдом по желанию.",
            modifier_group_keys=_PIZZA_MODS,
        ),
        DemoProductSpec(
            key="hawaiian", category_key="classic", name="Гавайская",
            price_minor=56000, portion="25 см / 430 г", photo="hawaiian.jpg",
            description="Копчёная курица, ананас и моцарелла — сладко-солёная классика.",
            modifier_group_keys=_PIZZA_MODS,
        ),
        DemoProductSpec(
            key="bbq", category_key="classic", name="BBQ-цыплёнок",
            price_minor=62000, portion="25 см / 440 г", photo="bbq.jpg",
            description="Курица гриль, соус BBQ, красный лук и кинза.",
            modifier_group_keys=_PIZZA_MODS,
        ),
        DemoProductSpec(
            key="mushroom", category_key="classic", name="Грибная",
            price_minor=57000, portion="25 см / 390 г", photo="mushroom.jpg",
            description="Шампиньоны, вешенки, трюфельное масло и моцарелла.",
            modifier_group_keys=_PIZZA_MODS,
        ),
        DemoProductSpec(
            key="meat", category_key="classic", name="Мясная",
            price_minor=69000, portion="25 см / 460 г", photo="meat.jpg",
            description="Пепперони, бекон, ветчина и копчёная колбаска.",
            badges=("spicy",),
            modifier_group_keys=_PIZZA_MODS,
        ),
        DemoProductSpec(
            key="truffle", category_key="author", name="Трюфельная",
            price_minor=89000, portion="25 см / 410 г", photo="truffle.jpg",
            description="Крем-соус на пармезане, шампиньоны и масло белого трюфеля.",
            badges=("chef",),
            modifier_group_keys=_PIZZA_MODS,
        ),
        DemoProductSpec(
            key="burrata", category_key="author", name="Буррата и прошутто",
            price_minor=92000, portion="25 см / 450 г", photo="burrata.jpg",
            description="Целая буррата, прошутто крудо, руккола и томаты конфи.",
            badges=("chef", "new"),
            modifier_group_keys=_PIZZA_MODS,
        ),
        DemoProductSpec(
            key="combo2", category_key="combo", name="Комбо «Пицца + напиток»",
            price_minor=109000, portion="пицца 33 см + напиток", photo="combo.jpg",
            description="Любая классическая пицца 33 см и напиток на выбор — выгоднее на 150 ₽.",
            badges=("hit",),
            modifier_group_keys=("pizza_pick", "drink_pick"),
        ),
        DemoProductSpec(
            key="wings", category_key="snacks", name="Крылышки",
            price_minor=39000, portion="6 шт / 300 г", photo="wings.jpg",
            description="Запечённые в печи крылышки в маринаде паприки и мёда.",
            badges=("spicy",),
            modifier_group_keys=("sauce_pick",),
        ),
        DemoProductSpec(
            key="fries", category_key="snacks", name="Картофель фри",
            price_minor=19000, portion="150 г", photo="fries.jpg",
            description="С морской солью и розмарином.",
        ),
        DemoProductSpec(
            key="caesar", category_key="snacks", name="Салат «Цезарь»",
            price_minor=42000, portion="250 г", photo="caesar.jpg",
            description="Ромэн, курица гриль, пармезан, чесночные крутоны и соус цезарь.",
        ),
        DemoProductSpec(
            key="saucerr", category_key="sauces", name="Соус сырный",
            price_minor=7000, portion="50 г", photo="saucerr.jpg",
            description="Домашний соус на чеддере и сливках.",
        ),
        DemoProductSpec(
            key="garlic", category_key="sauces", name="Соус чесночный",
            price_minor=7000, portion="50 г", photo="garlic.jpg",
            description="Сметана, чеснок и укроп.",
        ),
        DemoProductSpec(
            key="bbqsauce", category_key="sauces", name="Соус BBQ",
            price_minor=7000, portion="50 г", photo="bbqsauce.jpg",
            description="Копчёный томатный соус.",
        ),
        DemoProductSpec(
            key="hotsauce", category_key="sauces", name="Соус острый",
            price_minor=7000, portion="50 г", photo="hotsauce.jpg",
            description="Перец чили и томат — для смелых.",
            badges=("spicy",),
        ),
        DemoProductSpec(
            key="cola", category_key="drinks", name="Кока-кола 0,5",
            price_minor=14900, portion="0,5 л", photo="cola.jpg",
            description="В стекле, холодная.",
        ),
        DemoProductSpec(
            key="mors", category_key="drinks", name="Морс клюквенный",
            price_minor=15900, portion="0,5 л", photo="mors.jpg",
            description="Варим сами из свежей клюквы.",
        ),
        DemoProductSpec(
            key="lemonade", category_key="drinks", name="Лимонад манго-маракуйя",
            price_minor=18900, portion="0,5 л", photo="lemonade.jpg",
            description="Домашний лимонад на тростниковом сахаре.",
        ),
        DemoProductSpec(
            key="tiramisu", category_key="desserts", name="Тирамису",
            price_minor=35000, portion="130 г", photo="tiramisu.jpg",
            description="Маскарпоне, савоярди и эспрессо — как в Неаполе.",
        ),
        DemoProductSpec(
            key="fondant", category_key="desserts", name="Фондан шоколадный",
            price_minor=38000, portion="100 г", photo="fondant.jpg",
            description="Тёплый шоколадный кекс с жидким центром, подаём с шариком мороженого.",
            badges=("new",),
        ),
    ),
    promos=(
        DemoPromoSpec(
            key="third",
            name="Три пиццы — третья в подарок",
            condition={"type": "min_qty", "n": 3, "product_ids": list(_PIZZA_KEYS)},
            action={
                "type": "n_plus_m_free",
                "n": 2,
                "m": 1,
                "product_ids": list(_PIZZA_KEYS),
            },
            priority=10,
        ),
        DemoPromoSpec(
            key="freedel",
            name="Бесплатная доставка от 1200 ₽",
            condition={"type": "min_total", "minor": 120000},
            action={"type": "free_delivery"},
            priority=1,
        ),
        DemoPromoSpec(
            key="combofix",
            name="Маргарита + 2 колы = 990 ₽",
            condition={
                "type": "items_present",
                "product_ids": ["margherita", "cola"],
            },
            action={
                "type": "fixed_bundle_price",
                "price_minor": 99000,
                "items": {"margherita": 1, "cola": 2},
            },
            stacking=PromoStacking.EXCLUSIVE,
            priority=5,
        ),
    ),
    tables=(),
    orders=(
        DemoOrderSpec(
            status=ShopOrderStatus.NEW,
            delivery_type=ShopDeliveryType.DELIVERY,
            items=(
                DemoOrderItemSpec(
                    product_key="pepperoni",
                    qty=2,
                    selections=(
                        ("size", "m33"),
                        ("crust", "cheese"),
                        ("cheese_in", "mozz"),
                    ),
                ),
                DemoOrderItemSpec(product_key="cola"),
            ),
            customer_name="Сергей Образцов",
            customer_phone="+7 900 000-00-31",
            address="Москва, Столешников пер., 9, кв. 15",
            age_hours=0.3,
            history_minutes=(),
            geo=DemoOrderGeoSpec(
                delivery_lat=55.7540,
                delivery_lng=37.6220,
                shop_lat=55.7590,
                shop_lng=37.6150,
                route={
                    "type": "LineString",
                    "coordinates": [
                        [37.6150, 55.7590],
                        [37.6170, 55.7575],
                        [37.6190, 55.7560],
                        [37.6205, 55.7550],
                        [37.6220, 55.7540],
                    ],
                },
            ),
        ),
        DemoOrderSpec(
            status=ShopOrderStatus.PREPARING,
            delivery_type=ShopDeliveryType.PICKUP,
            items=(
                DemoOrderItemSpec(
                    product_key="margherita",
                    selections=(("size", "s25"),),
                ),
                DemoOrderItemSpec(product_key="saucerr"),
                DemoOrderItemSpec(product_key="garlic"),
            ),
            customer_name="Ольга Примерова",
            customer_phone="+7 900 000-00-88",
            age_hours=0.2,
            history_minutes=(2, 8),
        ),
        DemoOrderSpec(
            status=ShopOrderStatus.DONE,
            delivery_type=ShopDeliveryType.DELIVERY,
            items=(
                DemoOrderItemSpec(
                    product_key="fourcheez",
                    selections=(
                        ("size", "l40"),
                        ("crust", "plain"),
                        ("topping", "bacon"),
                    ),
                ),
                DemoOrderItemSpec(product_key="mors"),
                DemoOrderItemSpec(product_key="tiramisu"),
            ),
            customer_name="Павел Образцов",
            customer_phone="+7 900 000-00-64",
            address="Москва, Петровский бул., 21, кв. 7",
            age_hours=26.0,
            history_minutes=(3, 12, 25, 47),
        ),
    ),
)
