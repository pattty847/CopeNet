"""Safe parsing and evaluation for synthetic market formula symbols.

Formula symbols are close-price expressions such as ``VOO / GLD``.  They are
not securities: this module deliberately returns scalar points rather than
inventing OHLCV bars for arithmetic that has no honest candle interpretation.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Callable, Literal

from .models import MarketBar


MAX_EXPRESSION_LENGTH = 200
MAX_COMPONENT_SYMBOLS = 10
MAX_NESTING = 8
_SYMBOL_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.^=_-")
_NUMBER = re.compile(r"^(?:\d+(?:\.\d*)?|\.\d+)$")


class FormulaError(ValueError):
    """An expression is invalid or cannot be evaluated honestly."""


@dataclass(frozen=True)
class _Token:
    kind: Literal["symbol", "number", "operator", "lparen", "rparen", "eof"]
    text: str
    offset: int


@dataclass(frozen=True)
class _Symbol:
    value: str


@dataclass(frozen=True)
class _NumberNode:
    value: float


@dataclass(frozen=True)
class _Unary:
    operator: Literal["+", "-"]
    operand: "_Node"


@dataclass(frozen=True)
class _Binary:
    operator: Literal["+", "-", "*", "/"]
    left: "_Node"
    right: "_Node"


_Node = _Symbol | _NumberNode | _Unary | _Binary


@dataclass(frozen=True)
class ParsedFormula:
    expression: str
    components: tuple[str, ...]
    root: _Node
    synthetic: bool


@dataclass(frozen=True)
class FormulaPoint:
    t: int
    value: float


@dataclass(frozen=True)
class FormulaSeries:
    expression: str
    components: tuple[str, ...]
    points: tuple[FormulaPoint, ...]
    warnings: tuple[str, ...]

    def to_wire(self) -> dict[str, object]:
        return {
            "expression": self.expression,
            "components": list(self.components),
            "points": [{"t": point.t, "value": point.value} for point in self.points],
            "warnings": list(self.warnings),
        }


class _Parser:
    def __init__(self, tokens: list[_Token]) -> None:
        self.tokens = tokens
        self.index = 0
        self.depth = 0

    @property
    def current(self) -> _Token:
        return self.tokens[self.index]

    def advance(self) -> _Token:
        token = self.current
        self.index += 1
        return token

    def parse(self) -> _Node:
        root = self.additive()
        if self.current.kind != "eof":
            raise FormulaError(f"Unexpected '{self.current.text}' at position {self.current.offset + 1}")
        return root

    def additive(self) -> _Node:
        node = self.multiplicative()
        while self.current.kind == "operator" and self.current.text in {"+", "-"}:
            operator = self.advance().text
            node = _Binary(operator, node, self.multiplicative())  # type: ignore[arg-type]
        return node

    def multiplicative(self) -> _Node:
        node = self.unary()
        while self.current.kind == "operator" and self.current.text in {"*", "/"}:
            operator = self.advance().text
            node = _Binary(operator, node, self.unary())  # type: ignore[arg-type]
        return node

    def unary(self) -> _Node:
        if self.current.kind == "operator" and self.current.text in {"+", "-"}:
            operator = self.advance().text
            return _Unary(operator, self.unary())  # type: ignore[arg-type]
        return self.primary()

    def primary(self) -> _Node:
        token = self.current
        if token.kind == "symbol":
            self.advance()
            return _Symbol(token.text.upper())
        if token.kind == "number":
            self.advance()
            return _NumberNode(float(token.text))
        if token.kind == "lparen":
            self.advance()
            self.depth += 1
            if self.depth > MAX_NESTING:
                raise FormulaError(f"Formula nesting cannot exceed {MAX_NESTING} levels")
            node = self.additive()
            if self.current.kind != "rparen":
                raise FormulaError(f"Missing ')' for '(' at position {token.offset + 1}")
            self.advance()
            self.depth -= 1
            return node
        if token.kind == "eof":
            raise FormulaError("Formula ends before the next value")
        raise FormulaError(f"Expected a symbol, number, or '(' at position {token.offset + 1}")


def parse_formula(source: str) -> ParsedFormula:
    compact = source.strip()
    if not compact:
        raise FormulaError("Formula is required")
    if len(compact) > MAX_EXPRESSION_LENGTH:
        raise FormulaError(f"Formula cannot exceed {MAX_EXPRESSION_LENGTH} characters")
    root = _Parser(_tokenize(compact)).parse()
    components: list[str] = []
    _collect_symbols(root, components)
    if not components:
        raise FormulaError("Formula must contain at least one market symbol")
    if len(components) > MAX_COMPONENT_SYMBOLS:
        raise FormulaError(f"Formula cannot contain more than {MAX_COMPONENT_SYMBOLS} symbols")
    return ParsedFormula(
        expression=_format(root),
        components=tuple(components),
        root=root,
        synthetic=not isinstance(root, _Symbol),
    )


def formula_search_candidate(source: str) -> dict[str, object] | None:
    """Return a typed synthetic search row when ``source`` is a complete formula."""

    try:
        parsed = parse_formula(source)
    except FormulaError:
        return None
    if not parsed.synthetic:
        return None
    count = len(parsed.components)
    return {
        "type": "formula",
        "symbol": parsed.expression,
        "name": f"Formula symbol · {count} component{'s' if count != 1 else ''}",
        "exchange": "SYNTHETIC",
        "components": list(parsed.components),
    }


def active_formula_symbol(source: str) -> str:
    """The operand under the cursor for yfinance assistance in a formula input."""

    match = re.search(r"([A-Za-z0-9.^=_-]+)\s*$", source)
    if not match:
        return ""
    token = match.group(1)
    return "" if _NUMBER.fullmatch(token) else token.upper()


def evaluate_formulas(
    expressions: list[str],
    load_bars: Callable[[str], list[MarketBar]],
) -> list[FormulaSeries]:
    if not expressions:
        raise FormulaError("At least one formula is required")
    if len(expressions) > 5:
        raise FormulaError("At most five formulas may be plotted together")
    parsed_rows = [parse_formula(expression) for expression in expressions]
    unique_symbols = list(dict.fromkeys(symbol for row in parsed_rows for symbol in row.components))
    if len(unique_symbols) > MAX_COMPONENT_SYMBOLS:
        raise FormulaError(f"A chart cannot contain more than {MAX_COMPONENT_SYMBOLS} component symbols")
    histories = {symbol: load_bars(symbol) for symbol in unique_symbols}
    missing = [symbol for symbol, bars in histories.items() if not bars]
    if missing:
        raise FormulaError(f"No price history for {', '.join(missing)}")
    values = {
        symbol: {bar.t: float(bar.c) for bar in bars if math.isfinite(float(bar.c))}
        for symbol, bars in histories.items()
    }
    return [_evaluate_formula(parsed, values) for parsed in parsed_rows]


def _evaluate_formula(parsed: ParsedFormula, values: dict[str, dict[int, float]]) -> FormulaSeries:
    shared_times = set(values[parsed.components[0]])
    for symbol in parsed.components[1:]:
        shared_times.intersection_update(values[symbol])
    points: list[FormulaPoint] = []
    invalid_count = 0
    for timestamp in sorted(shared_times):
        environment = {symbol: values[symbol][timestamp] for symbol in parsed.components}
        try:
            value = _evaluate_node(parsed.root, environment)
        except (ZeroDivisionError, OverflowError):
            invalid_count += 1
            continue
        if not math.isfinite(value):
            invalid_count += 1
            continue
        points.append(FormulaPoint(t=timestamp, value=round(value, 10)))
    warnings: list[str] = []
    if invalid_count:
        warnings.append(f"Skipped {invalid_count} point{'s' if invalid_count != 1 else ''} with undefined or non-finite results")
    if not points:
        warnings.append("No shared timestamps produced a finite formula value")
    return FormulaSeries(parsed.expression, parsed.components, tuple(points), tuple(warnings))


def _evaluate_node(node: _Node, environment: dict[str, float]) -> float:
    if isinstance(node, _Symbol):
        return environment[node.value]
    if isinstance(node, _NumberNode):
        return node.value
    if isinstance(node, _Unary):
        value = _evaluate_node(node.operand, environment)
        return value if node.operator == "+" else -value
    left = _evaluate_node(node.left, environment)
    right = _evaluate_node(node.right, environment)
    if node.operator == "+":
        return left + right
    if node.operator == "-":
        return left - right
    if node.operator == "*":
        return left * right
    if right == 0:
        raise ZeroDivisionError
    return left / right


def _tokenize(source: str) -> list[_Token]:
    tokens: list[_Token] = []
    index = 0
    while index < len(source):
        char = source[index]
        if char.isspace():
            index += 1
            continue
        if char in "+*/":
            tokens.append(_Token("operator", char, index))
            index += 1
            continue
        if char == "-" and not _hyphen_inside_symbol(source, index):
            tokens.append(_Token("operator", char, index))
            index += 1
            continue
        if char == "(":
            tokens.append(_Token("lparen", char, index))
            index += 1
            continue
        if char == ")":
            tokens.append(_Token("rparen", char, index))
            index += 1
            continue
        if char not in _SYMBOL_CHARS:
            raise FormulaError(f"Unsupported character '{char}' at position {index + 1}")
        start = index
        while index < len(source) and source[index] in _SYMBOL_CHARS:
            if source[index] == "-" and not _hyphen_inside_symbol(source, index):
                break
            index += 1
        text = source[start:index]
        tokens.append(_Token("number" if _NUMBER.fullmatch(text) else "symbol", text, start))
        if len(tokens) > 128:
            raise FormulaError("Formula contains too many terms")
    tokens.append(_Token("eof", "", len(source)))
    return tokens


def _hyphen_inside_symbol(source: str, index: int) -> bool:
    if index <= 0 or index + 1 >= len(source):
        return False
    return source[index - 1] in _SYMBOL_CHARS and source[index + 1] in _SYMBOL_CHARS


def _collect_symbols(node: _Node, output: list[str]) -> None:
    if isinstance(node, _Symbol):
        if node.value not in output:
            output.append(node.value)
        return
    if isinstance(node, _Unary):
        _collect_symbols(node.operand, output)
    elif isinstance(node, _Binary):
        _collect_symbols(node.left, output)
        _collect_symbols(node.right, output)


def _precedence(node: _Node) -> int:
    if isinstance(node, _Binary):
        return 1 if node.operator in {"+", "-"} else 2
    if isinstance(node, _Unary):
        return 3
    return 4


def _format(node: _Node, parent_precedence: int = 0, right_of: str | None = None) -> str:
    precedence = _precedence(node)
    if isinstance(node, _Symbol):
        text = node.value
    elif isinstance(node, _NumberNode):
        text = f"{node.value:.15g}"
    elif isinstance(node, _Unary):
        text = f"{node.operator}{_format(node.operand, precedence)}"
    else:
        left = _format(node.left, precedence)
        right = _format(node.right, precedence, node.operator)
        text = f"{left} {node.operator} {right}"
    right_group_changes_shape = (
        isinstance(node, _Binary)
        and right_of is not None
        and precedence == parent_precedence
        and (right_of in {"-", "/"} or (right_of == "*" and node.operator == "/"))
    )
    needs_parentheses = precedence < parent_precedence or right_group_changes_shape
    return f"({text})" if needs_parentheses else text
