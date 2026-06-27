"""Запуск собранного HumanitecAgent и prod-path deep links."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from httpx import AsyncClient

from tests.agent._helpers import AGENT_API_PREFIX
from tests.agent.desktop_e2e.desktop_app import HumanitecDesktopInstall

DEFAULT_DEBUG_PORT = 9333


@dataclass(frozen=True)
class HumanitecDesktopLaunchConfig:
    frontend_base_url: str
    install: HumanitecDesktopInstall
    remote_debugging_port: int = DEFAULT_DEBUG_PORT
    startup_timeout_seconds: float = 120.0
    tunnel_online_timeout_seconds: float = 60.0


class HumanitecDesktopProcess:
    def __init__(self, config: HumanitecDesktopLaunchConfig) -> None:
        self._config = config
        self._user_data_dir = Path(tempfile.mkdtemp(prefix="humanitec-agent-userdata-"))
        self._process: subprocess.Popen[str] | None = None
        self._stdout_lines: list[str] = []

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
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.monotonic() + self._config.startup_timeout_seconds
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                output = self._read_process_output()
                raise RuntimeError(f"HumanitecAgent exited early: {output}")
            if self._remote_debugging_ready():
                return
            time.sleep(0.5)
        raise TimeoutError(
            f"HumanitecAgent did not open remote debugging port "
            f"{self._config.remote_debugging_port} within "
            f"{self._config.startup_timeout_seconds}s"
        )

    def stop(self) -> None:
        if self._process is None:
            return
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=10)
        self._process = None
        if self._user_data_dir.is_dir():
            shutil.rmtree(self._user_data_dir, ignore_errors=True)

    def open_deep_link(self, url: str) -> None:
        system = platform.system()
        if system == "Darwin":
            app_bundle = (
                self._config.install.install_root
                / f"{self._config.install.bundle_name}.app"
            )
            if not app_bundle.is_dir():
                raise FileNotFoundError(
                    f"HumanitecAgent app bundle missing for deep link: {app_bundle}"
                )
            completed = subprocess.run(
                ["open", "-a", str(app_bundle), url],
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

    def pair_via_deep_link(self, pairing_code: str) -> None:
        if len(pairing_code) != 6 or not pairing_code.isdigit():
            raise ValueError(f"pairing code must be 6 digits, got {pairing_code!r}")
        self.open_deep_link(f"humanitec://pairing?code={pairing_code}")

    def auth_via_deep_link(self, token: str) -> None:
        if not token:
            raise ValueError("auth token is required")
        self.open_deep_link(f"humanitec://auth/callback?token={token}")

    def open_pairing_ui_deep_link(self) -> None:
        self.open_deep_link("humanitec://pairing")

    def wait_for_credentials(self, timeout_seconds: float = 60.0) -> dict[str, str]:
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
            f"{self.credentials_path}"
        )

    def wait_for_credentials_cleared(self, timeout_seconds: float = 30.0) -> None:
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
        import urllib.error
        import urllib.request

        url = f"http://127.0.0.1:{self._config.remote_debugging_port}/json/version"
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                return response.status == 200
        except (urllib.error.URLError, TimeoutError):
            return False

    def _read_process_output(self) -> str:
        if self._process is None or self._process.stdout is None:
            return ""
        remaining = self._process.stdout.read()
        if remaining:
            self._stdout_lines.extend(remaining.splitlines())
        return "\n".join(self._stdout_lines)
