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


def test_parse_function_signature_prefers_run_over_execute():
    result = _parse_function_signature(
        "async def helper(value: str):\n"
        "    return {}\n\n"
        "async def execute(old: str):\n"
        "    return {}\n\n"
        "async def run(current: int, state=None):\n"
        "    return {}\n",
    )

    assert result["func_name"] == "run"
    assert list(result["parameters"]) == ["current"]


def test_parse_function_signature_falls_back_to_first_top_level_function():
    result = _parse_function_signature(
        "async def first(value: str):\n"
        "    return {}\n\n"
        "async def second(other: int):\n"
        "    return {}\n",
    )

    assert result["func_name"] == "first"
    assert list(result["parameters"]) == ["value"]
