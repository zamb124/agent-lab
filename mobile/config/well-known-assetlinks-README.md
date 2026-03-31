# Публикация Digital Asset Links (Android TWA)

Файл должен быть доступен по **HTTPS** на том же origin, что и `start_url` PWA:

`https://<ваш-домен>/.well-known/assetlinks.json`

**Платформа (frontend и др. с `register_platform_pwa_routes`):** положите заполненный JSON в `core/frontend/pwa/assetlinks.json` (шаблон — `assetlinks.json.example` рядом). Маршрут `GET /.well-known/assetlinks.json` регистрируется только если файл существует (в git не коммитится — см. корневой `.gitignore`). На деплое файл копируют в образ/том вместе с конфигом.

## Содержимое

1. Соберите TWA через Bubblewrap и получите `package_name` (applicationId) и SHA-256 отпечаток **release**-ключа подписи.
2. Заполните шаблон [`assetlinks.json.template`](assetlinks.json.template).
3. Выложите JSON на сервер; `Content-Type: application/json`.

Проверка: [Google Digital Asset Links](https://developers.google.com/digital-asset-links/tools/generator) или `assetlinks` в документации Android.

## Пример для nginx

```nginx
location = /.well-known/assetlinks.json {
    add_header Content-Type application/json;
    alias /var/www/static/assetlinks.json;
}
```

Инфраструктура платформы может монтировать файл иначе — главное: стабильный URL и корректный JSON.
