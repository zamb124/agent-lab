# Third-Party Notices

Платформа Humanitec (`agent-lab`) распространяется под [Elastic License 2.0](LICENSE).
Copyright (c) 2024-2026 Шведов Виктор Викторович.

Ниже перечислены компоненты с отличной от ELv2 лицензией. Их условия сохраняются
независимо от лицензии основного репозитория. ELv2 не перелицензирует сторонний код.

## Vendored / submodule

| Компонент | Путь | Лицензия | Источник |
|---|---|---|---|
| Goose (HumanitecAgent desktop upstream) | `apps/agent/desktop/vendor/goose` | Apache-2.0 | https://github.com/block/goose |

Текст лицензии upstream: `apps/agent/desktop/vendor/goose/LICENSE` (после инициализации submodule).

## Bundled assets

| Компонент | Путь | Лицензия |
|---|---|---|
| Noto Sans | `core/files/writer/fonts/NotoSans-Regular.ttf` | SIL Open Font License 1.1 |

Полный текст: [core/files/writer/fonts/OFL.txt](core/files/writer/fonts/OFL.txt).

## Runtime и dev-зависимости

Python-пакеты (`uv.lock`, группы в `pyproject.toml`) и npm-пакеты (`package-lock.json`)
лицензируются авторами соответственно (преимущественно MIT, Apache-2.0, BSD).
Список не дублируется в этом файле; при распространении бинарных артефактов соблюдайте
условия каждой зависимости и сохраняйте их copyright/notices.

Для аудита лицензий зависимостей:

```bash
uv pip tree
npm ls --all
```
