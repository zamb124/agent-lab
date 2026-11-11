"""Идентичность: одна таблица — один модуль, контракты без таблицы — contracts."""

from core.models.identity_models.auth_result import (
    AuthResult,
)
from core.models.identity_models.auth_session import (
    AuthSession,
)
from core.models.identity_models.company import (
    Company,
)
from core.models.identity_models.contracts import (
    ANONYMOUS_USER_ID,
    GUEST_USER_ID_PREFIX,
    SYSTEM_COMPANY_ID,
    AuthCodeCache,
    AuthProvider,
    AuthRequest,
    AuthState,
    NamespaceAutomationRule,
    NamespaceCRMSettings,
    NamespaceKind,
    NamespaceSyncSettings,
    ProviderUserInfo,
    SidebarNavEntry,
    SuggestsSettings,
    UserStatus,
    is_platform_user_id,
)
from core.models.identity_models.namespace import (
    Namespace,
)
from core.models.identity_models.user import (
    User,
)
from core.models.identity_models.user_badge import (
    UserBadge,
)
from core.models.identity_models.user_provider_record import (
    UserProviderRecord,
)

__all__ = [
    "AuthResult",
    "AuthSession",
    "Company",
    "UserStatus",
    "AuthProvider",
    "is_platform_user_id",
    "ProviderUserInfo",
    "AuthRequest",
    "AuthState",
    "GUEST_USER_ID_PREFIX",
    "ANONYMOUS_USER_ID",
    "AuthCodeCache",
    "SidebarNavEntry",
    "NamespaceAutomationRule",
    "SYSTEM_COMPANY_ID",
    "SuggestsSettings",
    "NamespaceCRMSettings",
    "NamespaceSyncSettings",
    "NamespaceKind",
    "Namespace",
    "User",
    "UserBadge",
    "UserProviderRecord",
]
