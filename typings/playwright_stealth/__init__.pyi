from playwright.async_api import BrowserContext, Page

class Stealth:
    def __init__(
        self,
        *,
        chrome_app: bool = ...,
        chrome_csi: bool = ...,
        chrome_load_times: bool = ...,
        chrome_runtime: bool = ...,
        hairline: bool = ...,
        iframe_content_window: bool = ...,
        media_codecs: bool = ...,
        navigator_hardware_concurrency: bool = ...,
        navigator_languages: bool = ...,
        navigator_permissions: bool = ...,
        navigator_platform: bool = ...,
        navigator_plugins: bool = ...,
        navigator_user_agent: bool = ...,
        navigator_user_agent_data: bool = ...,
        navigator_vendor: bool = ...,
        navigator_webdriver: bool = ...,
        error_prototype: bool = ...,
        sec_ch_ua: bool = ...,
        webgl_vendor: bool = ...,
        navigator_languages_override: tuple[str, str] = ...,
        navigator_platform_override: str = ...,
        navigator_user_agent_override: str | None = ...,
        navigator_vendor_override: str | None = ...,
        sec_ch_ua_override: str | None = ...,
        webgl_renderer_override: str | None = ...,
        webgl_vendor_override: str | None = ...,
        init_scripts_only: bool = ...,
        script_logging: bool = ...,
    ) -> None: ...

    async def apply_stealth_async(self, page_or_context: Page | BrowserContext) -> None: ...
