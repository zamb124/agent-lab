"""Подпись Token Т-Банка: официальные hex из документации, без HTTP."""

from core.clients.payment.tinkoff_token import compute_tinkoff_token


def test_official_init_token_hex() -> None:
    token = compute_tinkoff_token(
        {
            "TerminalKey": "MerchantTerminalKey",
            "Amount": 19200,
            "OrderId": "00000",
            "Description": "Подарочная карта на 1000 рублей",
            "DATA": {"Phone": "+71234567890", "Email": "a@test.com"},
            "Receipt": {"Email": "a@test.ru"},
        },
        "11111111111111",
    )
    assert token == "72dd466f8ace0a37a1f740ce5fb78101712bc0665d91a8108c7c8a0ccd426db2"


def test_official_notification_token_hex() -> None:
    token = compute_tinkoff_token(
        {
            "TerminalKey": "1234567890DEMO",
            "OrderId": "000000",
            "Success": True,
            "Status": "AUTHORIZED",
            "PaymentId": "0000000",
            "ErrorCode": "0",
            "Amount": 1111,
            "CardId": "000000",
            "Pan": "200000******0000",
            "ExpDate": "1111",
            "RebillId": "000000",
        },
        "11111111111",
    )
    assert token == "1c0964277d0213349243065a0d5b838b8e90d2d25f740d0f2767836e710e80c8"
