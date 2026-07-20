#!/usr/bin/env python3
"""Idempotent repair: mailbox bindings without password_encrypted get a rotated ISP password.

Run in-cluster (frontend pod) after mail.system connection exists:

  kubectl cp deploy/scripts/mail_system_repair_missing_passwords.py \\
    platform/$(kubectl get pod -n platform -l app=frontend -o jsonpath='{.items[0].metadata.name}'):/tmp/repair_mail.py
  kubectl exec -n platform deployment/frontend -- python /tmp/repair_mail.py

Safe to re-run: bindings that already have password_encrypted are skipped.
Uses ISPmanager email.edit directly so it works on images before set_mailbox_password.
"""

from __future__ import annotations

import asyncio
import secrets
import sys

from core.ai.company_settings import encrypt_secret
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID
from core.logging import get_logger
from core.mail.models import MailboxEnsureSpec

logger = get_logger(__name__)


async def _repair() -> int:
    from apps.frontend.container import get_frontend_container

    container = get_frontend_container()
    mail_service = container.mail_service
    connection = await mail_service.get_connection(SYSTEM_COMPANY_ID)
    if connection is None:
        raise RuntimeError("company_mail_connections: system connection missing")
    bindings = await mail_service._binding_repository.list_by_company(SYSTEM_COMPANY_ID)
    port = mail_service.port_for_connection(connection)
    repaired = 0
    skipped = 0
    for binding in bindings:
        if binding.password_encrypted and binding.password_encrypted.strip():
            skipped += 1
            continue
        password = secrets.token_urlsafe(24)
        spec = MailboxEnsureSpec(
            mail_domain=connection.mail_domain,
            local_part=binding.local_part,
            password=password,
        )
        _ = await port.ensure_mailbox(spec)
        if hasattr(port, "set_mailbox_password"):
            await port.set_mailbox_password(spec)
        elif hasattr(port, "_call"):
            email_address = f"{binding.local_part}@{connection.mail_domain}".lower()
            _ = await port._call(
                "email.edit",
                {
                    "elid": email_address,
                    "passwd": password,
                    "confirm": password,
                    "sok": "ok",
                },
            )
        else:
            raise RuntimeError(f"port cannot set mailbox password: {type(port)!r}")
        updated = binding.model_copy(
            update={"password_encrypted": encrypt_secret(password)},
        )
        _ = await mail_service._binding_repository.upsert(updated)
        repaired += 1
        logger.info(
            "mail.system.password_repaired",
            email_address=binding.email_address,
            mailbox_binding_id=binding.mailbox_binding_id,
        )
    logger.info(
        "mail.system.password_repair_done",
        repaired=repaired,
        skipped=skipped,
        total=len(bindings),
    )
    return repaired


def main() -> None:
    repaired = asyncio.run(_repair())
    print(f"repaired={repaired}", file=sys.stderr)


if __name__ == "__main__":
    main()
