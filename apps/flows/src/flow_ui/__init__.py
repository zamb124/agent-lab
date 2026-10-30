"""Flow UI runtime-машинерия над ``ExecutionState``.

Wire-грамматика (``document``, ``protocol``, ``interface``, ``templates``,
``html_bindings``, ``json_patch``) живёт в ``core/ui_document``; здесь — модули,
которым нужен ``ExecutionState``: применение действий и событий, проекция,
publish gate и схема для редактора.
"""
