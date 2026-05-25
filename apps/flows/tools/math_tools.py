"""Математический tool `calculator`: безопасное вычисление выражений через ast."""

import ast
import math
from types import EllipsisType
from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS

if TYPE_CHECKING:
    from core.state import ExecutionState

type Number = int | float
type AstConstantValue = str | bytes | bool | int | float | complex | None | EllipsisType


class CalculatorArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expression: str = Field(
        ...,
        min_length=1,
        description=(
            "Одно математическое выражение: +, -, *, /, //, %, **, скобки; "
            "функции sin, cos, tan, asin, acos, atan, sqrt, pow, exp, log, log10, log2, ceil, floor, abs, round, min, max; "
            "константы pi, e, tau. Без произвольных имён переменных кроме перечисленных констант."
        ),
    )


@tool(
    name="calculator",
    description="Вычисляет математические выражения. Поддерживает: +, -, *, /, **, %, sqrt, sin, cos, tan, log, exp, pi, e",
    tags=["math"],
    parameters_model=CalculatorArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def calculator(expression: str, *, state: "ExecutionState") -> str:
    _ = state
    consts: dict[str, Number] = {"pi": math.pi, "e": math.e, "tau": math.tau}

    def _number(value: AstConstantValue) -> Number:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Only numeric values are supported")
        return value

    def _constant_number(node: ast.Constant) -> Number:
        return _number(node.value)

    def _require_arity(name: str, args: list[Number], allowed: set[int]) -> None:
        if len(args) not in allowed:
            expected = ", ".join(str(item) for item in sorted(allowed))
            raise ValueError(f"Function {name} expects {expected} argument(s)")

    def _call_function(name: str, args: list[Number]) -> Number:
        match name:
            case "sin":
                _require_arity(name, args, {1})
                return math.sin(args[0])
            case "cos":
                _require_arity(name, args, {1})
                return math.cos(args[0])
            case "tan":
                _require_arity(name, args, {1})
                return math.tan(args[0])
            case "asin":
                _require_arity(name, args, {1})
                return math.asin(args[0])
            case "acos":
                _require_arity(name, args, {1})
                return math.acos(args[0])
            case "atan":
                _require_arity(name, args, {1})
                return math.atan(args[0])
            case "sqrt":
                _require_arity(name, args, {1})
                return math.sqrt(args[0])
            case "pow":
                _require_arity(name, args, {2})
                return math.pow(args[0], args[1])
            case "exp":
                _require_arity(name, args, {1})
                return math.exp(args[0])
            case "log":
                _require_arity(name, args, {1, 2})
                if len(args) == 1:
                    return math.log(args[0])
                return math.log(args[0], args[1])
            case "log10":
                _require_arity(name, args, {1})
                return math.log10(args[0])
            case "log2":
                _require_arity(name, args, {1})
                return math.log2(args[0])
            case "ceil":
                _require_arity(name, args, {1})
                return math.ceil(args[0])
            case "floor":
                _require_arity(name, args, {1})
                return math.floor(args[0])
            case "abs":
                _require_arity(name, args, {1})
                return abs(args[0])
            case "round":
                _require_arity(name, args, {1})
                return round(args[0])
            case "min":
                if not args:
                    raise ValueError("Function min expects at least one argument")
                return min(args)
            case "max":
                if not args:
                    raise ValueError("Function max expects at least one argument")
                return max(args)
            case _:
                raise ValueError(f"Unsupported function: {name}")

    def eval_node(node: ast.AST) -> Number:
        if isinstance(node, ast.Expression):
            return eval_node(node.body)
        if isinstance(node, ast.Constant):
            return _constant_number(node)
        if isinstance(node, ast.Name):
            if node.id in consts:
                return consts[node.id]
            raise ValueError(f"Unknown variable: {node.id}")
        if isinstance(node, ast.BinOp):
            left = eval_node(node.left)
            right = eval_node(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.FloorDiv):
                return left // right
            if isinstance(node.op, ast.Mod):
                return left % right
            if isinstance(node.op, ast.Pow):
                return left**right
            raise ValueError("Unsupported binary operation")
        if isinstance(node, ast.UnaryOp):
            operand = eval_node(node.operand)
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return +operand
            raise ValueError("Unsupported unary operation")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Only simple function calls supported")
            fn = node.func.id
            return _call_function(fn, [eval_node(a) for a in node.args])
        raise ValueError("Unsupported expression type")

    tree = ast.parse(expression, mode="eval")
    result = eval_node(tree)
    return f"Результат: {result}"
