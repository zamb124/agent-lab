# Stock — матрица покрытия документационными инструкциями

Статусы: ✅ опубликовано · 🚧 в работе · 📝 запланировано · ⛔ не документируем.

Админка `stock-app`, `/stock/`, port 9026, fixture `stock_ui` (Wave 0).
Домен: `tests/fixtures/stock.py` — `stock_di`, `stock_init` (виртуальные локации + ЕИ для `system`),
`stock_client`. Компания инициализируется через `init_company_stock` — проверить необходимость
для worker-компании при первом сценарии.

## UI-поверхности

| Страница | Что видит пользователь |
|---|---|
| `stock-home-page` | Обзор склада |
| `stock-locations-page` | Дерево локаций/складов |
| `stock-products-page` | Каталог товаров |
| `stock-transfer-page` | Оформление перемещения |
| `stock-transfers-page` | Журнал перемещений |
| `stock-valuation-page` | Денежная оценка запасов |

## Блоки и инструкции

### getting-started — С чего начать

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 1 | `stock-overview` | Обзор склада: локации, остатки, журнал | `test_stock_doc_getting_started.py` | ✅ |

### locations — Локации и склады

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 2 | `locations-tree` | Создать склад и зоны хранения | `test_stock_doc_locations.py` | ✅ |

### products — Товары

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 2 | `products-catalog` | Завести товар и единицы измерения | `test_stock_doc_products.py` | ✅ |

### transfers — Приход и перемещения

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 1 | `stock-incoming` | Провести поступление товара на склад | `test_stock_doc_incoming.py` | ✅ |
| 2 | `receive-stock` | Приход товара на склад от поставщика | — | ⛔ дубль `stock-incoming` |
| 2 | `transfer-between-locations` | Перемещение между складами | `test_stock_doc_transfers.py` | ✅ |
| 3 | `transfers-journal` | Журнал движений, детали проводки | `test_stock_doc_transfers.py` | ✅ |

### valuation — Оценка запасов

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 3 | `valuation-report` | Стоимость запасов по складам | `test_stock_doc_valuation.py` | ✅ |

## Долг и заметки

- Сквозной сценарий «товар → приход → перемещение → оценка» может стать featured complete-guide — решить при реализации.
- featured_slug для taxonomy: `stock-overview`.
