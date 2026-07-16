"""Tool-calling agent loop with a max-iterations guard.

Tools: `search` (RBAC-filtered retrieval) and `calculator` (AST-validated
arithmetic). In Azure mode the natural upgrade is native function calling on
the chat deployment; in local mode a small deterministic planner picks the
tool so the loop is fully exercisable without credentials.
"""

import ast
import logging
import operator
import re
from dataclasses import dataclass, field

from app.services.llm import LLM, Message
from app.services.rag import RagPipeline

logger = logging.getLogger(__name__)

_MATH_RE = re.compile(r"[-+(]*\d[\d\s.+\-*/()%]*[+\-*/%][\d\s.+\-*/()%]*\d\)*")

_ALLOWED_OPS = {
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


def calculator(expression: str) -> str:
    """Safely evaluate arithmetic via the AST — no eval(), no builtins."""

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPS:
            return _ALLOWED_OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPS:
            return _ALLOWED_OPS[type(node.op)](_eval(node.operand))
        raise ValueError(f"unsupported expression element: {type(node).__name__}")

    try:
        result = _eval(ast.parse(expression.strip(), mode="eval"))
    except (SyntaxError, ValueError, ZeroDivisionError) as exc:
        return f"calculator error: {exc}"
    return str(round(result, 6)) if isinstance(result, float) else str(result)


@dataclass
class AgentResult:
    answer: str
    steps: list[dict] = field(default_factory=list)


class Agent:
    def __init__(self, rag: RagPipeline, llm: LLM, max_iterations: int = 4):
        self._rag = rag
        self._llm = llm
        self._max_iterations = max_iterations

    def run(self, query: str, allowed_groups: list[str] | None) -> AgentResult:
        steps: list[dict] = []
        for _ in range(self._max_iterations):
            tool, tool_input = self._plan(query, steps)
            if tool is None:
                return AgentResult(self._finalize(query, steps), steps)
            observation = self._invoke(tool, tool_input, allowed_groups)
            steps.append({"tool": tool, "input": tool_input, "observation": observation})
            logger.info("agent step", extra={"ctx": {"tool": tool}})
        # Max-iterations guard: never loop forever, answer with what we have.
        return AgentResult(self._finalize(query, steps), steps)

    def _plan(self, query: str, steps: list[dict]) -> tuple[str | None, str]:
        """Choose the next tool.

        NOTE: in Azure mode this becomes native function calling on the chat
        deployment; the deterministic heuristic keeps local mode credential-free.
        """
        if not steps:
            match = _MATH_RE.search(query)
            if match:
                expr = match.group().strip()
                # Trim parens the regex over-captured from surrounding prose.
                while expr.count("(") > expr.count(")") and expr.startswith("("):
                    expr = expr[1:]
                while expr.count(")") > expr.count("(") and expr.endswith(")"):
                    expr = expr[:-1]
                return "calculator", expr
            return "search", query
        return None, ""  # one observation gathered -> synthesize the answer

    def _invoke(self, tool: str, tool_input: str, allowed_groups: list[str] | None) -> str:
        if tool == "calculator":
            return calculator(tool_input)
        if tool == "search":
            results = self._rag.retrieve(tool_input, allowed_groups, top_k=3)
            if not results:
                return "no accessible documents matched"
            return "\n".join(
                f"({r.record.title}) {r.record.content}" for r in results
            )
        return f"unknown tool: {tool}"

    def _finalize(self, query: str, steps: list[dict]) -> str:
        if not steps:
            return "I was unable to take any useful action for that request."
        last = steps[-1]
        if last["tool"] == "calculator":
            return f"{last['input'].strip()} = {last['observation']}"
        messages: list[Message] = [
            {"role": "system", "content": "Answer from the sources only."},
            {"role": "system", "content": "SOURCES:\n" + last["observation"]},
            {"role": "user", "content": query},
        ]
        return self._llm.complete(messages)
