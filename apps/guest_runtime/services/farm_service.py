"""Оркестрация build / lease / A2A invoke фермы code_agent."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

from apps.guest_runtime.db.repository import GuestRuntimeRepository
from apps.guest_runtime.services.deny import assert_source_allowed
from apps.guest_runtime.services.lease_store import GuestLeaseStore
from apps.guest_runtime.services.slots import (
    GuestSlot,
    build_docker_image,
    compute_source_digest,
    docker_image_inspect,
    docker_image_tag,
    extra_hosts_for_urls,
    maybe_delete_docker_image,
    restore_docker_slot,
    restore_inprocess_slot,
    rewrite_loopback_url,
    start_docker_slot,
    start_inprocess_slot,
    stop_slot,
)
from core.billing import get_billing_service
from core.billing.service import BALANCE_BLOCK_OPERATION_GUEST_RUNTIME
from core.capabilities.models import CapabilityExecutionContext
from core.clients.files_client import FilesClient
from core.config import get_settings
from core.config.models import GuestRuntimeFarmConfig
from core.errors.boundary import PlatformNotFoundError
from core.guest_runtime.billing import (
    trace_guest_build_usage,
    trace_guest_session_usage,
    trace_guest_start,
)
from core.guest_runtime.env import resolve_idle_ttl_seconds, validate_guest_env
from core.guest_runtime.models import (
    CodeAgentSourceFile,
    GuestBuildBusyError,
    GuestBuildStatus,
    GuestEnsureLeaseRequest,
    GuestEnsureLeaseResponse,
    GuestExecutorKind,
    GuestInvokeKind,
    GuestLease,
    GuestLeaseCapError,
    GuestLogLine,
    GuestRebuildRequest,
    GuestRebuildResponse,
    GuestRuntime,
    GuestRuntimeLogsResponse,
    GuestRuntimeStatusResponse,
)
from core.logging import get_logger
from core.logging.attributes import (
    LOG_CONTEXT_ID,
    LOG_FLOW_ID,
    LOG_GUEST_LEASE_ID,
    LOG_GUEST_RUNTIME_ID,
    LOG_NODE_ID,
    LOG_REQUEST_ID,
    LOG_SESSION_AGENT,
    LOG_TASK_ID,
    LOG_TRACE_ID,
)
from core.test_scope import resolve_test_scope
from core.types import (
    JsonObject,
    parse_json_object,
    parse_json_value,
    require_json_object,
    require_json_value,
)
from core.utils.background import run_with_log_context

logger = get_logger(__name__)


class GuestFarmService:
    def __init__(
        self,
        *,
        repository: GuestRuntimeRepository,
        lease_store: GuestLeaseStore,
        files_client: FilesClient,
        farm: GuestRuntimeFarmConfig,
    ) -> None:
        self._repository: GuestRuntimeRepository = repository
        self._leases: GuestLeaseStore = lease_store
        self._files: FilesClient = files_client
        self._farm_config: GuestRuntimeFarmConfig = farm
        self._slots: dict[str, GuestSlot] = {}

    @property
    def farm_config(self) -> GuestRuntimeFarmConfig:
        return self._farm_config

    async def rebuild(self, body: GuestRebuildRequest) -> GuestRebuildResponse:
        runtime = await self._build_image(body)
        if runtime.image_digest is None:
            raise RuntimeError("guest rebuild did not produce image_digest")
        if runtime.image_bytes is None:
            raise RuntimeError("guest rebuild did not produce image_bytes")
        return GuestRebuildResponse(
            guest_runtime_id=runtime.guest_runtime_id,
            image_digest=runtime.image_digest,
            image_bytes=runtime.image_bytes,
            build_status=runtime.build_status,
        )

    async def ensure_lease(self, body: GuestEnsureLeaseRequest) -> GuestEnsureLeaseResponse:
        farm = self._farm_config
        slot_lock = await self._leases.acquire_slot_lock(
            body.flow_id,
            body.node_id,
            ttl_seconds=farm.max_lifetime_seconds,
        )
        if not slot_lock:
            raise GuestBuildBusyError("guest lease ensure already running for this node")
        try:
            return await self._ensure_lease_locked(body)
        finally:
            await self._leases.release_slot_lock(body.flow_id, body.node_id)

    async def _ensure_lease_locked(
        self, body: GuestEnsureLeaseRequest
    ) -> GuestEnsureLeaseResponse:
        farm = self._farm_config
        await get_billing_service().require_balance_for_billable_operation(
            body.company_id,
            body.user_id,
            operation_code=BALANCE_BLOCK_OPERATION_GUEST_RUNTIME,
            notification_service="flows",
        )
        existing = await self._leases.get(body.flow_id, body.node_id)
        runtime = await self._build_image(
            GuestRebuildRequest(
                flow_id=body.flow_id,
                node_id=body.node_id,
                company_id=body.company_id,
                user_id=body.user_id,
                catalog_id=body.catalog_id,
                language=body.language,
                invoke_kind=body.invoke_kind,
                invoke_argv=body.invoke_argv,
                invoke_listen_port=body.invoke_listen_port,
                egress_hosts=body.egress_hosts,
                files=body.files,
            )
        )
        if runtime.image_digest is None:
            raise RuntimeError("guest runtime has no image_digest after build")
        if existing is not None and existing.image_digest == runtime.image_digest:
            slot = await self._live_or_recreate_slot(existing, runtime, body)
            self._slots[existing.guest_lease_id] = slot
            existing.shim_url = slot.shim_url
            existing.process_id = slot.process_id
            existing.container_id = slot.container_id
            existing.executor = slot.executor
            existing.idle_ttl_seconds = self._idle_ttl(body)
            existing.invoke_kind = body.invoke_kind
            existing.invoke_argv = list(body.invoke_argv)
            existing.invoke_listen_port = body.invoke_listen_port
            await self._push_context(slot, body, existing, runtime)
            ttl = self._leases.remaining_ttl(existing)
            await self._leases.put_existing(existing, ttl_seconds=ttl)
            return GuestEnsureLeaseResponse(
                guest_lease_id=existing.guest_lease_id,
                a2a_url=self.a2a_url(body.flow_id, body.node_id),
                image_digest=runtime.image_digest,
            )
        if existing is not None:
            await self._stop_lease(existing)
        slot = await self._start_slot(runtime, body)
        now = datetime.now(timezone.utc)
        lease = GuestLease(
            guest_lease_id=str(uuid.uuid4()),
            company_id=body.company_id,
            user_id=body.user_id,
            flow_id=body.flow_id,
            node_id=body.node_id,
            image_digest=runtime.image_digest,
            invoke_kind=body.invoke_kind,
            invoke_argv=list(body.invoke_argv),
            invoke_listen_port=body.invoke_listen_port,
            started_at=now,
            last_completed_at=None,
            in_flight=0,
            idle_ttl_seconds=self._idle_ttl(body),
            executor=slot.executor,
            shim_url=slot.shim_url,
            process_id=slot.process_id,
            container_id=slot.container_id,
        )
        try:
            await self._leases.acquire_new(lease, ttl_seconds=self._leases.remaining_ttl(lease))
        except GuestLeaseCapError:
            await stop_slot(slot)
            raise
        _ = await self._leases.incr_image_ref(
            lease.image_digest, ttl_seconds=farm.max_lifetime_seconds * 24
        )
        self._slots[lease.guest_lease_id] = slot
        self._start_log_drain(slot, body.flow_id, body.node_id)
        await self._push_context(slot, body, lease, runtime)
        await trace_guest_start(
            company_id=body.company_id,
            user_id=body.user_id,
            flow_id=body.flow_id,
            node_id=body.node_id,
        )
        logger.info(
            "guest.lease.acquired",
            **{
                LOG_FLOW_ID: body.flow_id,
                LOG_GUEST_RUNTIME_ID: runtime.guest_runtime_id,
                LOG_GUEST_LEASE_ID: lease.guest_lease_id,
            },
        )
        return GuestEnsureLeaseResponse(
            guest_lease_id=lease.guest_lease_id,
            a2a_url=self.a2a_url(body.flow_id, body.node_id),
            image_digest=runtime.image_digest,
        )

    async def get_lease(self, flow_id: str, node_id: str) -> GuestLease | None:
        return await self._leases.get(flow_id, node_id)

    async def status(self, flow_id: str, node_id: str) -> GuestRuntimeStatusResponse:
        runtime_id = GuestRuntimeRepository.runtime_id(flow_id, node_id)
        runtime = await self._repository.get(runtime_id)
        lease = await self._leases.get(flow_id, node_id)
        return GuestRuntimeStatusResponse(runtime=runtime, lease=lease)

    async def logs(
        self,
        flow_id: str,
        node_id: str,
        *,
        task_id: str | None = None,
        session_id: str | None = None,
        context_id: str | None = None,
    ) -> GuestRuntimeLogsResponse:
        items = await self._leases.list_logs(flow_id, node_id)
        filtered = [
            line
            for line in items
            if _log_line_matches(
                line,
                task_id=task_id,
                session_id=session_id,
                context_id=context_id,
            )
        ]
        return GuestRuntimeLogsResponse(items=filtered)

    async def drop_runtime(self, flow_id: str, node_id: str) -> None:
        lease = await self._leases.get(flow_id, node_id)
        if lease is not None:
            await self._stop_lease(lease)
        runtime_id = GuestRuntimeRepository.runtime_id(flow_id, node_id)
        runtime = await self._repository.get(runtime_id)
        if runtime is None:
            return
        if lease is None and runtime.image_digest is not None:
            await maybe_delete_docker_image(
                runtime.image_digest, GuestExecutorKind(self._farm_config.executor)
            )
        deleted = await self._repository.delete(runtime_id)
        if not deleted:
            raise RuntimeError(f"failed to delete GuestRuntime {runtime_id}")

    async def invoke_a2a(
        self,
        flow_id: str,
        node_id: str,
        rpc: JsonObject,
    ) -> JsonObject:
        method = rpc.get("method")
        if method == "SendMessage":
            return await self._send_message(flow_id, node_id, rpc)
        if method == "GetTask":
            return await self._get_task(rpc)
        raise ValueError(f"unsupported A2A method: {method!r}")

    async def reap(self) -> None:
        farm = self._farm_config
        now = datetime.now(timezone.utc)
        for lease in await self._leases.list_all():
            lifetime = (now - lease.started_at).total_seconds()
            if lifetime >= farm.max_lifetime_seconds:
                await self._expire_lease(lease, reason="max_lifetime")
                continue
            if lease.in_flight > 0:
                continue
            if lease.last_completed_at is None:
                idle = (now - lease.started_at).total_seconds()
            else:
                idle = (now - lease.last_completed_at).total_seconds()
            if idle >= lease.idle_ttl_seconds:
                await self._expire_lease(lease, reason="idle")
        await self._leases.rebuild_counts()

    def a2a_url(self, flow_id: str, node_id: str) -> str:
        base = get_settings().server.get_service_url("guest_runtime").rstrip("/")
        return f"{base}/guest-runtime/api/v1/a2a/{flow_id}/{node_id}"

    async def _expire_lease(self, lease: GuestLease, *, reason: str) -> None:
        logger.info(
            "guest.lease.expired",
            reason=reason,
            **{LOG_GUEST_LEASE_ID: lease.guest_lease_id, LOG_FLOW_ID: lease.flow_id},
        )
        await self._stop_lease(lease)

    async def _stop_lease(self, lease: GuestLease) -> None:
        lifetime_seconds = max(
            1,
            int((datetime.now(timezone.utc) - lease.started_at).total_seconds()),
        )
        await trace_guest_session_usage(
            company_id=lease.company_id,
            user_id=lease.user_id,
            flow_id=lease.flow_id,
            node_id=lease.node_id,
            lifetime_seconds=lifetime_seconds,
        )
        slot = self._slots.pop(lease.guest_lease_id, None)
        if slot is not None:
            await stop_slot(slot)
        elif lease.executor == GuestExecutorKind.DOCKER and lease.container_id is not None:
            restored = GuestSlot(
                executor=GuestExecutorKind.DOCKER,
                shim_url=lease.shim_url,
                process_id=None,
                container_id=lease.container_id,
            )
            await stop_slot(restored)
        await self._leases.release(lease)
        remaining = await self._leases.decr_image_ref(lease.image_digest)
        if remaining == 0:
            await maybe_delete_docker_image(lease.image_digest, lease.executor)
            logger.info("guest.image.gc", digest=lease.image_digest)

    async def _persist_runtime(self, runtime: GuestRuntime) -> GuestRuntime:
        saved = await self._repository.set(runtime)
        if not saved:
            raise RuntimeError("failed to persist GuestRuntime")
        return runtime

    async def _trace_build_usage(self, body: GuestRebuildRequest, started: datetime) -> None:
        elapsed = max(1, int((datetime.now(timezone.utc) - started).total_seconds()))
        await trace_guest_build_usage(
            company_id=body.company_id,
            user_id=body.user_id,
            flow_id=body.flow_id,
            node_id=body.node_id,
            build_seconds=elapsed,
        )

    async def _build_image(self, body: GuestRebuildRequest) -> GuestRuntime:
        farm = self._farm_config
        if not body.invoke_argv:
            raise ValueError("code_agent invoke_argv is required at runtime")
        total_bytes = sum(item.file_size for item in body.files)
        if total_bytes > farm.max_source_bytes:
            raise ValueError(
                f"code_agent source exceeds {farm.max_source_bytes} bytes: {total_bytes}"
            )
        contents = await self._read_files(body.files)
        assert_source_allowed(body.files, contents)
        digest_hex = compute_source_digest(contents)
        executor = GuestExecutorKind(farm.executor)
        runtime_id = GuestRuntimeRepository.runtime_id(body.flow_id, body.node_id)
        previous = await self._repository.get(runtime_id)
        if executor == GuestExecutorKind.INPROCESS:
            image_digest = f"inprocess:{digest_hex}"
            image_bytes = total_bytes
            if previous is not None and previous.image_digest == image_digest:
                return previous
            started = datetime.now(timezone.utc)
            try:
                await self._assert_company_budget(body.company_id, image_bytes, image_digest)
                now = datetime.now(timezone.utc)
                return await self._persist_runtime(
                    GuestRuntime(
                        guest_runtime_id=runtime_id,
                        flow_id=body.flow_id,
                        node_id=body.node_id,
                        company_id=body.company_id,
                        catalog_id=body.catalog_id,
                        language=body.language,
                        invoke_kind=body.invoke_kind,
                        invoke_argv=list(body.invoke_argv),
                        invoke_listen_port=body.invoke_listen_port,
                        egress_hosts=list(body.egress_hosts),
                        git_url=body.git_url,
                        source_sha=body.source_sha,
                        image_digest=image_digest,
                        image_bytes=image_bytes,
                        build_status=GuestBuildStatus.READY,
                        build_error=None,
                        updated_at=now,
                    )
                )
            finally:
                await self._trace_build_usage(body, started)
        if executor != GuestExecutorKind.DOCKER:
            raise RuntimeError(f"unsupported guest executor: {executor}")
        existing_image = await docker_image_inspect(docker_image_tag(digest_hex))
        if (
            existing_image is not None
            and previous is not None
            and previous.image_digest == existing_image[0]
            and previous.build_status == GuestBuildStatus.READY
        ):
            return previous
        acquired = await self._leases.acquire_build_lock(
            digest_hex, ttl_seconds=farm.max_lifetime_seconds
        )
        if not acquired:
            raise GuestBuildBusyError("guest build already running")
        started = datetime.now(timezone.utc)
        now = datetime.now(timezone.utc)
        building = GuestRuntime(
            guest_runtime_id=runtime_id,
            flow_id=body.flow_id,
            node_id=body.node_id,
            company_id=body.company_id,
            catalog_id=body.catalog_id,
            language=body.language,
            invoke_kind=body.invoke_kind,
            invoke_argv=list(body.invoke_argv),
            invoke_listen_port=body.invoke_listen_port,
            egress_hosts=list(body.egress_hosts),
            git_url=body.git_url,
            source_sha=body.source_sha,
            image_digest=previous.image_digest if previous is not None else None,
            image_bytes=previous.image_bytes if previous is not None else None,
            build_status=GuestBuildStatus.BUILDING,
            build_error=None,
            updated_at=now,
        )
        _ = await self._persist_runtime(building)
        try:
            image_digest, image_bytes = await build_docker_image(
                language=body.language,
                contents=contents,
                data_dir=Path(farm.data_dir),
                flow_id=body.flow_id,
                node_id=body.node_id,
                source_digest_hex=digest_hex,
            )
            if image_bytes > farm.max_image_bytes:
                raise ValueError(
                    f"code_agent image exceeds {farm.max_image_bytes} bytes: {image_bytes}"
                )
            await self._assert_company_budget(body.company_id, image_bytes, image_digest)
            if previous is not None and previous.image_digest == image_digest:
                ready = previous.model_copy(
                    update={
                        "build_status": GuestBuildStatus.READY,
                        "build_error": None,
                        "updated_at": datetime.now(timezone.utc),
                    }
                )
                return await self._persist_runtime(ready)
            ready = building.model_copy(
                update={
                    "image_digest": image_digest,
                    "image_bytes": image_bytes,
                    "build_status": GuestBuildStatus.READY,
                    "build_error": None,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            return await self._persist_runtime(ready)
        except Exception as exc:
            failed = building.model_copy(
                update={
                    "build_status": GuestBuildStatus.FAILED,
                    "build_error": str(exc),
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            _ = await self._persist_runtime(failed)
            raise
        finally:
            await self._leases.release_build_lock()
            await self._trace_build_usage(body, started)

    async def _assert_company_budget(
        self, company_id: str, new_bytes: int, new_digest: str
    ) -> None:
        farm = self._farm_config
        used = 0
        runtimes = await self._repository.list(limit=1000)
        for runtime in runtimes:
            if runtime.company_id != company_id:
                continue
            if runtime.image_digest == new_digest:
                return
            if runtime.image_bytes is not None:
                used += runtime.image_bytes
        if used + new_bytes > farm.company_image_budget_bytes:
            raise ValueError(
                f"company image budget {farm.company_image_budget_bytes} exceeded"
            )

    async def _read_files(self, files: list[CodeAgentSourceFile]) -> dict[str, bytes]:
        contents: dict[str, bytes] = {}
        for item in files:
            payload = await self._files.get_bytes(item.file_id)
            if len(payload) != item.file_size:
                raise ValueError(
                    f"file_size mismatch for {item.relative_path}: declared {item.file_size}, actual {len(payload)}"
                )
            contents[item.relative_path] = payload
        return contents

    async def _live_or_recreate_slot(
        self,
        lease: GuestLease,
        runtime: GuestRuntime,
        body: GuestEnsureLeaseRequest,
    ) -> GuestSlot:
        existing_slot = self._slots.get(lease.guest_lease_id)
        if existing_slot is not None:
            return existing_slot
        if lease.executor == GuestExecutorKind.INPROCESS:
            restored_inprocess = await restore_inprocess_slot(lease)
            if restored_inprocess is not None:
                self._start_log_drain(restored_inprocess, body.flow_id, body.node_id)
                return restored_inprocess
            if lease.process_id is not None:
                try:
                    os.kill(lease.process_id, 15)
                except ProcessLookupError:
                    pass
        if lease.executor == GuestExecutorKind.DOCKER and lease.container_id is not None:
            restored = await restore_docker_slot(lease.container_id)
            if restored is not None:
                self._start_log_drain(restored, body.flow_id, body.node_id)
                return restored
        if lease.executor == GuestExecutorKind.DOCKER and lease.container_id is not None:
            await stop_slot(
                GuestSlot(
                    executor=GuestExecutorKind.DOCKER,
                    shim_url=lease.shim_url,
                    process_id=None,
                    container_id=lease.container_id,
                )
            )
        slot = await self._start_slot(runtime, body)
        self._start_log_drain(slot, body.flow_id, body.node_id)
        return slot

    async def _start_slot(
        self, runtime: GuestRuntime, body: GuestEnsureLeaseRequest
    ) -> GuestSlot:
        farm = self._farm_config
        executor = GuestExecutorKind(farm.executor)
        env = self._guest_env(body, executor)
        data_dir = Path(farm.data_dir)
        contents = await self._read_files(body.files)
        if executor == GuestExecutorKind.INPROCESS:
            return await start_inprocess_slot(
                data_dir=data_dir,
                flow_id=body.flow_id,
                node_id=body.node_id,
                contents=contents,
                env=env,
            )
        if executor == GuestExecutorKind.DOCKER:
            if runtime.image_digest is None:
                raise RuntimeError("image_digest required for docker slot")
            extra_urls = [
                body.llm_proxy_base_url,
                body.capability_gateway_base_url,
                *[f"https://{host}" if "://" not in host else host for host in body.egress_hosts],
            ]
            return await start_docker_slot(
                farm=farm,
                image_digest=runtime.image_digest,
                env=env,
                extra_host_pairs=extra_hosts_for_urls(extra_urls),
            )
        raise RuntimeError(f"unsupported guest executor: {executor}")

    def _guest_env(
        self, body: GuestEnsureLeaseRequest, executor: GuestExecutorKind
    ) -> dict[str, str]:
        if not body.execution_token.strip():
            raise ValueError("execution_token is required")
        if not body.llm_proxy_base_url.strip():
            raise ValueError("llm_proxy_base_url is required")
        if not body.capability_gateway_base_url.strip():
            raise ValueError("capability_gateway_base_url is required")
        path = os.environ.get("PATH")
        if path is None or path.strip() == "":
            raise RuntimeError("PATH is required for guest env")
        llm_url = body.llm_proxy_base_url
        gateway_url = body.capability_gateway_base_url
        env: dict[str, str] = {
            "OPENAI_BASE_URL": llm_url,
            "OPENAI_API_KEY": body.execution_token,
            "CAPABILITY_GATEWAY_URL": gateway_url,
            "PLATFORM_EXECUTION_TOKEN": body.execution_token,
            "PLATFORM_SESSION_ID": body.session_id,
            "PLATFORM_TASK_ID": body.task_id,
            "PLATFORM_CONTEXT_ID": body.context_id,
            "PLATFORM_FLOW_ID": body.flow_id,
            "PLATFORM_NODE_ID": body.node_id,
            "PLATFORM_COMPANY_ID": body.company_id,
            "PLATFORM_USER_ID": body.user_id,
            "PLATFORM_BRANCH_ID": body.branch_id,
            "PLATFORM_CHANNEL": body.channel,
            "PLATFORM_SOURCE_NODE_ID": body.source_node_id,
            "PLATFORM_REQUEST_ID": body.request_id,
            "PLATFORM_TRACE_ID": body.trace_id,
            "PLATFORM_CAPABILITY_CONTEXT": self._capability_context(body).model_dump_json(),
            "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        if body.namespace is not None:
            env["PLATFORM_NAMESPACE"] = body.namespace
        if body.durable_execution_branch_id is not None:
            env["PLATFORM_DURABLE_EXECUTION_BRANCH_ID"] = body.durable_execution_branch_id
        if body.durable_node_schedule_sequence is not None:
            env["PLATFORM_DURABLE_NODE_SCHEDULE_SEQUENCE"] = str(
                body.durable_node_schedule_sequence
            )
        if body.durable_superstep_sequence is not None:
            env["PLATFORM_DURABLE_SUPERSTEP_SEQUENCE"] = str(body.durable_superstep_sequence)
        test_scope = resolve_test_scope()
        if test_scope is not None:
            env["PLATFORM_TEST_SCOPE"] = test_scope
        extra = validate_guest_env(body.guest_env)
        overlap = set(extra).intersection(env)
        if overlap:
            joined = ", ".join(sorted(overlap))
            raise ValueError(f"guest_env overlaps platform env: {joined}")
        env.update(extra)
        if executor == GuestExecutorKind.DOCKER:
            env["OPENAI_BASE_URL"] = rewrite_loopback_url(llm_url)
            env["CAPABILITY_GATEWAY_URL"] = rewrite_loopback_url(gateway_url)
            for key, value in extra.items():
                env[key] = rewrite_loopback_url(value)
            env["PATH"] = (
                "/src/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
            )
            env["HOME"] = "/tmp"
            env["XDG_CACHE_HOME"] = "/tmp"
            return env
        env["PATH"] = path
        home = os.environ.get("HOME")
        if home is not None and home.strip() != "":
            env["HOME"] = home
        lang = os.environ.get("LANG")
        if lang is not None and lang.strip() != "":
            env["LANG"] = lang
        return env

    def _start_log_drain(self, slot: GuestSlot, flow_id: str, node_id: str) -> None:
        stream = None
        if slot.process is not None:
            stream = slot.process.stdout
        elif slot.log_follow is not None:
            stream = slot.log_follow.stdout
        if stream is None:
            return
        slot.drain_task = run_with_log_context(
            self._drain_log_stream(stream, flow_id, node_id, slot),
            name="guest.shim.log_drain",
            background_kind="polling",
        )

    async def _drain_log_stream(
        self,
        stream: asyncio.StreamReader,
        flow_id: str,
        node_id: str,
        slot: GuestSlot,
    ) -> None:
        while True:
            raw = await stream.readline()
            if raw == b"":
                return
            text = raw.decode("utf-8", errors="replace").rstrip("\n")
            await self._ingest_shim_line(flow_id, node_id, text, slot=slot)

    async def _ingest_shim_line(
        self, flow_id: str, node_id: str, text: str, *, slot: GuestSlot
    ) -> None:
        now = datetime.now(timezone.utc)
        try:
            parsed = parse_json_value(text, "guest.shim.line")
        except ValueError:
            line = _guest_log_line(now, event="guest.shim.raw", line=text, parsed=None, slot=slot)
            await self._leases.append_log(flow_id, node_id, line)
            _log_guest_line(flow_id, node_id, line)
            return
        if not isinstance(parsed, dict):
            line = _guest_log_line(now, event="guest.shim.raw", line=text, parsed=None, slot=slot)
            await self._leases.append_log(flow_id, node_id, line)
            _log_guest_line(flow_id, node_id, line)
            return
        event_raw = parsed.get("event")
        event = event_raw if isinstance(event_raw, str) and event_raw.strip() else "guest.shim"
        line = _guest_log_line(
            now,
            event=event,
            line=text,
            parsed=require_json_object(parsed, "guest.shim.line"),
            slot=slot,
        )
        await self._leases.append_log(flow_id, node_id, line)
        _log_guest_line(flow_id, node_id, line)

    async def _append_error_log(
        self, flow_id: str, node_id: str, *, event: str, message: str, slot: GuestSlot
    ) -> None:
        await self._leases.append_log(
            flow_id,
            node_id,
            _guest_log_line(
                datetime.now(timezone.utc),
                event=event,
                line=message,
                parsed=None,
                slot=slot,
            ),
        )

    def _idle_ttl(self, body: GuestEnsureLeaseRequest) -> int:
        return resolve_idle_ttl_seconds(
            body.idle_ttl_seconds,
            farm_idle_ttl_seconds=self._farm_config.idle_ttl_seconds,
            farm_max_lifetime_seconds=self._farm_config.max_lifetime_seconds,
        )

    def _capability_context(self, body: GuestEnsureLeaseRequest) -> CapabilityExecutionContext:
        return CapabilityExecutionContext(
            execution_token=body.execution_token,
            company_id=body.company_id,
            user_id=body.user_id,
            flow_id=body.flow_id,
            branch_id=body.branch_id,
            session_id=body.session_id,
            task_id=body.task_id,
            context_id=body.context_id,
            channel=body.channel,
            request_id=body.request_id,
            trace_id=body.trace_id,
            durable_execution_branch_id=body.durable_execution_branch_id,
            durable_node_schedule_sequence=body.durable_node_schedule_sequence,
            durable_superstep_sequence=body.durable_superstep_sequence,
            source_node_id=body.source_node_id,
            namespace=body.namespace,
        )

    def _bind_slot_log_scope(self, slot: GuestSlot, body: GuestEnsureLeaseRequest) -> None:
        slot.log_task_id = body.task_id
        slot.log_session_id = body.session_id
        slot.log_context_id = body.context_id
        slot.log_request_id = body.request_id
        slot.log_trace_id = body.trace_id

    async def _push_context(
        self,
        slot: GuestSlot,
        body: GuestEnsureLeaseRequest,
        lease: GuestLease,
        runtime: GuestRuntime,
    ) -> None:
        payload: JsonObject = {
            "invoke_kind": GuestInvokeKind(body.invoke_kind).value,
            "invoke_argv": list(body.invoke_argv),
            "invoke_listen_port": body.invoke_listen_port,
            "request_id": body.request_id,
            "trace_id": body.trace_id,
            "session_id": body.session_id,
            "task_id": body.task_id,
            "context_id": body.context_id,
            "flow_id": body.flow_id,
            "guest_runtime_id": runtime.guest_runtime_id,
            "guest_lease_id": lease.guest_lease_id,
            "env": self._guest_env(body, slot.executor),
        }
        self._bind_slot_log_scope(slot, body)
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{slot.shim_url}/context", json=payload)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"guest POST /context failed: {response.status_code} {response.text}"
                )

    async def _send_message(
        self, flow_id: str, node_id: str, rpc: JsonObject
    ) -> JsonObject:
        lease = await self._leases.get(flow_id, node_id)
        if lease is None:
            raise PlatformNotFoundError("guest lease not found", error_code="guest_lease_not_found")
        slot = self._slots.get(lease.guest_lease_id)
        if slot is None:
            raise RuntimeError("guest slot is not running")
        params = require_json_object(rpc.get("params"), "a2a.params")
        text = _extract_message_text(params)
        metadata = _extract_message_metadata(params)
        platform_task_id, platform_context_id = _extract_message_identity(params)
        invoke_task_id = platform_task_id if platform_task_id is not None else slot.log_task_id
        if invoke_task_id is None or invoke_task_id.strip() == "":
            raise ValueError("guest A2A task_id is required")
        invoke_context_id = (
            platform_context_id if platform_context_id is not None else slot.log_session_id
        )
        if invoke_context_id is None or invoke_context_id.strip() == "":
            raise ValueError("guest A2A context_id is required")
        lease.in_flight += 1
        await self._leases.put_existing(
            lease, ttl_seconds=self._leases.remaining_ttl(lease)
        )
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                invoke_body: JsonObject = {"text": text, "metadata": metadata}
                response = await client.post(
                    f"{slot.shim_url}/invoke",
                    json=invoke_body,
                )
            if response.status_code >= 400:
                detail = response.text
                await self._append_error_log(
                    flow_id,
                    node_id,
                    event="guest.invoke.failed",
                    message=detail,
                    slot=slot,
                )
                raise RuntimeError(f"guest invoke failed: {response.status_code} {detail}")
            result_payload = parse_json_object(response.content, "guest.invoke")
        finally:
            if lease.in_flight < 1:
                raise RuntimeError("guest lease in_flight underflow")
            lease.in_flight -= 1
            lease.last_completed_at = datetime.now(timezone.utc)
            await self._leases.put_existing(
                lease, ttl_seconds=self._leases.remaining_ttl(lease)
            )
        task_id = invoke_task_id
        text_out = result_payload.get("text")
        if not isinstance(text_out, str):
            raise ValueError("guest invoke result.text required")
        task: JsonObject = {
            "id": task_id,
            "contextId": invoke_context_id,
            "status": {"state": "TASK_STATE_COMPLETED"},
            "artifacts": [
                {
                    "artifactId": "response",
                    "parts": [{"text": text_out}],
                }
            ],
        }
        effects = result_payload.get("platform_effects")
        artifacts = task["artifacts"]
        if not isinstance(artifacts, list):
            raise RuntimeError("guest task artifacts must be a list")
        if effects is not None:
            artifacts.append(
                {
                    "artifactId": "platform_effects",
                    "parts": [
                        {
                            "data": effects,
                            "metadata": {
                                "mediaType": "application/vnd.platform.effects+json"
                            },
                        }
                    ],
                }
            )
        interrupt = result_payload.get("interrupt")
        if interrupt is not None:
            artifacts.append(
                {
                    "artifactId": "interrupt",
                    "parts": [
                        {
                            "data": interrupt,
                            "metadata": {
                                "mediaType": "application/vnd.platform.interrupt+json"
                            },
                        }
                    ],
                }
            )
        guest_state = _guest_state_from_invoke(result_payload)
        if guest_state:
            artifacts.append(
                {
                    "artifactId": "state",
                    "parts": [
                        {
                            "data": guest_state,
                            "metadata": {"mediaType": "application/json"},
                        }
                    ],
                }
            )
        await self._leases.store_task(
            task_id,
            json.dumps(task, ensure_ascii=False),
            ttl_seconds=self._farm_config.max_lifetime_seconds,
        )
        return {
            "jsonrpc": "2.0",
            "id": rpc.get("id"),
            "result": task,
        }

    async def _get_task(self, rpc: JsonObject) -> JsonObject:
        params = require_json_object(rpc.get("params"), "a2a.params")
        task_id = params.get("id")
        if not isinstance(task_id, str) or task_id.strip() == "":
            raise ValueError("GetTask id is required")
        raw = await self._leases.get_task(task_id.strip())
        if raw is None:
            raise PlatformNotFoundError("task not found", error_code="guest_task_not_found")
        task = parse_json_object(raw, "guest.task")
        return {"jsonrpc": "2.0", "id": rpc.get("id"), "result": task}


def _extract_message_text(params: JsonObject) -> str:
    message = params.get("message")
    if not isinstance(message, dict):
        raise ValueError("SendMessage params.message required")
    parts = message.get("parts")
    if not isinstance(parts, list):
        raise ValueError("SendMessage parts required")
    chunks: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            raise ValueError("SendMessage part must be an object")
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            chunks.append(text)
    if not chunks:
        raise ValueError("SendMessage requires a text part")
    return "\n".join(chunks)


def _extract_message_metadata(params: JsonObject) -> JsonObject:
    raw = params.get("metadata")
    if raw is None:
        message = params.get("message")
        if isinstance(message, dict):
            raw = message.get("metadata")
    if raw is None:
        return {}
    return require_json_object(raw, "SendMessage.metadata")


def _guest_state_from_invoke(result_payload: JsonObject) -> JsonObject:
    reserved = {"text", "platform_effects", "interrupt", "state"}
    extras: JsonObject = {}
    for key, value in result_payload.items():
        if key in reserved:
            continue
        extras[key] = require_json_value(value, f"guest.invoke.{key}")
    raw_state = result_payload.get("state")
    if raw_state is None:
        return extras
    state_obj = require_json_object(raw_state, "guest.invoke.state")
    overlap = set(state_obj).intersection(extras)
    if overlap:
        joined = ", ".join(sorted(overlap))
        raise ValueError(f"guest invoke state overlaps extra keys: {joined}")
    merged = dict(state_obj)
    merged.update(extras)
    return merged


def _extract_message_identity(params: JsonObject) -> tuple[str | None, str | None]:
    message = params.get("message")
    if not isinstance(message, dict):
        raise ValueError("SendMessage params.message required")
    task_raw = message.get("taskId")
    context_raw = message.get("contextId")
    task_id = task_raw if isinstance(task_raw, str) and task_raw.strip() else None
    context_id = context_raw if isinstance(context_raw, str) and context_raw.strip() else None
    return task_id, context_id


def _optional_log_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _require_filter_id(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if stripped == "":
        raise ValueError(f"{field} must be non-empty when provided")
    return stripped


def _log_line_matches(
    line: GuestLogLine,
    *,
    task_id: str | None,
    session_id: str | None,
    context_id: str | None,
) -> bool:
    want_task = _require_filter_id(task_id, "task_id")
    want_session = _require_filter_id(session_id, "session_id")
    want_context = _require_filter_id(context_id, "context_id")
    if want_task is not None and line.task_id != want_task:
        return False
    if want_session is not None and line.session_id != want_session:
        return False
    if want_context is not None and line.context_id != want_context:
        return False
    return True


def _guest_log_line(
    now: datetime,
    *,
    event: str,
    line: str,
    parsed: JsonObject | None,
    slot: GuestSlot,
) -> GuestLogLine:
    task_id = slot.log_task_id
    session_id = slot.log_session_id
    context_id = slot.log_context_id
    request_id = slot.log_request_id
    trace_id = slot.log_trace_id
    if parsed is not None:
        parsed_task = _optional_log_str(parsed.get("task.id"))
        if parsed_task is None:
            parsed_task = _optional_log_str(parsed.get("task_id"))
        if parsed_task is not None:
            task_id = parsed_task
        parsed_session = _optional_log_str(parsed.get("session_agent"))
        if parsed_session is None:
            parsed_session = _optional_log_str(parsed.get("session_id"))
        if parsed_session is not None:
            session_id = parsed_session
        parsed_context = _optional_log_str(parsed.get("context_id"))
        if parsed_context is not None:
            context_id = parsed_context
        parsed_request = _optional_log_str(parsed.get("request_id"))
        if parsed_request is not None:
            request_id = parsed_request
        parsed_trace = _optional_log_str(parsed.get("trace_id"))
        if parsed_trace is not None:
            trace_id = parsed_trace
    return GuestLogLine(
        ts=now,
        event=event,
        line=line,
        request_id=request_id,
        trace_id=trace_id,
        task_id=task_id,
        session_id=session_id,
        context_id=context_id,
    )


def _log_guest_line(flow_id: str, node_id: str, line: GuestLogLine) -> None:
    fields: dict[str, str] = {
        LOG_FLOW_ID: flow_id,
        LOG_NODE_ID: node_id,
    }
    if line.request_id is not None:
        fields[LOG_REQUEST_ID] = line.request_id
    if line.trace_id is not None:
        fields[LOG_TRACE_ID] = line.trace_id
    if line.task_id is not None:
        fields[LOG_TASK_ID] = line.task_id
    if line.session_id is not None:
        fields[LOG_SESSION_AGENT] = line.session_id
    if line.context_id is not None:
        fields[LOG_CONTEXT_ID] = line.context_id
    logger.info(line.event, **fields)
