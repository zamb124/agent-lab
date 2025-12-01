# auth

### <span class="http-method get">GET</span> `/api/v1/auth/providers`

**Get Auth Providers**

Возвращает список доступных провайдеров авторизации

#### Ответы

| Код | Описание |
|-----|----------|
| `200` | Successful Response |

---

### <span class="http-method get">GET</span> `/api/v1/auth/login/{provider_name}`

**Start Auth**

Начинает процесс авторизации с выбранным провайдером.

Args:
    provider_name: Имя провайдера (yandex, google, etc.)
    redirect_uri: URI для возврата после авторизации

#### Параметры пути

| Параметр | Тип | Описание |
|----------|-----|----------|
| `provider_name` | string |  |

#### Query параметры

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `redirect_uri` | string | Нет |  |

#### Ответы

| Код | Описание |
|-----|----------|
| `200` | Successful Response |
| `422` | Validation Error |

---

### <span class="http-method get">GET</span> `/api/v1/auth/callback/{provider_name}`

**Auth Callback**

Обрабатывает callback от провайдера авторизации.

Args:
    provider_name: Имя провайдера
    code: Код авторизации от провайдера
    state: State для CSRF защиты
    error: Ошибка от провайдера (если есть)
    redirect_uri: URI callback

#### Параметры пути

| Параметр | Тип | Описание |
|----------|-----|----------|
| `provider_name` | string |  |

#### Query параметры

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `code` | string | Да |  |
| `state` | string | Да |  |
| `error` | string | Нет |  |
| `redirect_uri` | string | Нет |  |

#### Ответы

| Код | Описание |
|-----|----------|
| `200` | Successful Response |
| `422` | Validation Error |

---

### <span class="http-method post">POST</span> `/api/v1/auth/logout`

**Logout**

Завершает сессию пользователя.

Args:
    session_id: ID сессии для завершения

#### Query параметры

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `session_id` | string | Да |  |

#### Ответы

| Код | Описание |
|-----|----------|
| `200` | Successful Response |
| `422` | Validation Error |

---

### <span class="http-method get">GET</span> `/api/v1/auth/status`

**Auth Status**

Возвращает статус системы авторизации

#### Ответы

| Код | Описание |
|-----|----------|
| `200` | Successful Response |

---
