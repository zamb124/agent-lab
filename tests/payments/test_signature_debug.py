"""
Отладка подписи YooMoney webhook с реальными данными из production.
"""

import hashlib
import pytest


def test_real_signature_debug():
    """
    Отладка подписи с реальными данными из лога production:
    
    Webhook данные:
    'notification_type': 'card-incoming'
    'amount': '97.00'
    'withdraw_amount': '100.00' 
    'datetime': '2025-10-07T18:14:26Z'
    'sender': '' (пустой!)
    'codepro': 'false'
    'label': 'txn_db4a943d560e488a'
    'operation_id': '813176066791917096'
    'currency': '643'
    'sha1_hash': '949cf99277c287e7184a9d4246ca0fb189cccfcd'
    
    Ожидалось: ee3b4ef3e4525b7785b4ebbd4d75c93b242f19df
    Получено:  949cf99277c287e7184a9d4246ca0fb189cccfcd
    """
    
    # Реальные данные из webhook
    webhook_data = {
        'notification_type': 'card-incoming',
        'amount': '97.00',
        'withdraw_amount': '100.00',
        'datetime': '2025-10-07T18:14:26Z',
        'sender': '',
        'codepro': 'false',
        'label': 'txn_db4a943d560e488a',
        'operation_id': '813176066791917096',
        'currency': '643',
        'sha1_hash': '949cf99277c287e7184a9d4246ca0fb189cccfcd'
    }
    
    notification_secret = "CRc/NiG28QXh0bc7xXmwsMKC"
    
    print("🔍 ОТЛАДКА ПОДПИСИ YooMoney")
    print("=" * 50)
    
    # Попробуем разные варианты amount
    
    # Вариант 1: Используем amount (97.00)
    check_string_1 = (
        f"{webhook_data['notification_type']}&{webhook_data['operation_id']}&"
        f"{webhook_data['amount']}&{webhook_data['currency']}&"
        f"{webhook_data['datetime']}&{webhook_data['sender']}&"
        f"{webhook_data['codepro']}&{notification_secret}&{webhook_data['label']}"
    )
    
    hash_1 = hashlib.sha1(check_string_1.encode('utf-8')).hexdigest()
    
    print(f"📋 Строка 1 (amount): {check_string_1}")
    print(f"🔑 Хеш 1: {hash_1}")
    print(f"✅ Совпадает: {hash_1 == webhook_data['sha1_hash']}")
    print()
    
    # Вариант 2: Используем withdraw_amount (100.00)
    check_string_2 = (
        f"{webhook_data['notification_type']}&{webhook_data['operation_id']}&"
        f"{webhook_data['withdraw_amount']}&{webhook_data['currency']}&"
        f"{webhook_data['datetime']}&{webhook_data['sender']}&"
        f"{webhook_data['codepro']}&{notification_secret}&{webhook_data['label']}"
    )
    
    hash_2 = hashlib.sha1(check_string_2.encode('utf-8')).hexdigest()
    
    print(f"📋 Строка 2 (withdraw_amount): {check_string_2}")
    print(f"🔑 Хеш 2: {hash_2}")
    print(f"✅ Совпадает: {hash_2 == webhook_data['sha1_hash']}")
    print()
    
    # Вариант 3: Попробуем другой порядок параметров
    # Может для card-incoming порядок отличается?
    check_string_3 = (
        f"{webhook_data['notification_type']}&{webhook_data['operation_id']}&"
        f"{webhook_data['withdraw_amount']}&{webhook_data['currency']}&"
        f"{webhook_data['datetime']}&{webhook_data['sender']}&"
        f"{webhook_data['codepro']}&{notification_secret}&{webhook_data['label']}"
    )
    
    hash_3 = hashlib.sha1(check_string_3.encode('utf-8')).hexdigest()
    
    print(f"📋 Строка 3 (тот же что 2): {check_string_3}")
    print(f"🔑 Хеш 3: {hash_3}")
    print(f"✅ Совпадает: {hash_3 == webhook_data['sha1_hash']}")
    print()
    
    # Попробуем с разными секретами (возможно секрет не тот)
    test_secrets = [
        "CRc/NiG28QXh0bc7xXmwsMKC",  # Наш текущий
        "9798041830b49871c3a16ac87ce408a707e3502f04efea15b46ccc6b73cc047a",  # Старый
        ""  # Пустой
    ]
    
    for i, secret in enumerate(test_secrets, 1):
        check_string = (
            f"{webhook_data['notification_type']}&{webhook_data['operation_id']}&"
            f"{webhook_data['withdraw_amount']}&{webhook_data['currency']}&"
            f"{webhook_data['datetime']}&{webhook_data['sender']}&"
            f"{webhook_data['codepro']}&{secret}&{webhook_data['label']}"
        )
        
        hash_test = hashlib.sha1(check_string.encode('utf-8')).hexdigest()
        
        print(f"📋 Секрет {i} ({secret[:10]}...): {hash_test}")
        print(f"✅ Совпадает: {hash_test == webhook_data['sha1_hash']}")
        if hash_test == webhook_data['sha1_hash']:
            print(f"🎯 НАЙДЕН ПРАВИЛЬНЫЙ СЕКРЕТ: {secret}")
        print()
    
    # Что получил YooMoney  
    print(f"🎯 YooMoney отправил хеш: {webhook_data['sha1_hash']}")
    print("💡 Проверьте секрет в настройках YooMoney!")
    
    # Попробуем еще варианты - может кодировка или порядок?
    print("\n🧪 ДОПОЛНИТЕЛЬНЫЕ ТЕСТЫ:")
    
    # Основной формат но с разными кодировками
    base_string = f"card-incoming&813176438229065084&97.00&643&2025-10-07T18:20:38Z&&false&CRc/NiG28QXh0bc7xXmwsMKC&txn_cf55a781f5cb42c7"
    
    encodings = ['utf-8', 'ascii', 'latin1']
    for enc in encodings:
        try:
            test_hash = hashlib.sha1(base_string.encode(enc)).hexdigest()
            print(f"Кодировка {enc}: {test_hash}")
            print(f"Совпадает: {test_hash == webhook_data['sha1_hash']}")
        except:
            print(f"Кодировка {enc}: ОШИБКА")
    
    # Может секрет как-то экранируется?
    secret_variants = [
        "CRc/NiG28QXh0bc7xXmwsMKC",
        "CRc%2FNiG28QXh0bc7xXmwsMKC",  # URL encoded /
        "CRc\\NiG28QXh0bc7xXmwsMKC",   # Escaped /
    ]
    
    print("\n🔑 ВАРИАНТЫ СЕКРЕТА:")
    for variant in secret_variants:
        test_string = f"card-incoming&813176438229065084&97.00&643&2025-10-07T18:20:38Z&&false&{variant}&txn_cf55a781f5cb42c7"
        test_hash = hashlib.sha1(test_string.encode('utf-8')).hexdigest()
        print(f"Секрет '{variant}': {test_hash}")
        print(f"Совпадает: {test_hash == webhook_data['sha1_hash']}")
        if test_hash == webhook_data['sha1_hash']:
            print("🎯 НАЙДЕН ПРАВИЛЬНЫЙ СЕКРЕТ!!!")
    
    print(f"\n🎯 Целевой хеш от YooMoney: {webhook_data['sha1_hash']}")


