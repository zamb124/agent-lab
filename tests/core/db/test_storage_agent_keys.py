"""Ключи устройств не получают префикс компании из контекста запроса."""

from types import SimpleNamespace
from typing import cast

from core.db.storage import Storage
from core.models.context_models import Context


def test_agent_device_key_stays_global_when_company_is_active() -> None:
    context = SimpleNamespace(active_company=SimpleNamespace(company_id="acme"))
    storage = Storage(get_context_func=lambda: cast(Context, context))
    assert storage._company_key("agent_device:dev1") == "agent_device:dev1"
    assert storage._company_key("agent_pairing:123456") == "agent_pairing:123456"
    assert storage._company_key("flows:testing_bundle_seed") == "flows:testing_bundle_seed"
    assert (
        storage._company_key("flows:email_trigger_fired:acme:box:flow:trig:1")
        == "flows:email_trigger_fired:acme:box:flow:trig:1"
    )
    assert storage._company_key("company:system:request:lead-1") == "company:system:request:lead-1"
    assert storage._company_key("mail:notify:acme:user:box:1") == "mail:notify:acme:user:box:1"
    assert storage._company_key("mail_attachment:box:10:0") == "mail_attachment:box:10:0"
    assert (
        storage._company_key("calendar:notify:acme:user:google:evt")
        == "calendar:notify:acme:user:google:evt"
    )
    assert storage._company_key("billing:resource_base_prices_json") == "billing:resource_base_prices_json"
    assert (
        storage._company_key("billing:company:acme:resource_base_prices_json")
        == "billing:company:acme:resource_base_prices_json"
    )
    assert storage._company_key("billing:settled:span:rule") == "billing:settled:span:rule"
    assert storage._company_key("payment:acme:tinkoff:acme:abc") == "payment:acme:tinkoff:acme:abc"
    assert storage._company_key("payment_external:tinkoff:op1") == "payment_external:tinkoff:op1"
    assert storage._company_key("payment_notification:n1") == "payment_notification:n1"
    assert storage._company_key("integration_oauth_state:tok") == "integration_oauth_state:tok"
    assert (
        storage._company_key("integration_ext_author:acme:amocrm:acc:ext")
        == "integration_ext_author:acme:amocrm:acc:ext"
    )
    assert storage._company_key("session") == "company:acme:session"
