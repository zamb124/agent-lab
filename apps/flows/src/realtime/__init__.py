"""Realtime-слой flows.

Доменных WS-команд у flows нет: задачи (включая HITL) ведутся через
платформенное ядро WorkItem (сервис worktracker, HTTP + push-события).
Чат сервиса flows работает по A2A SSE (`apps/flows/src/api/a2a.py`).
"""
