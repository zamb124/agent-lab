"""
Калькулятор - инструмент для математических вычислений.
Использует ast для безопасного парсинга выражений.
Весь код самодостаточен для инлайнинга.
"""

import ast
import math
import operator
from typing import Optional

from apps.agents.src.tools import tool


@tool(
    name="calculator",
    description="Вычисляет математические выражения. Поддерживает: +, -, *, /, **, %, sqrt, sin, cos, tan, log, exp, pi, e",
    tags=["math"],
)
async def calculator(expression: str, state: Optional[dict] = None) -> str:
    """Вычисляет математическое выражение через безопасный AST парсер."""
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
        "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "asin": math.asin, "acos": math.acos, "atan": math.atan,
        "sqrt": math.sqrt, "pow": math.pow, "exp": math.exp,
        "log": math.log, "log10": math.log10, "log2": math.log2,
        "ceil": math.ceil, "floor": math.floor,
        "abs": abs, "round": round, "min": min, "max": max,
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
