"""Эталонная витрина «Магазин «У дома»» — продуктовый у дома.

Показывает: deep-каталог с подкатегориями, ночной график (08:00–02:00,
переход через полночь), фасовку с абсолютными ценами, скидку от суммы
заказа и «товары недели», статус заказа «в доставке».
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

_WEEK_KEYS = ("milk32", "bananas", "pelmeni", "buckwheat")

MARKET = DemoShopSpec(
    key="market",
    kind=ShopKind.SHOP,
    name='Магазин «У дома»',
    description=(
        "Продуктовый за углом: всё нужное каждый день — молочка, хлеб, "
        "овощи, бакалея и бытовая химия. Привозим за 30–45 минут."
    ),
    phone="+7 (495) 400-50-60",
    city="Москва",
    address="ул. Земляной Вал, 33",
    timezone="Europe/Moscow",
    theme={"accent_color": "#3f9c51", "preset": "compact", "mode": "light"},
    working_hours={
        "0": "08:00-02:00",
        "1": "08:00-02:00",
        "2": "08:00-02:00",
        "3": "08:00-02:00",
        "4": "08:00-02:00",
        "5": "08:00-02:00",
        "6": "08:00-02:00",
    },
    delivery_enabled=True,
    pickup_enabled=True,
    onsite_enabled=False,
    delivery_zone={},
    delivery_fee_minor=9900,
    min_order_minor=70000,
    prep_minutes=20,
    courier_mode="bike",
    cover_photo="cover.jpg",
    badges=(
        {"key": "hit", "label": "Хит продаж", "icon": "local_fire_department"},
        {"key": "new", "label": "Новинка", "icon": "new_releases"},
        {"key": "farm", "label": "Фермерское", "icon": "eco"},
    ),
    categories=(
        DemoCategorySpec(
            key="dairy", name="Молочное",
            children=(
                DemoCategorySpec(key="milk", name="Молоко и кефир"),
                DemoCategorySpec(key="cheese", name="Сыры и творог"),
            ),
        ),
        DemoCategorySpec(key="bread", name="Хлеб и выпечка"),
        DemoCategorySpec(key="produce", name="Овощи и фрукты"),
        DemoCategorySpec(key="meat", name="Мясо и колбасы"),
        DemoCategorySpec(key="grocery", name="Бакалея"),
        DemoCategorySpec(key="drinks", name="Напитки и вода"),
        DemoCategorySpec(key="frozen", name="Заморозка"),
        DemoCategorySpec(key="household", name="Бытовая химия"),
    ),
    modifier_groups=(
        DemoModifierGroupSpec(
            key="packsize",
            name="Фасовка",
            selection_mode=ModifierSelectionMode.SINGLE,
            price_mode=ModifierPriceMode.ABSOLUTE,
            min_selected=1,
            max_selected=1,
            options=(
                DemoOptionSpec(key="p200", name="200 г", price_minor=34000, is_default=True),
                DemoOptionSpec(key="p500", name="500 г", price_minor=79000),
            ),
        ),
    ),
    products=(
        DemoProductSpec(
            key="milk32", category_key="milk", name="Молоко 3,2%",
            price_minor=8900, portion="1 л", photo="milk32.jpg",
            description="Пастеризованное, от проверенной фермы. Срок — всегда свежий.",
            badges=("hit", "farm"),
        ),
        DemoProductSpec(
            key="kefir", category_key="milk", name="Кефир 3,2%",
            price_minor=7900, portion="1 л", photo="kefir.jpg",
            description="Классический кефир на живых заквасках.",
            badges=("farm",),
        ),
        DemoProductSpec(
            key="smetana", category_key="milk", name="Сметана 20%",
            price_minor=14900, portion="350 г", photo="smetana.jpg",
            description="Густая, без растительных добавок.",
        ),
        DemoProductSpec(
            key="tvorog", category_key="cheese", name="Творог 9%",
            price_minor=18900, portion="300 г", photo="tvorog.jpg",
            description="Рассыпчатый фермерский творог.",
            badges=("farm",),
        ),
        DemoProductSpec(
            key="cheese", category_key="cheese", name="Сыр российский",
            price_minor=34000, portion="200 г", photo="cheese.jpg",
            description="Полутвёрдый, выдержка 2 месяца. Выбирайте фасовку.",
            modifier_group_keys=("packsize",),
        ),
        DemoProductSpec(
            key="parmesan", category_key="cheese", name="Пармезан",
            price_minor=52000, portion="150 г", photo="parmesan.jpg",
            description="Выдержанный 12 месяцев — к пасте и салатам.",
            badges=("new",),
        ),
        DemoProductSpec(
            key="darnitsky", category_key="bread", name="Хлеб «Дарницкий»",
            price_minor=7900, portion="700 г", photo="darnitsky.jpg",
            description="Ржано-пшеничный, поставка каждое утро.",
            badges=("hit",),
        ),
        DemoProductSpec(
            key="buns", category_key="bread", name="Булочки сдобные",
            price_minor=12900, portion="4 шт / 280 г", photo="buns.jpg",
            description="Сдобные к чаю, пекутся районной пекарней.",
        ),
        DemoProductSpec(
            key="bananas", category_key="produce", name="Бананы",
            price_minor=13900, portion="1 кг", photo="bananas.jpg",
            description="Зрелые, без тёмных пятен — взвешиваем при сборке.",
            badges=("hit",),
        ),
        DemoProductSpec(
            key="apples", category_key="produce", name="Яблоки «Гала»",
            price_minor=16900, portion="1 кг", photo="apples.jpg",
            description="Сладкие и хрустящие, калибр 70+.",
        ),
        DemoProductSpec(
            key="tomatoes", category_key="produce", name="Томаты",
            price_minor=21900, portion="1 кг", photo="tomatoes.jpg",
            description="Тепличные, упругие — для салатов.",
        ),
        DemoProductSpec(
            key="potatoes", category_key="produce", name="Картофель молодой",
            price_minor=9900, portion="1 кг", photo="potatoes.jpg",
            description="Мытый, размер «крупный» — идеален для жарки.",
        ),
        DemoProductSpec(
            key="doktor", category_key="meat", name="Колбаса «Докторская»",
            price_minor=38900, portion="500 г", photo="doktor.jpg",
            description="ГОСТ, категория А — без сои и крахмала.",
            badges=("hit",),
        ),
        DemoProductSpec(
            key="chicken", category_key="meat", name="Филе куриное охл.",
            price_minor=42000, portion="500 г", photo="chicken.jpg",
            description="Охлаждённое, не замороженное — привозят ежедневно.",
            badges=("farm",),
        ),
        DemoProductSpec(
            key="sausages", category_key="meat", name="Сосиски молочные",
            price_minor=25900, portion="400 г", photo="sausages.jpg",
            description="В натуральной оболочке — детям на завтрак.",
        ),
        DemoProductSpec(
            key="buckwheat", category_key="grocery", name="Гречка ядрица",
            price_minor=9900, portion="900 г", photo="buckwheat.jpg",
            description="Ядрица высший сорт, быстроразваривающаяся.",
        ),
        DemoProductSpec(
            key="rice", category_key="grocery", name="Рис круглозерный",
            price_minor=10900, portion="800 г", photo="rice.jpg",
            description="Для каш и плова.",
        ),
        DemoProductSpec(
            key="pasta", category_key="grocery", name="Макароны «Перья»",
            price_minor=7900, portion="450 г", photo="pasta.jpg",
            description="Из твёрдых сортов пшеницы.",
        ),
        DemoProductSpec(
            key="sugar", category_key="grocery", name="Сахар-песок",
            price_minor=8900, portion="1 кг", photo="sugar.jpg",
            description="Категория ТС2, белый.",
        ),
        DemoProductSpec(
            key="tea", category_key="grocery", name="Чай чёрный листовой",
            price_minor=21900, portion="200 г", photo="tea.jpg",
            description="Крупнолистовой, Индия.",
        ),
        DemoProductSpec(
            key="coffee", category_key="grocery", name="Кофе молотый",
            price_minor=44900, portion="250 г", photo="coffee.jpg",
            description="Средняя обжарка, для чашки и френч-пресса.",
            badges=("new",),
        ),
        DemoProductSpec(
            key="water5", category_key="drinks", name="Вода питьевая 5 л",
            price_minor=15900, portion="5 л", photo="water5.jpg",
            description="Артезианская, негазированная.",
        ),
        DemoProductSpec(
            key="juice", category_key="drinks", name="Сок апельсиновый",
            price_minor=18900, portion="1 л", photo="juice.jpg",
            description="Прямой отжим, без сахара.",
        ),
        DemoProductSpec(
            key="cola2", category_key="drinks", name="Кола 2 л",
            price_minor=16900, portion="2 л", photo="cola2.jpg",
            description="Всегда холодная из витрины.",
        ),
        DemoProductSpec(
            key="pelmeni", category_key="frozen", name="Пельмени «Сибирские»",
            price_minor=32900, portion="800 г", photo="pelmeni.jpg",
            description="Говядина+свинина, тонкое тесто — не развариваются.",
            badges=("hit",),
        ),
        DemoProductSpec(
            key="vegmix", category_key="frozen", name="Смесь овощная",
            price_minor=14900, portion="400 г", photo="vegmix.jpg",
            description="«Мексиканская»: кукуруза, фасоль, перец, горошек.",
        ),
        DemoProductSpec(
            key="powder", category_key="household", name="Порошок стиральный",
            price_minor=54900, portion="1,5 кг", photo="powder.jpg",
            description="Универсальный, для белого и цветного.",
        ),
        DemoProductSpec(
            key="gel", category_key="household", name="Гель для посуды",
            price_minor=16900, portion="500 мл", photo="gel.jpg",
            description="Концентрированный, с ароматом лимона.",
        ),
    ),
    promos=(
        DemoPromoSpec(
            key="total5",
            name="Скидка 5% от 2000 ₽",
            condition={"type": "min_total", "minor": 200000},
            action={"type": "percent_order", "pct": 5},
            priority=1,
        ),
        DemoPromoSpec(
            key="week15",
            name="Товары недели −15%",
            condition={"type": "always"},
            action={"type": "percent_items", "pct": 15, "product_ids": list(_WEEK_KEYS)},
            priority=5,
        ),
    ),
    tables=(),
    orders=(
        DemoOrderSpec(
            status=ShopOrderStatus.NEW,
            delivery_type=ShopDeliveryType.DELIVERY,
            items=(
                DemoOrderItemSpec(product_key="milk32"),
                DemoOrderItemSpec(product_key="darnitsky"),
                DemoOrderItemSpec(product_key="pelmeni"),
                DemoOrderItemSpec(product_key="juice"),
            ),
            customer_name="Елена Примерова",
            customer_phone="+7 900 000-00-12",
            address="Москва, ул. Земляной Вал, 41, кв. 12",
            age_hours=0.2,
            history_minutes=(),
        ),
        DemoOrderSpec(
            status=ShopOrderStatus.DELIVERING,
            delivery_type=ShopDeliveryType.DELIVERY,
            items=(
                DemoOrderItemSpec(product_key="bananas", qty=2),
                DemoOrderItemSpec(product_key="tvorog"),
                DemoOrderItemSpec(
                    product_key="cheese",
                    selections=(("packsize", "p500"),),
                ),
                DemoOrderItemSpec(product_key="chicken"),
                DemoOrderItemSpec(product_key="water5"),
            ),
            customer_name="Виктор Образцов",
            customer_phone="+7 900 000-00-97",
            address="Москва, Сыромятническая наб., 10, кв. 4",
            age_hours=0.8,
            history_minutes=(2, 7, 19),
            comment="Домофон 12В, 3 этаж",
        ),
    ),
)
