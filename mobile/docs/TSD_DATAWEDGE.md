# ТСД `/stock/tsd`: сканеры, DataWedge, native-мост

Терминал — тот же web-бандл `apps/stock/ui-dist/tsd.js`, открытый в браузере,
PWA или Capacitor WebView. Ввод скана унифицирован в `TsdScanInput`
(`apps/stock/ui/pages/tsd/scan/scan-input.ts`); все источники сходятся в один
обработчик `onScan(code)`.

## Источники ввода

| Источник | Как работает | Настройка |
|---|---|---|
| HID-сканер (BT/USB cradle) | Быстрая пачка keydown + Enter, детект по межсимвольной паузе | Ничего: сканер в keyboard wedge-режиме |
| Камера | `stock-tsd-camera-scanner` (getUserMedia + BarcodeDetector) | Разрешение камеры в браузере/оболочке |
| Ручной ввод | Поле на экране → `submit()` | — |
| DataWedge keystroke | То же HID-пачка | Profile → Keystroke output |
| DataWedge intent / нативный плагин | `window.dispatchEvent(new CustomEvent('stock/tsd:native_scan', { detail: { code } }))` | См. ниже |

## Native-мост

Скан без клавиатурной эмуляции (DataWedge в intent-режиме, скан-кнопка
терминала, будущий Capacitor-плагин) инжектит код событием на `window`:

```ts
window.dispatchEvent(new CustomEvent('stock/tsd:native_scan', {
    detail: { code: '4607012345678' },
}));
```

Контракт: `detail.code` — непустая строка; trim и минимальная длина (3)
применяются в `TsdScanInput.submit()`. Некорректные события молча
игнорируются. Из нативной оболочки (Android):

```java
webView.evaluateJavascript(
    "window.dispatchEvent(new CustomEvent('stock/tsd:native_scan'," +
    "{detail:{code:'" + jsEscape(code) + "'}}))", null);
```

## DataWedge (Zebra)

Два рабочих профиля, выбор — по железу:

1. **Keystroke output** (по умолчанию, нулевой код): DataWedge шлёт
   символы как клавиатуру — их ловит HID-ветка `TsdScanInput`.
   Profile: `Keystroke output → Enabled`, `Action key → Enter`.
2. **Intent output** → JavaScript-мост выше: intent ловится в
   `MainActivity` и пробрасывается в WebView через `evaluateJavascript`.
   Код моста добавляется рядом с `LinnexBridgeWebChromeClient`, когда
   появится Zebra-железо — плагин-обёртка не вендорится заранее.

## Офлайн

При `navigator.onLine === false` коммиты исполнения встают в
`stock/tsd_outbox` (persisted в `platform:stock:tsd.outbox`) с ключом
идемпотентности, зафиксированным до первой отправки. Доставка — FIFO при
`network.online && ws.status === 'open'`; элемент с доменным отказом
останавливает очередь и ждёт решения оператора (UI показывает счётчик,
список и удаление). Записи старше 24 ч не гидратируются.
