from scripts.check_strict_agent_architecture import collect_violations


def test_strict_agent_architecture_gates_are_clean() -> None:
    violations = collect_violations()
    assert violations == [], "\n".join(violation.format() for violation in violations)
