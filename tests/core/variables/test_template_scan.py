from core.variables import scan_prompt_template


def test_scan_prompt_template_extracts_required_and_optional_roots():
    result = scan_prompt_template("Summarize {topic} for {?audience} in {topic.style}")

    assert result.required_roots == ["topic"]
    assert result.optional_roots == ["audience"]


def test_scan_prompt_template_excludes_loop_bound_variable():
    template = "{for item in items}{item.name}{endfor} topic={topic}"
    result = scan_prompt_template(template)

    assert "item" not in result.required_roots
    assert "item" not in result.optional_roots
    assert "items" in result.optional_roots
    assert "topic" in result.required_roots


def test_scan_prompt_template_excludes_system_refs():
    result = scan_prompt_template("Now is {current_date} for {user_name}, topic {topic}")

    assert result.required_roots == ["topic"]
    assert "current_date" not in result.optional_roots
    assert "user_name" not in result.optional_roots


def test_scan_prompt_template_empty_input_returns_no_refs():
    result = scan_prompt_template(None)

    assert result.refs == []
    assert result.required_roots == []


def test_scan_prompt_template_nested_required_path():
    result = scan_prompt_template("Use {user.profile.name}")

    assert result.required_roots == ["user"]


def test_scan_prompt_template_short_optional_form():
    result = scan_prompt_template("Hello ?nickname and {?full_name}")

    assert result.optional_roots == ["nickname", "full_name"]
    assert result.required_roots == []


def test_scan_prompt_template_required_with_default_is_not_strictly_required():
    result = scan_prompt_template("Topic {topic|general}")

    assert "topic" not in result.required_roots
    assert any(ref.name == "topic" and not ref.required for ref in result.refs)


def test_scan_prompt_template_optional_with_default():
    result = scan_prompt_template("{?audience|everyone}")

    assert "audience" in result.optional_roots


def test_scan_prompt_template_default_text_nested_refs():
    result = scan_prompt_template("{topic|fallback {style}}")

    assert "topic" not in result.required_roots
    assert "style" in result.required_roots


def test_scan_prompt_template_escape_brace():
    result = scan_prompt_template(r"literal \{topic\} and real {topic}")

    assert result.required_roots == ["topic"]


def test_scan_prompt_template_promotes_optional_to_required():
    result = scan_prompt_template("{?topic} and {topic}")

    assert result.required_roots == ["topic"]
    assert not any(ref.name == "topic" and not ref.required for ref in result.refs)


def test_scan_prompt_template_all_system_variables_excluded():
    template = (
        "{current_date} {current_time} {current_datetime} {current_year} "
        "{current_month} {current_day} {user_name} {user_id} {user_email} {topic}"
    )
    result = scan_prompt_template(template)

    assert result.required_roots == ["topic"]


def test_scan_prompt_template_garbage_braces_do_not_crash():
    result = scan_prompt_template("{{ { } } empty {} unicode тест {topic}")

    assert "topic" in result.required_roots


def test_scan_prompt_template_large_template():
    result = scan_prompt_template("x" * 10000 + "{topic}")

    assert result.required_roots == ["topic"]
