"""Инварианты optional_fields для интеграции AmoCRM."""

from apps.crm.integrations.amocrm.type_extensions import AMO_OPTIONAL_FIELDS_BY_TYPE_ID


def test_amocrm_optional_fields_include_organization_with_external_refs() -> None:
    org = AMO_OPTIONAL_FIELDS_BY_TYPE_ID["organization"]
    assert isinstance(org, dict)
    assert "external_refs" in org
    assert org["external_refs"]["type"] == "external_refs"
