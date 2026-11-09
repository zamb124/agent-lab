# Geo — матрица покрытия документационными инструкциями

Статусы: ✅ опубликовано · 🚧 в работе · 📝 запланировано · ⛔ не документируем.

Админка `geo-app`, `/geo/` на `system.<subdomain>:9028`, `_GEO_UI = AppUI(SERVICE_UI_REGISTRY["geo"])`.
Карта: helpers `wait_geo_map_ready`, `click_geo_map_at` в `tests/ui/shots/conftest.py`;
`geo_directory_ready` — micro.osm импорт (session fixture).

## UI-поверхности

| Страница | Что видит пользователь |
|---|---|
| `geo-overview-page` | Обзор гео-движка |
| `geo-addresses-page` | Справочник адресов |
| `geo-sources-page` | Источники геоданных (импорт/покрытие) |
| `geo-route-lab-page` | Маршрутная лаборатория на карте |
| `geo-map-lab-page` | Карточная лаборатория |

## Блоки и инструкции

### route_lab — Маршрутная лаборатория

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 1 | `route-lab` | Маршрутная лаборатория | `test_geo_route_lab_e2e.py` | ✅ |
| 2 | `route-lab-matrix` | Матрица времени и оптимальный объезд | `test_geo_route_lab_e2e.py` | ✅ |

### addresses — Адреса

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 2 | `admin-edit-address` | Админ-правка адреса | `test_geo_addresses_admin_e2e.py` | ✅ |
| 2 | `address-lookup-on-map` | Найти адрес на карте (user-уровень) | новый | 📝 |

### sources — Источники геоданных

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 3 | `admin-sources-hub` | Хаб источников и покрытие | `test_geo_sources_admin_e2e.py` | ✅ |

### getting-started (новый тег при необходимости)

| Уровень | doc_slug | Инструкция | Тест | Статус |
|---|---|---|---|---|
| 1 | `geo-overview-tour` | Обзор возможностей geo | новый | 📝 |

## Долг и заметки

- Wave 0: geo добавлен в taxonomy (service_order + tags addresses/sources/route_lab) — существующие 4 инструкции публикуются.
- Сервис по сути системная админка компании — обсуждено: достаточно 4–6 сценариев, user-level — только обзор + поиск адреса.
- featured_slug: `route-lab`.
