"""RFC 6902 патчи артефакта ``state`` (``core/ui_document/json_patch``).

diff/apply патчей обязаны быть взаимно обратными и не трогать исходные объекты.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.types import JsonObject
from core.ui_document.json_patch import apply_json_patch, json_patch_operations
from core.ui_document.protocol import JsonPatchOperation


class TestJsonPatch:
    def test_diff_covers_add_replace_remove_and_nested_objects(self) -> None:
        before: JsonObject = {"a": 1, "b": {"c": 1, "d": [1]}, "gone": True, "same": "x"}
        after: JsonObject = {"a": 2, "b": {"c": 1, "d": [1, 2], "e": None}, "fresh": {"k": 1}, "same": "x"}
        operations = json_patch_operations(before, after)
        assert [operation.model_dump() for operation in operations] == [
            {"op": "remove", "path": "/gone"},
            {"op": "replace", "path": "/a", "value": 2},
            {"op": "replace", "path": "/b/d", "value": [1, 2]},
            {"op": "add", "path": "/b/e", "value": None},
            {"op": "add", "path": "/fresh", "value": {"k": 1}},
        ]
        assert apply_json_patch(before, operations) == after
        assert json_patch_operations(after, after) == []

    def test_type_change_is_a_whole_value_replace(self) -> None:
        operations = json_patch_operations({"a": {"x": 1}}, {"a": [1]})
        assert [operation.op for operation in operations] == ["replace"]
        operations = json_patch_operations({"a": 1}, {"a": {"x": 1}})
        assert operations[0].value == {"x": 1}

    def test_pointer_escaping_round_trips_special_keys(self) -> None:
        before: JsonObject = {}
        after: JsonObject = {"a/b": 1, "c~d": {"e/f": 2}}
        operations = json_patch_operations(before, after)
        assert [operation.path for operation in operations] == ["/a~1b", "/c~0d"]
        assert apply_json_patch(before, operations) == after
        removal = json_patch_operations(after, {"c~d": {}})
        assert [operation.path for operation in removal] == ["/a~1b", "/c~0d/e~1f"]
        assert apply_json_patch(after, removal) == {"c~d": {}}

    def test_apply_does_not_mutate_the_target(self) -> None:
        target: JsonObject = {"a": {"b": {"c": 1}}, "list": [1]}
        patched = apply_json_patch(
            target,
            [
                JsonPatchOperation(op="replace", path="/a/b/c", value=2),
                JsonPatchOperation(op="add", path="/a/new", value=True),
                JsonPatchOperation(op="remove", path="/list"),
            ],
        )
        assert patched == {"a": {"b": {"c": 2}, "new": True}}
        assert target == {"a": {"b": {"c": 1}}, "list": [1]}

    def test_add_creates_intermediate_objects(self) -> None:
        assert apply_json_patch({}, [JsonPatchOperation(op="add", path="/a/b/c", value=1)]) == {
            "a": {"b": {"c": 1}}
        }
        assert apply_json_patch(
            {"a": 5}, [JsonPatchOperation(op="add", path="/a/b", value=1)]
        ) == {"a": {"b": 1}}

    def test_root_operations(self) -> None:
        assert apply_json_patch({"a": 1}, [JsonPatchOperation(op="replace", path="", value={"b": 2})]) == {"b": 2}
        with pytest.raises(ValueError, match="cannot remove document root"):
            _ = apply_json_patch({"a": 1}, [JsonPatchOperation(op="remove", path="")])
        with pytest.raises(ValueError, match="root value must be an object"):
            _ = apply_json_patch({"a": 1}, [JsonPatchOperation(op="replace", path="", value=[1])])

    def test_remove_of_unknown_path_fails(self) -> None:
        with pytest.raises(ValueError, match="does not exist"):
            _ = apply_json_patch({"a": 1}, [JsonPatchOperation(op="remove", path="/b")])
        with pytest.raises(ValueError, match="does not exist"):
            _ = apply_json_patch({"a": 1}, [JsonPatchOperation(op="remove", path="/a/b")])

    def test_operation_path_must_be_a_json_pointer(self) -> None:
        with pytest.raises(ValidationError):
            _ = JsonPatchOperation(op="add", path="a", value=1)
        with pytest.raises(ValidationError):
            _ = JsonPatchOperation(op="move", path="/a")  # pyright: ignore[reportArgumentType]

    def test_remove_operation_serializes_without_value(self) -> None:
        operation = JsonPatchOperation(op="remove", path="/a", value=1)
        assert operation.model_dump() == {"op": "remove", "path": "/a"}
        assert operation.model_dump(mode="json", exclude_none=True) == {"op": "remove", "path": "/a"}
        assert JsonPatchOperation(op="add", path="/a").model_dump() == {"op": "add", "path": "/a", "value": None}
        assert JsonPatchOperation.model_validate({"op": "remove", "path": "/a"}).value is None
