
from apps.flows.src.services.flow_node_merge import merge_incoming_node_dict_for_persist


def test_merge_preserves_type_when_incoming_is_only_pos() -> None:
    prev = {
        "formatter": {
            "type": "code",
            "code": "async def run(state):\n    return state",
        }
    }
    inc = {"formatter": {"pos_x": 12, "pos_y": 34}}
    out = merge_incoming_node_dict_for_persist(inc, prev)
    assert out["formatter"]["type"] == "code"
    assert "async def run" in out["formatter"]["code"]
    assert out["formatter"]["pos_x"] == 12
    assert out["formatter"]["pos_y"] == 34


def test_incoming_replaces_when_has_type() -> None:
    prev = {
        "n": {
            "type": "code",
            "code": "old",
        }
    }
    inc = {
        "n": {
            "type": "llm_node",
            "llm": {"model": "x"},
        }
    }
    out = merge_incoming_node_dict_for_persist(inc, prev)
    assert out["n"]["type"] == "llm_node"


def test_pos_only_no_prev_unchanged() -> None:
    inc = {"a": {"pos_x": 1, "pos_y": 2}}
    out = merge_incoming_node_dict_for_persist(inc, None)
    assert out == inc
