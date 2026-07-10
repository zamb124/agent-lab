"""Статический контракт кода: чтения/записи state и ключи возврата.

Единый канон анализа пользовательского кода `code_node`/inline tool на предмет
того, какие поля `state` он читает и пишет, и какие ключи возвращает. Знание
языков живёт здесь один раз; `code_runner_*` отдают этот же контракт через
`POST /analyze`, а data-flow инспектор flows использует его in-process.
"""

from core.code_contract.models import (
    CodeContract,
    CodeContractAnalyzeRequest,
    CodeContractAnalyzeResponse,
)
from core.code_contract.scanner import scan_code_contract

__all__ = [
    "CodeContract",
    "CodeContractAnalyzeRequest",
    "CodeContractAnalyzeResponse",
    "scan_code_contract",
]
