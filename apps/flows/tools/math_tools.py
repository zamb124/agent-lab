"""Математический tool `calculator`: безопасное вычисление выражений через ast."""

import ast
import math
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS

type Number = int | float


class CalculatorArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

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
    args_schema=CalculatorArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def calculator(expression: str, state: dict[str, Any] | None = None) -> str:
    funcs: dict[str, Callable[..., Any]] = {
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "asin": math.asin,
        "acos": math.acos,
        "atan": math.atan,
        "sqrt": math.sqrt,
        "pow": math.pow,
        "exp": math.exp,
        "log": math.log,
        "log10": math.log10,
        "log2": math.log2,
        "ceil": math.ceil,
        "floor": math.floor,
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
    }

    consts: dict[str, Number] = {"pi": math.pi, "e": math.e, "tau": math.tau}

    def _number(value: Any) -> Number:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Only numeric values are supported")
        return value

    def eval_node(node: ast.AST) -> Number:
        if isinstance(node, ast.Expression):
            return eval_node(node.body)
        if isinstance(node, ast.Constant):
            return _number(node.value)
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
            if fn not in funcs:
                raise ValueError(f"Unsupported function: {fn}")
            return _number(funcs[fn](*[eval_node(a) for a in node.args]))
        raise ValueError("Unsupported expression type")

    tree = ast.parse(expression, mode="eval")
    result = eval_node(tree)
    return f"Результат: {result}"
