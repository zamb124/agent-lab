"""Crawl pipeline errors."""


class CrawlExtractTooShortError(ValueError):
    """Extracted page text is below configured min_extract_chars."""

    url: str

    def __init__(self, url: str) -> None:
        super().__init__(f"extracted text too short for url: {url}")
        self.url = url


class CrawlNoExtractableContentError(ValueError):
    """HTML-страница не содержит извлекаемого текста."""

    url: str

    def __init__(self, url: str) -> None:
        super().__init__(f"no extractable content for url: {url}")
        self.url = url
