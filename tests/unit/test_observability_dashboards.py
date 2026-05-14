import json
import re
from pathlib import Path

import pytest
import yaml

# Источник правды для дашбордов / Loki / Alloy / Grafana provisioning — Helm chart files.
_OBSERVABILITY_FILES = Path(__file__).parents[2] / "deploy" / "helm" / "agent-lab" / "files"
DASHBOARDS_DIR = _OBSERVABILITY_FILES / "dashboards"
ALERTS_DIR = _OBSERVABILITY_FILES / "grafana-alerts"
OBSERVABILITY_DIR = _OBSERVABILITY_FILES

LOKI_DATASOURCE_UID = "loki"
TEMPO_DATASOURCE_UID = "tempo"


def _load_dashboards():
    dashboards = {}
    for path in sorted(DASHBOARDS_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            dashboards[path.name] = json.load(f)
    return dashboards


@pytest.fixture(scope="module")
def dashboards():
    return _load_dashboards()


class TestDashboardStructure:
    def test_all_dashboards_have_required_fields(self, dashboards):
        for name, db in dashboards.items():
            assert db.get("schemaVersion") >= 36, f"{name}: outdated schemaVersion"
            assert db.get("uid"), f"{name}: missing uid"
            assert db.get("title"), f"{name}: missing title"
            assert db.get("panels"), f"{name}: no panels"

    def test_all_uids_unique(self, dashboards):
        uids = [db["uid"] for db in dashboards.values()]
        assert len(uids) == len(set(uids)), f"Duplicate UIDs found: {uids}"

    def test_all_datasources_valid(self, dashboards):
        for name, db in dashboards.items():
            for panel in db.get("panels", []):
                for target in panel.get("targets", []):
                    ds = target.get("datasource")
                    if ds is None:
                        continue
                    uid = ds.get("uid") if isinstance(ds, dict) else ds
                    assert uid in {LOKI_DATASOURCE_UID, TEMPO_DATASOURCE_UID}, (
                        f"{name}: invalid datasource uid '{uid}'"
                    )


class TestLogQLExpressions:
    def test_no_json_dot_notation_in_logql(self, dashboards):
        """
        Loki | json parser превращает http.status_code в http_status_code.
        LogQL с точками в именах полей (например `json | http.status_code >= 500`) — баг.
        Исключаем строковые литералы (message="foo.bar") и regex ({svc=~".+"}).
        """
        # Ищем поля с точкой вне строковых литералов и regex
        dot_field_pattern = re.compile(
            r"\|\s+json\s+\|"           # начало: | json |
            r"[^|]*?"                    # любые символы до следующего |
            r"\b[a-z_]+\.[a-z_]+\b"     # field.subfield
            r"(?![\"'])"               # не за которым следует кавычка
        )
        for name, db in dashboards.items():
            for panel in db.get("panels", []):
                for target in panel.get("targets", []):
                    expr = target.get("expr", "")
                    if "| json" not in expr:
                        continue
                    matches = dot_field_pattern.findall(expr)
                    assert not matches, (
                        f"{name}: LogQL contains dot-notation after | json: {expr}"
                    )

    def test_unwrap_fields_use_underscores(self, dashboards):
        for name, db in dashboards.items():
            for panel in db.get("panels", []):
                for target in panel.get("targets", []):
                    expr = target.get("expr", "")
                    for match in re.finditer(r"unwrap\s+(\S+)", expr):
                        field = match.group(1)
                        assert "." not in field, (
                            f"{name}: unwrap uses dot notation: {field} in {expr}"
                        )

    def test_all_logql_have_svc_selector_or_explicit_scope(self, dashboards):
        """
        Все LogQL запросы должны фильтровать по svc (или service) или иметь
        явный контракт без svc (только traces).
        """
        for name, db in dashboards.items():
            for panel in db.get("panels", []):
                for target in panel.get("targets", []):
                    expr = target.get("expr", "")
                    ds = target.get("datasource", {})
                    uid = ds.get("uid") if isinstance(ds, dict) else ds
                    if uid != LOKI_DATASOURCE_UID:
                        continue
                    # Traces или ad-hoc queries могут не иметь svc
                    if "traceId" in expr or "trace_id" in expr.lower():
                        continue
                    assert "svc" in expr or "service" in expr, (
                        f"{name}: LogQL missing svc/service filter: {expr}"
                    )


class TestAlertRules:
    def test_alert_rules_loadable(self):
        path = ALERTS_DIR / "alert-rules.yaml"
        assert path.exists(), "alert-rules.yaml not found"
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert "groups" in data
        assert len(data["groups"]) > 0

    def test_all_alert_uids_unique(self):
        path = ALERTS_DIR / "alert-rules.yaml"
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        uids = []
        for group in data.get("groups", []):
            for rule in group.get("rules", []):
                uid = rule.get("uid")
                assert uid, f"Alert rule missing uid: {rule.get('title')}"
                uids.append(uid)
        assert len(uids) == len(set(uids)), f"Duplicate alert UIDs: {uids}"

    def test_alert_conditions_use_loki(self):
        dot_field_pattern = re.compile(
            r"\|\s+json\s+\|[^|]*?\b[a-z_]+\.[a-z_]+\b(?![\"'])"
        )
        path = ALERTS_DIR / "alert-rules.yaml"
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        for group in data.get("groups", []):
            for rule in group.get("rules", []):
                for q in rule.get("data", []):
                    if q.get("datasourceUid") == LOKI_DATASOURCE_UID:
                        expr = q.get("model", {}).get("expr", "")
                        if "| json" in expr:
                            matches = dot_field_pattern.findall(expr)
                            assert not matches, (
                                f"Alert {rule['uid']}: dot notation after | json: {expr}"
                            )

    def test_contact_points_loadable(self):
        path = ALERTS_DIR / "contact-points.yaml"
        assert path.exists()
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert "contactPoints" in data

    def test_notification_policies_loadable(self):
        path = ALERTS_DIR / "notification-policies.yaml"
        assert path.exists()
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert "policies" in data


class TestProvisioningConfig:
    def test_dashboard_provider_loadable(self):
        path = OBSERVABILITY_DIR / "grafana-dashboards.yaml"
        assert path.exists()
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        providers = data.get("providers", [])
        assert any(p.get("name") == "Platform Dashboards" for p in providers)

    def test_datasources_have_uids(self):
        path = OBSERVABILITY_DIR / "grafana-datasources.yaml"
        assert path.exists()
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        uids = [ds.get("uid") for ds in data.get("datasources", [])]
        # Tempo имеет фиксированный uid; Loki — uid `loki` в grafana-datasources.yaml.
        assert TEMPO_DATASOURCE_UID in uids
        assert LOKI_DATASOURCE_UID in uids
        names = [ds.get("name") for ds in data.get("datasources", [])]
        assert "Loki" in names
        assert "Tempo" in names


class TestAlloyConfig:
    def test_alloy_config_valid(self):
        path = OBSERVABILITY_DIR / "alloy.config"
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert 'svc   = "\\"service.name\\""' not in content, (
            "alloy.config contains escaped quotes for service.name"
        )
        assert "discovery.kubernetes" in content
        assert "discovery.relabel.pods.output" in content

    def test_alloy_has_loki_write_and_otlp(self):
        path = OBSERVABILITY_DIR / "alloy.config"
        content = path.read_text(encoding="utf-8")
        assert "loki.write" in content
        assert "otelcol.receiver.otlp" in content
        assert "otelcol.exporter.otlp" in content
