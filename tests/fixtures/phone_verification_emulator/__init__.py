"""Реальный HTTP-эмулятор провайдеров верификации телефона.

Поднимает локальный ASGI-сервер, который говорит официальными протоколами
Telegram Bot API, MAX Bot API, Yandex ID, VK ID, Sber ID и SMS.RU —
без моков и monkeypatching: прод-клиенты ходят на него через
endpoint-оверрайды в `customer_auth.brands.<apex>` (конфиг).
"""
