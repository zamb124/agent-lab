# Исходники для iPhone и iPad

Здесь **может не быть файлов в git** — это нормально. Можно положить PNG или JPEG **сюда** (например `01.png`, `02.png`, …) **или прямо в родительский каталог `mobile/screens/`** — скрипт подхватит и то и другое. Затем из корня репозитория:

```bash
uv run python mobile/screens/generate_app_store_screenshots.py
```

Результат появится в `mobile/screens/generated/`. Подробности: [../README.md](../README.md).
