from apps.flows.src.api.v1.code import _parse_function_signature


def test_parse_function_signature_preserves_none_default_for_optional_param():
    result = _parse_function_signature(
        "async def execute(url: str, data: dict = None, state: dict = None):\n"
        "    return {}\n",
        "execute",
    )

    params = result["parameters"]
    assert params["url"]["required"] is True
    assert params["url"]["has_default"] is False
    assert params["data"]["type"] == "object"
    assert params["data"]["required"] is False
    assert params["data"]["has_default"] is True
    assert params["data"]["default"] is None
