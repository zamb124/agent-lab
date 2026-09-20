"""Realtime слой Sync: каталог `op_*` (REST + Centrifugo RPC) и TaskIQ STT.

Команды: `SYNC_OPERATIONS` → тот же `op_*` с REST-зеркала и с bus
`POST /sync/api/internal/realtime/command`. Push — `PlatformEvent` через bus
и Centrifugo `/realtime`. Heavy STT — TaskIQ (`enqueue(SYNC_TRANSCRIBE_*)`).
"""
