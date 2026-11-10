# Shop — матрица покрытия документационными инструкциями

Статусы: ✅ опубликовано · 🚧 в работе · 📝 запланировано · ⛔ не документируем.

Две аудитории: **владелец магазина** (админка `shop-app`, `/shop/`, port 9027, fixture `shop_ui`)
и **покупатель** (публичная витрина `/shop/api/v1/public/s/<slug>` на 9027, `ui_page_anonymous`).
Демо-витрины с ~70 фото: `tests/ui/shots/seed_content.py::seed_demo_shops`
(фикстура `shots_shop_di` + `shop_worker`; переиспользовать паттерн seed для красивых кадров).

## UI-поверхности (админка)

| Страница | Что видит пользователь |
|---|---|
| `shop-home-page` | Главная магазина / список магазинов |
| `shop-builder-page` | Конструктор витрины |
| `shop-menu-page` | Меню: позиции, категории, модификаторы |
| `shop-orders-page` | Доска входящих заказов |
| `shop-promos-page` | Акции и лояльность |
| `shop-settings-page` | Настройки: slug/домен, доставка, зоны на карте |

## Блоки и инструкции

### getting-started — С чего начать

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 1 | `shop-first-store` | Создать магазин → добавить позиции → опубликовать витрину | `test_shop_doc_getting_started.py` | ✅ |
| 1 | `storefront-tour` | Витрина глазами покупателя (anon) | `test_shop_doc_getting_started.py` | 📝 |

### menu — Меню и каталог

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 2 | `menu-items-and-modifiers` | Позиции, категории, модификаторы | `test_shop_doc_menu.py` | ✅ |
| 2 | `builder-sections` | Сборка витрины в конструкторе | `test_shop_doc_builder.py` | ✅ |

### storefront — Витрина

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 2 | `publish-storefront` | Публикация и ссылка на витрину | `test_shop_doc_publish.py` | ✅ |
| 2 | `storefront-checkout` | Покупатель оформляет заказ до конца | `test_shop_doc_checkout.py` | ✅ |
| 3 | `storefront-mobile` | Мобильная витрина (390×844) | `test_shop_doc_checkout.py` | ✅ |

### orders — Заказы

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 2 | `incoming-orders-board` | Входящий заказ в доске, статусы | `test_shop_doc_orders.py` | ✅ |
| 3 | `order-status-flow` | Полный цикл статусов заказа | `test_shop_doc_orders.py` | ✅ |

### promos — Акции и лояльность

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 2 | `promo-create` | Создать акцию и показать на витрине | `test_shop_doc_promos.py` | ✅ |
| 3 | `loyalty-points` | Баллы лояльности покупателя | `test_shop_loyalty_e2e.py` | 📝 |

### delivery — Доставка

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 2 | `delivery-zone-map` | Зона доставки на карте (platform-map — красивый кадр) | `test_shop_doc_delivery.py` | ✅ |

### customer — Покупатель

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 3 | `customer-auth-phone` | Вход покупателя по телефону | `test_shop_customer_auth_e2e.py` | 📝 |
| 3 | `customer-feedback` | Отзыв покупателя: оценка → лента | `test_shop_doc_feedback.py` | ✅ |

### settings — Настройки

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 2 | `shop-settings` | Адрес витрины, часы работы, пресеты | `test_shop_doc_settings.py` | ✅ |

## Долг и заметки

- Существующие `test_shop_*` файлы покрывают механику, но без `@pytest.mark.scenario` — часть сценариев добавляется маркерами к готовым маршрутам, часть — новыми `test_shop_doc_*.py`.
- Анонимная витрина: `ui_page_anonymous` без X-Test-Scope (CORS preflight падает иначе).
- featured_slug для taxonomy: `shop-first-store`.
