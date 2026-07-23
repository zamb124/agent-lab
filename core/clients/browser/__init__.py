"""
Контракты Browser Runtime, общие для apps/browser (сервер) и peer-клиентов.
Живут в core/, чтобы core/clients и другие сервисы не импортировали apps/browser
(нарушение границы core/ → apps/ в architecture.mdc).
"""

from core.clients.browser.crawl_fetch_types import (
    BrowserCrawlFetchRequest,
    BrowserCrawlFetchResponse,
)
from core.clients.browser.mcp_contracts import (
    ToolCloseSessionArgs,
    ToolCreateSessionArgs,
    ToolNavigateArgs,
    ToolObserveArgs,
    ToolSaveStateArgs,
)

__all__ = [
    "BrowserCrawlFetchRequest",
    "BrowserCrawlFetchResponse",
    "ToolCloseSessionArgs",
    "ToolCreateSessionArgs",
    "ToolNavigateArgs",
    "ToolObserveArgs",
    "ToolSaveStateArgs",
]