def test_signature_variants():
    """Тест разных вариантов формирования подписи для card-incoming"""
    
    # Согласно документации YooMoney разные типы уведомлений могут использовать разные поля:
    # https://yoomoney.ru/docs/wallet/using-api/notification-p2p-incoming
    
    webhook_data = {
        'notification_type': 'card-incoming',
        'amount': '97.00',
        'withdraw_amount': '100.00',
        'datetime': '2025-10-07T18:14:26Z',
        'sender': '',
        'codepro': 'false', 
        'label': 'txn_db4a943d560e488a',
        'operation_id': '813176066791917096',
        'currency': '643'
    }
    
    expected_hash = '949cf99277c287e7184a9d4246ca0fb189cccfcd'
    secret = "CRc/NiG28QXh0bc7xXmwsMKC"
    
    # Для card-incoming может использоваться amount, а не withdraw_amount
    variants = [
        # Стандартный формат с amount
        f"card-incoming&813176066791917096&97.00&643&2025-10-07T18:14:26Z&&false&{secret}&txn_db4a943d560e488a",
        
        # Формат с withdraw_amount 
        f"card-incoming&813176066791917096&100.00&643&2025-10-07T18:14:26Z&&false&{secret}&txn_db4a943d560e488a",
        
        # Может для card-incoming другой порядок?
        f"card-incoming&813176066791917096&97.00&643&2025-10-07T18:14:26Z&false&{secret}&txn_db4a943d560e488a",
        
        # Без sender совсем?
        f"card-incoming&813176066791917096&97.00&643&2025-10-07T18:14:26Z&false&{secret}&txn_db4a943d560e488a"
    ]
    
    print(f"🎯 Ищем правильный формат для card-incoming")
    print(f"Expected hash: {expected_hash}")
    print()
    
    for i, variant in enumerate(variants, 1):
        hash_variant = hashlib.sha1(variant.encode('utf-8')).hexdigest()
        print(f"Вариант {i}: {variant}")
        print(f"Хеш: {hash_variant}")
        print(f"Совпадает: {hash_variant == expected_hash}")
        
        if hash_variant == expected_hash:
            print("🎉 НАЙДЕН ПРАВИЛЬНЫЙ ФОРМАТ!")
        print("-" * 50)
