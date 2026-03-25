# Сценарии (автогенерация)

Каталог заполняется E2E-тестами из `tests/ui/e2e/`: при использовании фикстуры `scenario` и вызовов `await scenario.step(..., page)` для каждого шага создаётся подпапка с `README.md` и `screenshots/`.

- Без тега: `docs/scenarios/<slug>/`
- С маркером `@pytest.mark.scenario_tag("имя")`: `docs/scenarios/<имя>/<slug>/`

Отключить запись файлов: переменная окружения `UI_SCENARIO_DOCS=0`.
