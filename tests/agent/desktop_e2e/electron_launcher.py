"""Запуск собранного HumanitecAgent/LinnexAgent и prod-path deep links."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from httpx import AsyncClient

from tests.agent._helpers import AGENT_API_PREFIX
from tests.agent.desktop_e2e.desktop_app import HumanitecDesktopInstall

DEFAULT_DEBUG_PORT = 9333
# Fail-fast: pytest desktop_e2e timeout = 15s; внутренние ожидания короче.
_DESKTOP_WAIT_SECONDS = 10.0
# GUI Electron на macOS часто стартует без /opt/homebrew/bin — developer shell
# не видит rg/python3 из Homebrew. Продуктовый PATH для goosed shell.
_DESKTOP_PATH_PREFIXES = (
    "/opt/homebrew/bin",
    "/opt/homebrew/sbin",
    "/usr/local/bin",
    "/usr/local/sbin",
)


def _desktop_shell_path(existing: str | None) -> str:
    parts: list[str] = []
    for prefix in _DESKTOP_PATH_PREFIXES:
        if prefix not in parts:
            parts.append(prefix)
    if existing:
        for chunk in existing.split(":"):
            if chunk and chunk not in parts:
                parts.append(chunk)
    return ":".join(parts)


def _available_debug_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        if not isinstance(port, int) or port <= 0:
            raise RuntimeError(f"invalid ephemeral debug port: {port!r}")
        return port


@dataclass(frozen=True)
class HumanitecDesktopLaunchConfig:
    frontend_base_url: str
    install: HumanitecDesktopInstall
    remote_debugging_port: int = DEFAULT_DEBUG_PORT
    startup_timeout_seconds: float = _DESKTOP_WAIT_SECONDS
    tunnel_online_timeout_seconds: float = _DESKTOP_WAIT_SECONDS


class HumanitecDesktopProcess:
    def __init__(self, config: HumanitecDesktopLaunchConfig) -> None:
        self._config = config
        self._user_data_dir = Path(tempfile.mkdtemp(prefix="humanitec-agent-userdata-"))
        self._goose_path_root = self._user_data_dir / "goose"
        self._goose_path_root.mkdir(parents=True, exist_ok=True)
        self._output_path = self._user_data_dir / "desktop-process.log"
        self._output_handle: Any | None = None
        self._process: subprocess.Popen[str] | None = None

    @property
    def user_data_dir(self) -> Path:
        return self._user_data_dir

    @property
    def credentials_path(self) -> Path:
        return self._user_data_dir / "humanitec-agent.json"

    @property
    def remote_debugging_port(self) -> int:
        return self._config.remote_debugging_port

    def start(self) -> None:
        if self._process is not None:
            raise RuntimeError("HumanitecAgent process already started")
        env = os.environ.copy()
        env["HUMANITEC_FRONTEND_BASE_URL"] = self._config.frontend_base_url
        env["HUMANITEC_DEV_PROBE"] = "1"
        env["GOOSE_PATH_ROOT"] = str(self._goose_path_root)
        env["GOOSE_ENABLE_DIRECT_TOOL_CALL"] = "1"
        env["HUMANITEC_REVOCATION_POLL_INTERVAL_MS"] = "500"
        env["HUMANITEC_ENABLE_TEST_DEEP_LINK"] = "1"
        # macOS GUI apps get a stripped PATH; developer shell expects brew tools (rg).
        env["PATH"] = _desktop_shell_path(env.get("PATH"))
        self._output_handle = self._output_path.open("w", encoding="utf-8")
        command = [
            str(self._config.install.executable),
            f"--user-data-dir={self._user_data_dir}",
            f"--remote-debugging-port={self._config.remote_debugging_port}",
            f"--humanitec-frontend-base-url={self._config.frontend_base_url}",
            "--no-sandbox",
        ]
        self._process = subprocess.Popen(
            command,
            env=env,
            stdout=self._output_handle,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        deadline = time.monotonic() + self._config.startup_timeout_seconds
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                output = self._read_process_output()
                raise RuntimeError(f"HumanitecAgent exited early: {output}")
            if self._remote_debugging_ready() and self._has_page_target():
                return
            time.sleep(0.2)
        raise TimeoutError(
            f"HumanitecAgent did not open remote debugging page target on port "
            f"{self._config.remote_debugging_port} within "
            f"{self._config.startup_timeout_seconds}s\n"
            f"output:\n{self._read_process_output()}"
        )

    def stop(self, *, cleanup_user_data: bool = True) -> None:
        """Останавливает процесс. `cleanup_user_data=False` — для restart-сценариев,
        где persisted-состояние (goose config) должно переживать перезапуск."""
        process = self._process
        self._process = None
        if process is not None and process.poll() is None:
            self._kill_process_tree(process)
        if self._output_handle is not None:
            self._output_handle.close()
            self._output_handle = None
        if cleanup_user_data and self._user_data_dir.is_dir():
            shutil.rmtree(self._user_data_dir, ignore_errors=True)

    def _kill_process_tree(self, process: subprocess.Popen[str]) -> None:
        pid = process.pid
        if pid is None:
            return
        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            try:
                process.kill()
            except ProcessLookupError:
                return
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass

    def open_deep_link(self, url: str) -> None:
        system = platform.system()
        if system == "Darwin":
            # Уже запущенный экземпляр с тестовым user-data-dir; `open -a` поднимает
            # другой процесс без нашего --user-data-dir / CDP.
            completed = subprocess.run(
                ["open", url],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"open deep link failed: {completed.stderr or completed.stdout}"
                )
            return
        if system == "Linux":
            opener = shutil.which("xdg-open")
            if opener is None:
                raise FileNotFoundError("xdg-open is required for deep links on Linux")
            completed = subprocess.run(
                [opener, url],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"xdg-open deep link failed: {completed.stderr or completed.stdout}"
                )
            return
        raise RuntimeError(f"deep links are not supported on host OS: {system}")

    async def handle_deep_link_in_test_instance(self, url: str) -> None:
        from playwright.async_api import async_playwright

        playwright = await async_playwright().start()
        try:
            browser = await playwright.chromium.connect_over_cdp(
                f"http://127.0.0.1:{self.remote_debugging_port}"
            )
            deadline = time.monotonic() + self._config.startup_timeout_seconds
            while time.monotonic() < deadline:
                for context in browser.contexts:
                    for page in context.pages:
                        handled = await page.evaluate(
                            """
                            async (deepLinkUrl) => {
                              const api = window.humanitecAgent;
                              if (!api || typeof api.handleDeepLinkForTest !== 'function') {
                                return false;
                              }
                              await api.handleDeepLinkForTest(deepLinkUrl);
                              return true;
                            }
                            """,
                            url,
                        )
                        if handled is True:
                            return
                await asyncio.sleep(0.2)
        finally:
            await playwright.stop()
        raise TimeoutError("HumanitecAgent test deep-link dispatcher not available")

    def _protocol_url(self, path_and_query: str) -> str:
        scheme = self._config.install.protocol_scheme
        if not scheme:
            raise ValueError("protocol_scheme is required on desktop install")
        return f"{scheme}://{path_and_query.lstrip('/')}"

    def pair_via_deep_link(self, pairing_code: str) -> None:
        if len(pairing_code) != 6 or not pairing_code.isdigit():
            raise ValueError(f"pairing code must be 6 digits, got {pairing_code!r}")
        self.open_deep_link(self._protocol_url(f"pairing?code={pairing_code}"))

    async def pair_via_test_deep_link(self, pairing_code: str) -> None:
        if len(pairing_code) != 6 or not pairing_code.isdigit():
            raise ValueError(f"pairing code must be 6 digits, got {pairing_code!r}")
        await self.handle_deep_link_in_test_instance(
            self._protocol_url(f"pairing?code={pairing_code}")
        )

    def auth_via_deep_link(self, token: str) -> None:
        if not token:
            raise ValueError("auth token is required")
        self.open_deep_link(self._protocol_url(f"auth/callback?token={token}"))

    async def auth_via_test_deep_link(self, token: str) -> None:
        if not token:
            raise ValueError("auth token is required")
        await self.handle_deep_link_in_test_instance(
            self._protocol_url(f"auth/callback?token={token}")
        )

    def open_pairing_ui_deep_link(self) -> None:
        self.open_deep_link(self._protocol_url("pairing"))

    def wait_for_credentials(self, timeout_seconds: float = _DESKTOP_WAIT_SECONDS) -> dict[str, str]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self.credentials_path.is_file():
                return self.read_credentials()
            if self._process is not None and self._process.poll() is not None:
                output = self._read_process_output()
                raise RuntimeError(f"HumanitecAgent exited before pairing: {output}")
            time.sleep(0.25)
        raise TimeoutError(
            f"HumanitecAgent credentials not written within {timeout_seconds}s: "
            f"{self.credentials_path}\noutput:\n{self._read_process_output()}"
        )

    def wait_for_credentials_cleared(
        self,
        timeout_seconds: float = _DESKTOP_WAIT_SECONDS,
    ) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if not self.credentials_path.is_file():
                return
            time.sleep(0.25)
        raise TimeoutError(
            f"HumanitecAgent credentials still present after revoke: {self.credentials_path}"
        )

    def read_credentials(self) -> dict[str, str]:
        if not self.credentials_path.is_file():
            raise FileNotFoundError(f"credentials missing: {self.credentials_path}")
        payload = json.loads(self.credentials_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("humanitec-agent.json must be object")
        credentials: dict[str, str] = {}
        for key, value in payload.items():
            if isinstance(value, str):
                credentials[str(key)] = value
        return credentials

    async def wait_for_tunnel_online(
        self,
        http_client: AsyncClient,
        device_id: str,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + self._config.tunnel_online_timeout_seconds
        last_items: list[dict[str, Any]] = []
        while time.monotonic() < deadline:
            response = await http_client.get(f"{AGENT_API_PREFIX}/devices")
            response.raise_for_status()
            payload = response.json()
            items = payload["items"]
            if not isinstance(items, list):
                raise ValueError("devices list response items must be list")
            last_items = [item for item in items if isinstance(item, dict)]
            matched = next(
                (item for item in last_items if item.get("device_id") == device_id),
                None,
            )
            if matched is not None and matched.get("is_tunnel_online") is True:
                return matched
            await asyncio.sleep(0.5)
        raise TimeoutError(
            f"device {device_id!r} tunnel did not become online; last devices={last_items!r}"
        )

    def _remote_debugging_ready(self) -> bool:
        url = f"http://127.0.0.1:{self._config.remote_debugging_port}/json/version"
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                return response.status == 200
        except (urllib.error.URLError, TimeoutError):
            return False

    def _has_page_target(self) -> bool:
        url = f"http://127.0.0.1:{self._config.remote_debugging_port}/json/list"
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return False
        if not isinstance(payload, list):
            return False
        return any(
            isinstance(target, dict) and target.get("type") == "page"
            for target in payload
        )

    def _read_process_output(self) -> str:
        if self._output_handle is not None:
            self._output_handle.flush()
        if not self._output_path.is_file():
            return ""
        return self._output_path.read_text(encoding="utf-8", errors="replace")
