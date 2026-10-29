"""Процессы платформы и библиотечные домены.

- ``<svc>/`` — HTTP-процесс; его TaskIQ — ``worker.py`` в том же каталоге.
- ``idle/`` — TaskIQ без HTTP: очереди ``idle`` и ``a2a_push``.
- ``worker_manifest.py`` — топология очередей TaskIQ.
"""
