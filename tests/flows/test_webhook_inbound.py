"""apps.flows.src.triggers.webhook_inbound"""

import apps.flows.src.triggers.webhook_inbound as wh


def test_client_ip_allowed_empty():
    assert wh.client_ip_allowed("127.0.0.1", None) is True
    assert wh.client_ip_allowed("127.0.0.1", "") is True


def test_client_ip_allowed_single():
    assert wh.client_ip_allowed("127.0.0.1", "127.0.0.1") is True
    assert wh.client_ip_allowed("127.0.0.1", "8.8.8.8") is False


def test_rate_limit_window():
    flow_id = "test_rl_flow_isolation"
    trigger_id = "test_rl_trigger"
    ip = "198.51.100.7"
    assert wh.check_webhook_rate_limit(flow_id, trigger_id, ip, max_per_minute=3) is True
    assert wh.check_webhook_rate_limit(flow_id, trigger_id, ip, max_per_minute=3) is True
    assert wh.check_webhook_rate_limit(flow_id, trigger_id, ip, max_per_minute=3) is True
    assert wh.check_webhook_rate_limit(flow_id, trigger_id, ip, max_per_minute=3) is False
