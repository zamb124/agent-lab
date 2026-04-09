"""
Проигрывает сценарий пользователя CRM по JSON из generate_crm_sales_demo.py:

  1) создаёт заметку (текст из полей записи в JSON);
  2) POST /entities/notes/{note_id}/analyze — анализ (текст берётся из заметки);
  3) POST /entities/notes/{note_id}/apply — применение черновика.

Связи, контакты и прочий граф из файла не создаются: импортируются только записи-встречи
(`entity_type` note и `entity_subtype` meeting), по одной заметке на каждую такую запись.

По умолчанию для всех шагов используется namespace `default` (как у новой компании в CRM).
Иначе: `--namespace <имя>`. Чтобы взять namespace из поля каждой записи JSON: `--use-json-namespace`
(если в строке нет namespace — снова `--namespace` или `default`).

Нужны: CRM с worker (TaskIQ), JWT в CRM_API_TOKEN или --token.
`--base-url` — только хост CRM (например http://127.0.0.1:8003), без лишнего `/crm/...`. POST идёт на `.../crm/api/v1/entities` без завершающего слэша (иначе возможен HTTP 405).

Пайплайны по разным встречам идут параллельно (asyncio + семафор), внутри одной встречи шаги
по-прежнему последовательные. Параметр `--concurrency` задаёт максимум одновременных потоков.

  export CRM_API_TOKEN=...
  uv run python scripts/import_crm_sales_demo.py --json-path demo_sales.json --concurrency 8
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8003"
DEFAULT_JSON_PATH = "demo_sales.json"
DEFAULT_CONCURRENCY = 5
DEFAULT_NAMESPACE = "default"


def _api_root(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/crm/api/v1"


def _note_text(row: dict[str, Any]) -> str:
    parts: list[str] = []
    desc = row.get("description")
    if isinstance(desc, str) and desc.strip():
        parts.append(desc.strip())
    name = row.get("name")
    if isinstance(name, str) and name.strip() and not parts:
        parts.append(name.strip())
    attrs = row.get("attributes")
    if isinstance(attrs, dict):
        for key in ("participants", "decisions"):
            v = attrs.get(key)
            if v:
                parts.append(f"{key}: {v}")
    text = "\n\n".join(parts)
    if not text.strip():
        raise ValueError(f"Нет текста для заметки: logical_id={row.get('logical_id')!r}")
    return text


def _namespace_for_row(
    row: dict[str, Any],
    cli_namespace: str,
    use_json_namespace: bool,
) -> str:
    base = cli_namespace.strip() if cli_namespace.strip() else DEFAULT_NAMESPACE
    if not use_json_namespace:
        return base
    ns = row.get("namespace")
    if isinstance(ns, str) and ns.strip():
        return ns.strip()
    return base


def _iter_meeting_notes(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        e
        for e in entities
        if e.get("entity_type") == "note" and e.get("entity_subtype") == "meeting"
    ]

    def sort_key(e: dict[str, Any]) -> tuple:
        a = e.get("attributes") if isinstance(e.get("attributes"), dict) else {}
        return (a.get("deal_index", 0), a.get("meeting_index", 0), e.get("logical_id", ""))

    return sorted(rows, key=sort_key)


async def _post(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict[str, str],
    *,
    json_body: Any | None = None,
    step: str,
) -> dict[str, Any] | None:
    t0 = time.perf_counter()
    print(f"[import] {method} {step} …", flush=True)
    req_kw: dict[str, Any] = {"headers": headers}
    if json_body is not None:
        req_kw["json"] = json_body
    response = await client.request(method, url, **req_kw)
    elapsed = time.perf_counter() - t0
    if response.status_code >= 400:
        raise RuntimeError(
            f"{step} HTTP {response.status_code} за {elapsed:.2f}s: {response.text[:2000]}",
        )
    print(f"[import] OK {step} за {elapsed:.2f}s", flush=True)
    if response.content:
        data = response.json()
        if isinstance(data, dict):
            return data
    return None


async def _pipeline_one_note(
    *,
    client: httpx.AsyncClient,
    root: str,
    headers: dict[str, str],
    row: dict[str, Any],
    index: int,
    total: int,
    cli_namespace: str,
    use_json_namespace: bool,
    skip_apply: bool,
    sem: asyncio.Semaphore,
) -> None:
    lid = row.get("logical_id", "?")
    prefix = f"[{index + 1}/{total} {lid}]"
    async with sem:
        ns = _namespace_for_row(row, cli_namespace, use_json_namespace)
        text = _note_text(row)
        name = row.get("name") or "Встреча"
        payload: dict[str, Any] = {
            "entity_type": "note",
            "entity_subtype": "meeting",
            "namespace": ns,
            "name": name,
            "description": text,
            "attributes": row.get("attributes") if isinstance(row.get("attributes"), dict) else {},
            "tags": row.get("tags") if isinstance(row.get("tags"), list) else [],
        }
        if row.get("note_date"):
            payload["note_date"] = row["note_date"]

        created = await _post(
            client,
            "POST",
            f"{root}/entities",
            headers,
            json_body=payload,
            step=f"{prefix} заметка",
        )
        if not created:
            raise RuntimeError(f"{prefix} пустой ответ при создании заметки")
        note_id = created.get("entity_id")
        if not note_id:
            raise RuntimeError(f"{prefix} в ответе нет entity_id")

        analyze_body = {"check_duplicates": False}
        analyze_url = f"{root}/entities/notes/{note_id}/analyze"
        await _post(
            client,
            "POST",
            analyze_url,
            headers,
            json_body=analyze_body,
            step=f"{prefix} analyze",
        )

        if skip_apply:
            print(f"[import] {prefix} apply пропущен (--skip-apply)", flush=True)
            return

        apply_url = f"{root}/entities/notes/{note_id}/apply"
        await _post(
            client,
            "POST",
            apply_url,
            headers,
            json_body=None,
            step=f"{prefix} apply",
        )


async def run(
    *,
    base_url: str,
    token: str,
    json_path: str,
    cli_namespace: str,
    use_json_namespace: bool,
    limit: int | None,
    skip_apply: bool,
    timeout: float,
    concurrency: int,
) -> None:
    with open(json_path, encoding="utf-8") as f:
        bundle = json.load(f)

    entities_raw = bundle.get("logical_entities")
    if not isinstance(entities_raw, list):
        raise ValueError("В JSON нет logical_entities")

    notes = _iter_meeting_notes(entities_raw)
    if limit is not None:
        notes = notes[:limit]

    if not notes:
        print("[import] Нет записей встреч (note/meeting) в JSON — нечего импортировать.", flush=True)
        return

    n = len(notes)
    parallel = concurrency if concurrency > 0 else n
    parallel = max(1, min(parallel, n))
    print(
        f"[import] Встреч: {n}, параллельных пайплайнов: {parallel}",
        flush=True,
    )

    root = _api_root(base_url)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    sem = asyncio.Semaphore(parallel)

    async with httpx.AsyncClient(timeout=timeout) as client:
        await asyncio.gather(
            *[
                _pipeline_one_note(
                    client=client,
                    root=root,
                    headers=headers,
                    row=row,
                    index=i,
                    total=n,
                    cli_namespace=cli_namespace,
                    use_json_namespace=use_json_namespace,
                    skip_apply=skip_apply,
                    sem=sem,
                )
                for i, row in enumerate(notes)
            ],
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Симуляция: заметка → analyze → apply по JSON демо.",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("CRM_API_TOKEN", ""),
        help="JWT или CRM_API_TOKEN",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--json-path", default=DEFAULT_JSON_PATH)
    parser.add_argument(
        "--namespace",
        default=DEFAULT_NAMESPACE,
        help=f"Namespace для API (по умолчанию {DEFAULT_NAMESPACE})",
    )
    parser.add_argument(
        "--use-json-namespace",
        action="store_true",
        help="Брать namespace из поля каждой записи в JSON (если пусто — из --namespace)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Обработать только первые N встреч (отладка)",
    )
    parser.add_argument(
        "--skip-apply",
        action="store_true",
        help="Не вызывать apply черновика",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help="Сколько встреч обрабатывать одновременно (0 = без лимита, все сразу)",
    )
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args()

    if not args.token or not str(args.token).strip():
        raise SystemExit("Нужен --token или CRM_API_TOKEN")

    t0 = time.perf_counter()
    asyncio.run(
        run(
            base_url=args.base_url,
            token=str(args.token).strip(),
            json_path=args.json_path,
            cli_namespace=args.namespace,
            use_json_namespace=args.use_json_namespace,
            limit=args.limit,
            skip_apply=args.skip_apply,
            timeout=args.timeout,
            concurrency=args.concurrency,
        ),
    )
    print(f"[import] Готово за {time.perf_counter() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
