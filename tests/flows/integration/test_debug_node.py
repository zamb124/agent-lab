"""debug: where does the seed lead get dropped"""
from __future__ import annotations
import json, pytest
from apps.flows.src.services.flows_loader import load_flows_to_db
from apps.flows.src.tools.registry import ToolRegistry
from core.clients.mail_client import MailClient
from core.config.models import MailConfig
from core.mail.service import MailService
from tests.core.mail.conftest import seed_mail_company_member
from tests.core.mail.fakes import RecordingMailServerPort
from tests.flows.durable_runtime_harness import run_flow, workflow_state
from core.mail.models import CompanyMailConnectionUpsertPayload, MailboxBindingCreatePayload, MailboxBindingKind, MailProvider

@pytest.mark.asyncio
async def test_where_lead_dropped(app, di, unique_id, mock_llm_with_queue):
    company_id, user_id = f"so_{unique_id}", f"so_user_{unique_id}"
    await seed_mail_company_member(di, company_id=company_id, user_id=user_id, unique_id=unique_id)
    port = RecordingMailServerPort(supports_provision=False)
    service = MailService(authz=di.authz_service, namespace_service=di.namespace_service,
                          mail_config=MailConfig(), port_override=port, files_service=di.files_service)
    _ = await load_flows_to_db(di.flow_access_service, files_service=di.files_service)
    clients = tuple(MailClient(service) if isinstance(c, MailClient) else c for c in di.tool_registry._clients)
    reg = ToolRegistry(clients=clients, node_constructor=di.node_constructor, flow_factory=di.flow_factory)
    reg.register_builtin_tools()
    mock_llm_with_queue(["Итог"])
    flow = await di.flow_factory.get_flow("shop_outreach", tool_registry=reg)
    state = workflow_state(flow_id="shop_outreach", unique_id=unique_id,
                           content="Лид: lead1@restaurant.example", user_id=user_id,
                           variables={"send_enabled": False, "sender_local_part": "sales", "crm_namespace": ""})
    result = await run_flow(di=di, flow=flow, state=state)
    dump = {k: result.get(k) for k in ("leads","leads_to_send","skipped_leads","node_errors","run_stats_json","rendered_emails","seed_mode","seed_leads","send_enabled")}
    with open("/tmp/flow_dump.json","w") as f:
        f.write(json.dumps(dump, default=str, ensure_ascii=False))
    pytest.fail("dump written")
