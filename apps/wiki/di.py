"""DI процесса wiki: страницы базы знаний внутри namespace."""

from typing import Annotated

from apps.wiki.services.wiki_service import WikiService
from core.di import http_di, task_di
from core.di.platform import PlatformDi


class WikiDi(PlatformDi):
    wiki_service: WikiService


Di = Annotated[WikiDi, http_di(WikiDi), task_di(WikiDi)]
