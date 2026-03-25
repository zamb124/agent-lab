# Сценарии (автогенерация)

Каталог заполняется E2E-тестами из `tests/ui/e2e/`: при использовании фикстуры `scenario` и вызовов `await scenario.step(..., page)` для каждого шага создаётся подпапка с `README.md` и `screenshots/`.

- Без тега: `docs/scenarios/<slug>/`
- С маркером `@pytest.mark.scenario_tag("имя")`: `docs/scenarios/<имя>/<slug>/`

Отключить запись файлов: переменная окружения `UI_SCENARIO_DOCS=0`.

**MkDocs:** пункты навигации «Сценарии (E2E, автогенерация)» подставляются хуком `mkdocs_hooks.py` при `mkdocs build` — все `docs/scenarios/**/README.md` попадают в меню автоматически (название — первая строка `# ...` в файле). В `mkdocs.yml` сценарии вручную не перечисляются.
