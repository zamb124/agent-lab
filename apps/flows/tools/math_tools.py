"""Математический tool `calculator`: безопасное вычисление выражений через ast."""

import ast
import math
import operator
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.tools import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS


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
async def calculator(expression: str, state: Optional[dict] = None) -> str:
    ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    funcs = {
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

    consts = {"pi": math.pi, "e": math.e, "tau": math.tau}

    def eval_node(node):
        if isinstance(node, ast.Expression):
            return eval_node(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in consts:
                return consts[node.id]
            raise ValueError(f"Unknown variable: {node.id}")
        if isinstance(node, ast.BinOp):
            op = type(node.op)
            if op not in ops:
                raise ValueError("Unsupported binary operation")
            return ops[op](eval_node(node.left), eval_node(node.right))
        if isinstance(node, ast.UnaryOp):
            op = type(node.op)
            if op not in ops:
                raise ValueError("Unsupported unary operation")
            return ops[op](eval_node(node.operand))
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Only simple function calls supported")
            fn = node.func.id
            if fn not in funcs:
                raise ValueError(f"Unsupported function: {fn}")
            return funcs[fn](*[eval_node(a) for a in node.args])
        raise ValueError("Unsupported expression type")

    tree = ast.parse(expression, mode="eval")
    result = eval_node(tree)
    return f"Результат: {result}"
