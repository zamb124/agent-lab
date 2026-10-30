"""Платформенный UI-документ-протокол (Flow UI) поверх чистого A2A 1.0.

- ``document`` — грамматика блоков и документ (``FlowUIDocument``), единственная спецификация;
- ``protocol`` — mediaType, artifactId и payload-модели wire (``FlowUIRender``, ``FlowUIActionMessage``);
- ``interface`` — ответ ``GET .../interface``;
- ``json_patch`` — патчи RFC 6902 над JSON (``json_patch_operations``, ``apply_json_patch``).

Машинерия мутации ``ExecutionState``, галерея ``templates`` и ``html_bindings``
живут в ``apps/flows/src/flow_ui`` — Flow UI mutation принадлежит сервису flows.

Пакет не реэкспортирует модули: ``apps.flows.src.state.execution_state`` импортирует ``document``/``protocol``.
"""
