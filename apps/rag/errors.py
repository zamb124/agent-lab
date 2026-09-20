"""Ошибки границы RAG: без HTTPException, чтобы REST и WS звали один `op_*`."""


class RagAccessDeniedError(PermissionError):
    """Нет сессии, компании или FGA view на namespace."""


class RagNotFoundError(LookupError):
    """Namespace или документ не найден после успешного Check."""
