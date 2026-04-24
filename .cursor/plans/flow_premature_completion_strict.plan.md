---
name: flow_premature_completion_strict
overview: Тихий выход, когда ни одна условная ветка не сработала, запрещён — всегда FlowPrematureCompletionError. Обратной совместимости нет. Все графы в репозитории приводятся к новым требованиям (явные fallback/END).
todos:
  - id: runtime-raise
    content: "flow.py: убрать continue при all-conditional; бросать FlowPrematureCompletionError (reason, extra stuck_at)"
    status: completed
  - id: audit-bundles
    content: "Пройти apps/flows/bundles/**/flow.json (+ тестовые фикстуры): у роутеров добавить явный fallback (безусловное ребро на ноду-сток или общий процессор → formatter → END)"
    status: completed
  - id: tests-update
    content: Переписать test_all_conditional_*; прогнать pytest flows
    status: pending
  - id: rules-sync
    content: Обновить .cursor/rules/flows_logic.mdc и при дублировании .windsurf/rules/flows_logic.md
    status: pending
isProject: false
---

# Завершение flow без совпавшей ветки = ошибка (без BC)

## Решение

- **Семантика рантайма:** если после ноды есть исходящие рёбра к нодам (`to` не `null`) и **ни одно** не активировалось — **всегда** `FlowPrematureCompletionError` (отдельный `reason`, напр. `no_conditional_match`, `extra.stuck_at`).
- **Обратной совместимости нет:** не добавляем флаги flow/node, не оставляем тихий выход.

## Графы в репозитории

- **Переделать** все конфиги, которые полагались на «молчаливый» stop: в частности [`apps/flows/bundles/example_graph/flow.json`](apps/flows/bundles/example_graph/flow.json) и любые другие bundle/тестовые графы, где у `classifier`/роутера только условные ветки без покрытия «остального» случая.
- **Паттерн исправления:** явный fallback — например безусловное ребро с `classifier` на общий обработчик / `formatter` / отдельную ноду «default», затем путь к терминалу (`to: null`), чтобы при любом `route` всегда был активный structural переход **или** корректное завершение через ноду, у которой нет обязательных несработавших ветвей (по текущим правилам `_raise_if_premature_completion`).

Конкретные рёбра подбираются по смыслу графа (example_graph: договориться, куда вести «не order/operator» — например в существующий `general_processor`, как в base-скилле, если это соответствует продукту).

## Файлы кода и правил

| Зона | Действие |
|------|----------|
| [`apps/flows/src/runtime/flow.py`](apps/flows/src/runtime/flow.py) | Убрать ветку `continue` при `_all_structural_outgoing_edges_are_conditional`; выбрасывать исключение |
| Bundles + при необходимости тестовые JSON | Правки графов |
| [`tests/flows/core/test_flow_and_join.py`](tests/flows/core/test_flow_and_join.py) | Ожидание исключения вместо «успеха»; при необходимости отдельный граф с fallback для «легального» полного прохода |
| [`.cursor/rules/flows_logic.mdc`](.cursor/rules/flows_logic.mdc) | Удалить пункт про «допустимое завершение» для всех условных |
| [`.windsurf/rules/flows_logic.md`](.windsurf/rules/flows_logic.md) | То же, если дублирует |

## Не делаем

- Флаги «как раньше» / opt-in silent exit.
- Документирование миграции для старых внешних графов — вне scope; в репо графы приведены в соответствие.
