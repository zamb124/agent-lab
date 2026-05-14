"""
Тесты утилит авторизации.

Проверяют работу с JWT токенами, хешированием паролей и токенов.
Без моков - все реальные функции.
"""

from datetime import datetime, timedelta, timezone

from core.auth.utils import (
    compare_passwords,
    generate_access_token,
    generate_refresh_token,
    generate_session_id,
    get_cache_session_key,
    get_cache_token_key,
    get_token_info,
    hash_password,
    hash_token,
)


class TestPasswordHashing:
    """Тесты хеширования паролей."""

    def test_hash_password(self):
        """Хеширование пароля создает bcrypt хеш."""
        password = "test_password_123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        assert hash1 != password
        assert hash2 != password
        assert hash1 != hash2
        assert len(hash1) > 50

    def test_compare_passwords_correct(self):
        """Сравнение правильного пароля возвращает True."""
        password = "test_password_123"
        password_hash = hash_password(password)

        assert compare_passwords(password, password_hash) is True

    def test_compare_passwords_incorrect(self):
        """Сравнение неправильного пароля возвращает False."""
        password = "test_password_123"
        wrong_password = "wrong_password"
        password_hash = hash_password(password)

        assert compare_passwords(wrong_password, password_hash) is False

    def test_compare_passwords_none_hash(self):
        """Сравнение с None хешем возвращает False."""
        assert compare_passwords("password", None) is False


class TestTokenHashing:
    """Тесты хеширования токенов."""

    def test_hash_token(self):
        """Хеширование токена создает SHA256 хеш."""
        token = "test_token_12345"
        hash1 = hash_token(token)
        hash2 = hash_token(token)

        assert hash1 == hash2
        assert len(hash1) == 64
        assert hash1 != token

    def test_hash_token_different_tokens(self):
        """Разные токены дают разные хеши."""
        token1 = "token1"
        token2 = "token2"

        hash1 = hash_token(token1)
        hash2 = hash_token(token2)

        assert hash1 != hash2


class TestJWTTokens:
    """Тесты работы с JWT токенами."""

    def test_generate_access_token(self):
        """Генерация access токена создает валидный JWT."""
        user = {
            "id": 1,
            "iss": "test_issuer",
            "email": "test@example.com",
        }
        session_id = "session_123"
        jwt_secret = "test_secret_key"
        jwt_algorithm = "HS256"
        token_exp_minutes = 60

        token = generate_access_token(
            user=user,
            session_id=session_id,
            jwt_secret=jwt_secret,
            jwt_algorithm=jwt_algorithm,
            token_exp_minutes=token_exp_minutes,
        )

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 50

    def test_get_token_info_valid(self):
        """Декодирование валидного токена возвращает данные."""
        user = {
            "id": 1,
            "iss": "test_issuer",
            "email": "test@example.com",
        }
        session_id = "session_123"
        jwt_secret = "test_secret_key"
        jwt_algorithm = "HS256"

        token = generate_access_token(
            user=user,
            session_id=session_id,
            jwt_secret=jwt_secret,
            jwt_algorithm=jwt_algorithm,
            token_exp_minutes=60,
        )

        token_info = get_token_info(
            token=token,
            jwt_secret=jwt_secret,
            jwt_algorithm=jwt_algorithm,
        )

        assert token_info is not None
        assert token_info["id"] == 1
        assert token_info["iss"] == "test_issuer"
        assert token_info["email"] == "test@example.com"
        assert token_info["session_id"] == "session_123"

    def test_get_token_info_invalid_secret(self):
        """Декодирование токена с неправильным секретом возвращает None."""
        user = {
            "id": 1,
            "iss": "test_issuer",
            "email": "test@example.com",
        }
        session_id = "session_123"
        jwt_secret = "test_secret_key"
        wrong_secret = "wrong_secret_key"

        token = generate_access_token(
            user=user,
            session_id=session_id,
            jwt_secret=jwt_secret,
            jwt_algorithm="HS256",
            token_exp_minutes=60,
        )

        token_info = get_token_info(
            token=token,
            jwt_secret=wrong_secret,
            jwt_algorithm="HS256",
        )

        assert token_info is None

    def test_get_token_info_expired(self):
        """Декодирование истекшего токена возвращает None."""
        user = {
            "id": 1,
            "iss": "test_issuer",
            "email": "test@example.com",
        }
        session_id = "session_123"
        jwt_secret = "test_secret_key"

        token = generate_access_token(
            user=user,
            session_id=session_id,
            jwt_secret=jwt_secret,
            jwt_algorithm="HS256",
            token_exp_minutes=-1,
        )

        token_info = get_token_info(
            token=token,
            jwt_secret=jwt_secret,
            jwt_algorithm="HS256",
        )

        assert token_info is None


class TestRefreshToken:
    """Тесты генерации refresh токенов."""

    def test_generate_refresh_token(self):
        """Генерация refresh токена создает случайный токен."""
        token_data = generate_refresh_token(token_exp_days=7)

        assert "refresh_token" in token_data
        assert "expires_at" in token_data
        assert len(token_data["refresh_token"]) > 50
        assert isinstance(token_data["expires_at"], datetime)

    def test_generate_refresh_token_expires_at(self):
        """Expires_at устанавливается правильно."""
        token_data = generate_refresh_token(token_exp_days=7)
        expires_at = token_data["expires_at"]

        assert expires_at > datetime.now(timezone.utc)
        assert expires_at < datetime.now(timezone.utc) + timedelta(days=8)

    def test_generate_refresh_token_unique(self):
        """Каждый refresh токен уникален."""
        token1 = generate_refresh_token(token_exp_days=7)
        token2 = generate_refresh_token(token_exp_days=7)

        assert token1["refresh_token"] != token2["refresh_token"]


class TestSessionID:
    """Тесты генерации session ID."""

    def test_generate_session_id(self):
        """Генерация session ID создает UUID."""
        session_id = generate_session_id()

        assert session_id is not None
        assert isinstance(session_id, str)
        assert len(session_id) == 36

    def test_generate_session_id_unique(self):
        """Каждый session ID уникален."""
        session_id1 = generate_session_id()
        session_id2 = generate_session_id()

        assert session_id1 != session_id2


class TestCacheKeys:
    """Тесты генерации ключей кэша."""

    def test_get_cache_token_key(self):
        """Генерация ключа кэша токена."""
        token = "test_token_123"
        prefix = "token:auth:"

        key = get_cache_token_key(token, prefix)

        assert key.startswith(prefix)
        assert len(key) > len(prefix)
        assert len(key) == len(prefix) + 64

    def test_get_cache_session_key(self):
        """Генерация ключа кэша сессии."""
        user_id = 123
        prefix = "session:auth:"

        key = get_cache_session_key(user_id, prefix)

        assert key == f"{prefix}{user_id}"

