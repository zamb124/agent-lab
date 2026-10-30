"""Flow UI: интерфейс flow поверх чистого A2A 1.0.

- ``document`` — грамматика блоков и документ (``FlowUIDocument``), единственная спецификация;
- ``schema`` — JSON Schema грамматики для редактора (``flow_ui_schema``);
- ``protocol`` — mediaType, artifactId и payload-модели wire (``FlowUIRender``, ``FlowUIActionMessage``);
- ``projection`` — проекция ``ExecutionState`` по путям интерфейса и патчи RFC 6902;
- ``action`` — приём ``ui-action``: значения input-блоков становятся полями state;
- ``runtime`` — применение ``ui_render``/``ui_navigate`` к ``ExecutionState``;
- ``effects`` — те же события из sandbox-кода через capability gateway;
- ``html_bindings`` — ``data-bind``/``data-show`` из ``source`` блока ``html``;
- ``problems`` — publish gate документа;
- ``templates`` — галерея готовых документов;
- ``interface`` — ответ ``GET .../interface``.

Пакет не реэкспортирует модули: ``core.state.execution_state`` импортирует ``document``/``protocol``,
а ``runtime``/``action``/``projection`` импортируют ``ExecutionState``.
"""
