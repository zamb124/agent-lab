# Рекурсивный цикл миграции (migration mode)

Запускается, когда задача — «навести канон», «конвертировать в TS»,
«вычистить отсебятину» в области платформы. Это исполняемый цикл, а не
чеклист-напоминание: он работает, пока счётчики не станут нулём.

Эталон — `references/target-architecture.md`. Нарушения и их замены —
`anti-patterns.md` (колонка «сигнатура» = `rule_id` из `scripts/ui_canon_rules.py`).

## Инварианты

1. **Монотонность.** `uv run python scripts/check_ui_kit_canon.py` не может
   вырасти — каждый коммит снижает счётчики или оставляет равными.
   После снижения — `uv run python scripts/check_ui_kit_canon.py --update`.
2. **Hard cutover.** Без адаптеров, алиасов «на переходный период», deprecated-
   слоёв. Callsites обновляются в том же коммите.
3. **Kit-first.** Если каноничной замены нет — сначала компонент/утилита в
   `core/frontend/static/lib/` + UIKDS-карточка + contract.spec, потом
   миграция callsites. Никогда — локальная копия «временно».
4. **Gate-зелёный на каждом шаге.** `make ui` (или минимум `ui-build` +
   `ui-typecheck` + `lint-ts` + затронутые specs) зелёный перед коммитом.
5. **Один unit — один коммит.** Unit = файл или сплочённый кластер
   (компонент + его callsites + тест). Коммит сообщение: зона и rule_id.

## Цикл

```
LOOP:
  1. QUEUE  := uv run python scripts/report_ui_kostyli.py --json
              → reports/ui-kostyli.json
  2. unit   := выбрать следующий unit по приоритету (ниже)
  3. scan   := для unit — какие rule_id сработали (из отчёта) + чтение файла
  4. classify каждое нарушение:
       kit-аналог есть      → заменить, удалить локальную реализацию
       kit-аналога нет      → KIT-GAP: остановиться, создать core-компонент
                             (UIKDS карточка + contract.spec), потом заменить
       ложное срабатывание  → исправить сигнатуру правила в ui_canon_rules.py
                             (или path_exclude), прогнать baseline --update
       паттерн новый        → запись в anti-patterns.md + новое правило
  5. convert: unit → .ts (см. recipes.md § TS): strict-типы, declare-поля,
     import type, lit-specifiers. Ошибки типов чинить честно — не `any`.
  6. gates: npm run build:ui && npx tsc -p tsconfig.json &&
            соответствующие spec-файлы && (make lint-ts если тронуты каноны)
  7. commit: "refactor(<svc>): <что> [<rule_id>]" + --update baseline при падении счётчиков
  8. repeat
```

## Приоритет очереди

1. **Блокирующие**: vendored_lit_path, extends_native, fetch_outside_events —
   они ломают сборку/архитектуру.
2. **Kit-gap'ы**: custom_primitive по популярности класса (dropdown в 5 сервисах
   → один platform-dropdown вместо пяти локальных).
3. **По слоям снизу вверх**: lib/utils → lib/styles → lib/events →
   lib/components → lib/components/fields → lib/base → apps (по убыванию
   файлов: flows → frontend → crm → sync → office → worktracker → wiki →
   rag → stock → provider_litserve) → tests.
4. Soft-нарушения в unit — чинить попутно, только если детектор точный;
   иначе оставить в очереди.

## Конверсия файла в .ts — минимальный контракт

- `git mv x.js x.ts`, правки спецификаторов импортёров НЕ нужны
  (`.js` в `import` остаётся — tsc/esbuild резолвят `.js`→`.ts`).
- Сразу честные типы: `static properties` + `declare` для реактивных полей;
  интерфейсы payload'ов у фабрик; `unknown` + сужение вместо `any`.
- Нет `// @ts-ignore`, `as any`, `!` без необходимости; нельзя типизировать
  честно → остановиться и описать конфликт (kit может требовать расширения).

## Отчёт итерации

Каждая сессия цикла заканчивает статусом: сколько unit'ов обработано, дельта
счётчиков (`ui_js_files`, hard-правила), какие kit-gap'ы добавлены, что в
очереди следующее. Незаконченный unit не коммитится половинчато.

## Стоп-условия

- `ui_js_files == 0` и все hard-правила == 0 → миграция завершена;
  остаются soft-улучшения (по желанию).
- Нарушение, для которого канон не даёт честного решения → стоп, правим
  правило-владельца (`frontend.mdc`/`ui_components.mdc`/`ui_fields.mdc`)
  в том же изменении, потом код (`main.mdc` § Принципы п.9).
