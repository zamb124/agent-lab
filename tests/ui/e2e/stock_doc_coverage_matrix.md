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
| `stock-locations-page` | Карта склада: дерево локаций + карточка локации |
| `stock-stock-report-page` | Остатки по локациям с субсуммами |
| `stock-products-page` | Каталог товаров |
| `stock-transfer-page` | Оформление перемещения |
| `stock-transfers-page` | Журнал перемещений |
| `stock-valuation-page` | Денежная оценка запасов |
| `stock-moves-page` | Лента всех строк движений товара с фильтрами |
| `stock-packages-page` | Тара/упаковки: содержимое и перемещение целиком |
| `stock-inventory-page` | Инвентаризация: due-ячейки, факт vs учёт |
| `stock-*-settings` | Справочники: склады, типы хранения/тары, ресурсы, правила |
| `stock-valuation-journal-page` | Журнал слоёв оценки: приходы и списания |
| `stock-valuation-batches-page` | Партии запасов (FIFO-слои) по товарам |
| `stock-waves-page` | Волны сборки: свободные строки отбора → волна → выпуск |
| `stock-lots-page` | Партии и сроки годности склада: FEFO-статусы, форма партии |
| `stock-op-types-page` | Типы операций: политики резерва, недостачи, партий, префиксы |
| `stock-decisions-page` | Журнал рефлекс-решений размещения с фильтром статуса |

## Блоки и инструкции

### getting-started — С чего начать

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 1 | `stock-overview` | Обзор склада: локации, остатки, журнал | `test_stock_doc_getting_started.py` | ✅ |

### locations — Локации и склады

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 2 | `locations-tree` | Создать склад и зоны хранения | `test_stock_doc_locations.py` | ✅ |
| 2 | `stock-by-location` | Остатки по локациям: где что лежит | `test_stock_doc_stock_report.py` | ✅ |
| 3 | `moves-journal` | Журнал движений строками товара | `test_stock_doc_operations.py` | ✅ |
| 3 | `packages-containers` | Тара: содержимое и перемещение | `test_stock_doc_operations.py` | ✅ |
| 3 | `inventory-count` | Инвентаризация: факт vs учёт | `test_stock_doc_operations.py` | ✅ |
| 2 | `stock-admin-lots` | Партии и сроки годности: FEFO-карта склада | `test_stock_admin_new_pages.py` | 🚧 |

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
| 2 | `stock-admin-waves` | Волны сборки: строки заказов → волна → выпуск | `test_stock_admin_new_pages.py` | 🚧 |

### valuation — Оценка запасов

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 3 | `valuation-report` | Стоимость запасов по складам | `test_stock_doc_valuation.py` | ✅ |

### settings — Настройки склада

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 2 | `settings-warehouse` | Склады, типы хранения, тара | `test_stock_doc_operations.py` | ✅ |
| 2 | `settings-uoms` | Единицы измерения и упаковки | `test_stock_doc_operations.py` | ✅ |
| 2 | `settings-catalogs` | Ресурсы/техника, правила размещения и пополнения, маршруты, партии | `test_stock_doc_operations.py` | ✅ |
| 2 | `stock-admin-operation-types` | Типы операций: полный редактор политик | `test_stock_admin_new_pages.py` | 🚧 |
| 3 | `stock-admin-decisions` | Рефлекс-решения: аудит размещений | `test_stock_admin_new_pages.py` | 🚧 |

### tsd — ТСД-сканер

Сценарии — `test_stock_tsd_terminal.py` (18 тестов) и `test_stock_tsd_lots_returns.py` (4 теста).

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 1 | `tsd-receive` | Приёмка сканом: локация → товар → количество | `test_stock_tsd_receive` | ✅ |
| 1 | `tsd-receive-multiline` | Приёмка по накладной, несколько товаров | `test_stock_tsd_receive_multiline` | ✅ |
| 1 | `tsd-move` | Перемещение между ячейками | `test_stock_tsd_move` | ✅ |
| 1 | `tsd-putaway` | Размещение с подсказкой ячейки | `test_stock_tsd_putaway` | ✅ |
| 1 | `tsd-count` | Пересчёт ячейки | `test_stock_tsd_count` | ✅ |
| 1 | `tsd-count-zero` | Пересчёт: фактический ноль | `test_stock_tsd_count_zero` | ✅ |
| 1 | `tsd-container-move` | Перемещение тары целиком | `test_stock_tsd_container_move` | ✅ |
| 2 | `tsd-document-pick` | Отбор по накладной | `test_stock_tsd_document_pick` | ✅ |
| 2 | `tsd-document-pack` | Упаковка по накладной | `test_stock_tsd_document_pack` | ✅ |
| 2 | `tsd-document-ship` | Отгрузка по накладной | `test_stock_tsd_document_ship` | ✅ |
| 2 | `tsd-document-exception` | Исключение: недостача по строке | `test_stock_tsd_document_exception` | ✅ |
| 2 | `tsd-document-container-move` | Перемещение тары по документу | `test_stock_tsd_document_container_move` | ✅ |
| 2 | `tsd-inquiry` | Справочный скан: товар и остатки | `test_stock_tsd_inquiry_rescan` | ✅ |
| 2 | `tsd-context-chips` | Контекст-чипы: оператор, ресурс, документ | `test_stock_tsd_context_chips` | ✅ |
| 3 | `tsd-offline-outbox` | Офлайн-очередь исполнения | `test_stock_tsd_offline_outbox` | ✅ |
| 2 | `stock-tsd-hid-scan` | HID-сканер: клавиатурный ввод = скан | `test_stock_tsd_hid_scan` | ✅ |
| 2 | `stock-tsd-task-switch` | Переключение между заданиями | `test_stock_tsd_task_switch` | ✅ |
| 2 | `stock-tsd-receive-lots` | Приёмка партии: номер и срок годности | `test_stock_tsd_lots_returns.py` | ✅ |
| 2 | `stock-tsd-serials` | Приёмка серийников: скан = 1 шт | `test_stock_tsd_lots_returns.py` | ✅ |
| 2 | `stock-tsd-fefo-pick` | Отбор партий по FEFO | `test_stock_tsd_lots_returns.py` | ✅ |
| 2 | `stock-tsd-return` | Возврат от покупателя с карточки накладной | `test_stock_tsd_lots_returns.py` | ✅ |
| 1 | `tsd-scanner` | Общая инструкция входа и скана | — | ⛔ покрыто набором выше |

### full-lifecycle — Полный цикл склада

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 3 | `stock-full-lifecycle` | Настройка администратором → смена на ТСД | `test_stock_full_lifecycle.py` | ✅ |

## Долг и заметки

- Сквозной сценарий «товар → приход → перемещение → оценка» может стать featured complete-guide — решить при реализации.
- featured_slug для taxonomy: `stock-overview`.
