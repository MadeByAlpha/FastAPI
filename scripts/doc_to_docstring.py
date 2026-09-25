#!/usr/bin/env python3
"""
Convert `annotated_doc.Doc` metadata into plain docstrings.

- `Annotated[T, Doc("...")]` is unwrapped to `T`.
- `Annotated[T, X, Doc("...")]` keeps the other metadata: `Annotated[T, X]`.
- Documentation of function parameters becomes a Google style `Args:` section, which
  basedpyright and ty both use for per-parameter hover and signature help. The section is
  inserted before the first Markdown heading of the existing docstring (e.g. `## Example`),
  or at its end when there is none.
- Documentation of variables and class attributes becomes an attribute docstring right
  after the declaration.
- Generated docstring lines longer than `MAX_LINE_LENGTH` are wrapped at word boundaries.
  Fenced code blocks, headings and tables are left as they are, and a single word longer
  than the limit (e.g. a URL) is kept whole.
- `annotated_doc` imports left unused are removed, as are `Annotated` imports whose last
  usage was removed by the conversion.

Only the edited spans are rewritten; the rest of each file is left untouched.

Usage:
    python scripts/doc_to_docstring.py [PATH ...]  # default: typings
"""

from __future__ import annotations

import argparse
import ast
import inspect
import re
import sys
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import cast, final

MAX_LINE_LENGTH = 120

ARGS_HEADER = "Args:"
ARG_INDENT = " " * 4
ARG_DESCRIPTION_INDENT = " " * 8

DOC_MODULE = "annotated_doc"
ANNOTATED_MODULES = frozenset({"typing", "typing_extensions"})

FENCE_RE = re.compile(r"(`{3,}|~{3,})")
HEADING_RE = re.compile(r"#{1,6}(\s|$)")
LIST_ITEM_RE = re.compile(r"([-*+]|\d+[.)])\s+")
# A word that would change the Markdown structure if a wrapped line started with it.
BLOCK_MARKER_RE = re.compile(r"[-*+>|]|#{1,6}|\d+[.)]|=+|-{2,}|`{3,}.*|~{3,}.*")

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
# Nodes that carry source positions.
Located = ast.stmt | ast.expr
# Renders docstring lines (relative indentation, already escaped) for a given width.
Renderer = Callable[[int], list[str]]


class ConversionError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Edit:
    start: int
    end: int
    text: str


@final
class Source:
    """Source bytes with conversion from AST positions (UTF-8 byte columns) to offsets."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.newline = "\r\n" if b"\r\n" in data else "\n"
        self.line_starts = [0]
        for index, byte in enumerate(data):
            if byte == ord("\n"):
                self.line_starts.append(index + 1)

    def offset(self, lineno: int, col: int) -> int:
        return self.line_starts[lineno - 1] + col

    def start(self, node: Located) -> int:
        return self.offset(node.lineno, node.col_offset)

    def end(self, node: Located) -> int:
        assert node.end_lineno is not None and node.end_col_offset is not None
        return self.offset(node.end_lineno, node.end_col_offset)

    def text(self, start: int, end: int) -> str:
        return self.data[start:end].decode()

    def segment(self, node: Located) -> str:
        return self.text(self.start(node), self.end(node))

    def line_end(self, lineno: int) -> int:
        end = self.line_starts[lineno] - 1 if lineno < len(self.line_starts) else len(self.data)
        if end > 0 and self.data[end - 1 : end] == b"\r":
            end -= 1
        return end

    def indent_of(self, lineno: int) -> str:
        line = self.data[self.line_starts[lineno - 1] : self.line_end(lineno)].decode()
        return line[: len(line) - len(line.lstrip(" \t"))]

    def starts_line(self, node: Located) -> bool:
        """Whether only whitespace precedes `node` on its first line."""
        line_start = self.line_starts[node.lineno - 1]
        return not self.data[line_start : self.start(node)].strip()


@final
class Names:
    """Local names bound to `annotated_doc.Doc`, `Annotated` and their modules."""

    def __init__(self, tree: ast.Module) -> None:
        self.doc: set[str] = set()
        self.annotated: set[str] = set()
        self.doc_modules: set[str] = set()
        self.annotated_modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0:
                for alias in node.names:
                    local = alias.asname or alias.name
                    if node.module == DOC_MODULE and alias.name == "Doc":
                        self.doc.add(local)
                    elif node.module in ANNOTATED_MODULES and alias.name == "Annotated":
                        self.annotated.add(local)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == DOC_MODULE:
                        self.doc_modules.add(alias.asname or alias.name)
                    elif alias.name in ANNOTATED_MODULES:
                        self.annotated_modules.add(alias.asname or alias.name)

    @staticmethod
    def _matches(node: ast.expr, names: set[str], modules: set[str], attr: str) -> bool:
        if isinstance(node, ast.Name):
            return node.id in names
        return (
            isinstance(node, ast.Attribute)
            and node.attr == attr
            and isinstance(node.value, ast.Name)
            and node.value.id in modules
        )

    def is_doc(self, node: ast.expr) -> bool:
        return isinstance(node, ast.Call) and self._matches(node.func, self.doc, self.doc_modules, "Doc")

    def is_annotated(self, node: ast.expr) -> bool:
        return self._matches(node, self.annotated, self.annotated_modules, "Annotated")


def doc_text(call: ast.Call, path: Path) -> str:
    args = [*call.args, *(keyword.value for keyword in call.keywords if keyword.arg == "documentation")]
    if len(args) != 1 or not isinstance(args[0], ast.Constant) or not isinstance(args[0].value, str):
        raise ConversionError(f"{path}:{call.lineno}: Doc() must take a single string literal")
    return inspect.cleandoc(args[0].value)


def escape_docstring(text: str) -> str:
    """Escape text for inclusion inside a non-raw `\"\"\"` literal."""
    return text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')


def starts_block(line: str) -> bool:
    """Whether a line starts a Markdown block that cannot follow `name:` on the same line."""
    stripped = line.lstrip()
    return bool(FENCE_RE.match(stripped) or HEADING_RE.match(stripped) or LIST_ITEM_RE.match(stripped))


def wrap_line(line: str, width: int, hanging: str | None = None) -> list[str]:
    """Wrap one line at word boundaries; continuation lines get the `hanging` indent."""
    stripped = line.lstrip()
    if len(line) <= width or not stripped or HEADING_RE.match(stripped) or stripped.startswith("|"):
        return [line]
    indent = line[: len(line) - len(stripped)]
    if hanging is None:
        item = LIST_ITEM_RE.match(stripped)
        hanging = indent + " " * len(item.group(0)) if item else indent

    rows: list[list[str]] = [[]]
    length = len(indent)
    for word in stripped.split():
        row = rows[-1]
        if row and length + 1 + len(word) > width:
            rows.append([word])
            length = len(hanging) + len(word)
        else:
            length += len(word) + (1 if row else 0)
            row.append(word)
    # Never start a continuation line with a word that Markdown would read as a new block.
    for previous, row in pairwise(rows):
        while len(previous) > 1 and BLOCK_MARKER_RE.fullmatch(row[0]):
            row.insert(0, previous.pop())
    return [(indent if index == 0 else hanging) + " ".join(row) for index, row in enumerate(rows)]


def wrap_markdown(lines: Iterable[str], width: int) -> list[str]:
    """Wrap Markdown lines longer than `width`, leaving fenced code blocks untouched."""
    result: list[str] = []
    fence: str | None = None
    for line in lines:
        stripped = line.lstrip()
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
            result.append(line)
            continue
        if match := FENCE_RE.match(stripped):
            fence = match.group(1)
            result.append(line)
            continue
        result.extend(wrap_line(line, width))
    return result


def render_text(text: str) -> Renderer:
    return lambda width: wrap_markdown(escape_docstring(text).splitlines(), width)


def render_arguments(entries: list[tuple[str, str]]) -> Renderer:
    """Render a Google style `Args:` section."""

    def render(width: int) -> list[str]:
        lines = [ARGS_HEADER]
        for index, (name, text) in enumerate(entries):
            if index:
                lines.append("")
            description = escape_docstring(text).splitlines()
            if description and description[0] and not starts_block(description[0]):
                head, rest = f"{ARG_INDENT}{name}: {description[0]}", description[1:]
            else:
                head, rest = f"{ARG_INDENT}{name}:", description
            lines.extend(wrap_line(head, width, ARG_DESCRIPTION_INDENT))
            lines.extend(wrap_markdown((ARG_DESCRIPTION_INDENT + line if line else "" for line in rest), width))
        return lines

    return render


def indent_block(lines: Iterable[str], indent: str) -> list[str]:
    return [indent + line if line.strip() else "" for line in lines]


def first_heading(lines: list[str]) -> int | None:
    """Index of the first Markdown heading outside fenced code blocks."""
    fence: str | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
        elif match := FENCE_RE.match(stripped):
            fence = match.group(1)
        elif HEADING_RE.match(stripped):
            return index
    return None


def insert_block(lines: list[str], block: list[str], *, before_heading: bool) -> list[str]:
    """
    Insert `block` as its own paragraph, before the first heading or at the end.

    `lines` is the docstring content split into lines: the first one follows the opening
    quotes and the last one precedes the closing quotes.
    """
    lines = list(lines)
    while len(lines) > 1 and not lines[-1].strip():
        del lines[-1]
    index = first_heading(lines) if before_heading else None
    before, after = (lines, []) if index is None else (lines[:index], lines[index:])
    while len(before) > 1 and not before[-1].strip():
        del before[-1]
    if any(line.strip() for line in before):
        before.append("")
    else:
        before = [""]  # only the line break right after the opening quotes
    return [*before, *block, *([""] if after else []), *after]


def get_docstring(body: list[ast.stmt], index: int) -> ast.Expr | None:
    if index < len(body):
        stmt = body[index]
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
            return stmt
    return None


@final
class Converter:
    def __init__(self, path: Path, source: Source, tree: ast.Module) -> None:
        self.path = path
        self.source = source
        self.names = Names(tree)
        self.tree = tree
        self.edits: list[Edit] = []

    def location(self, node: Located) -> str:
        return f"{self.path}:{node.lineno}"

    def strip_doc(self, annotation: ast.expr | None) -> str | None:
        """Remove `Doc` from a top-level `Annotated[...]` and return its text."""
        if not (isinstance(annotation, ast.Subscript) and self.names.is_annotated(annotation.value)):
            return None
        elements = annotation.slice.elts if isinstance(annotation.slice, ast.Tuple) else [annotation.slice]
        docs = [index for index, element in enumerate(elements) if index > 0 and self.names.is_doc(element)]
        if not docs:
            return None
        if len(docs) > 1:
            raise ConversionError(f"{self.location(annotation)}: multiple Doc() in one Annotated[...]")

        index = docs[0]
        call = elements[index]
        assert isinstance(call, ast.Call)
        if len(elements) == 2:
            # Annotated[T, Doc(...)] -> T
            replacement = self.source.segment(elements[0])
            self.edits.append(Edit(self.source.start(annotation), self.source.end(annotation), replacement))
        else:
            # Annotated[T, X, Doc(...)] -> Annotated[T, X]
            self.edits.append(Edit(self.source.end(elements[index - 1]), self.source.end(call), ""))
        return doc_text(call, self.path)

    def run(self) -> None:
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.convert_function(node)
            for field in ("body", "orelse", "finalbody"):
                body: object = getattr(node, field, None)
                if isinstance(body, list):
                    statements = cast("list[ast.stmt]", body)
                    for index, stmt in enumerate(statements):
                        if isinstance(stmt, ast.AnnAssign):
                            self.convert_variable(statements, index, stmt)

    def convert_function(self, function: FunctionNode) -> None:
        arguments = function.args
        parameters: list[tuple[str, ast.arg]] = [
            *((arg.arg, arg) for arg in (*arguments.posonlyargs, *arguments.args)),
            *(() if arguments.vararg is None else ((f"*{arguments.vararg.arg}", arguments.vararg),)),
            *((arg.arg, arg) for arg in arguments.kwonlyargs),
            *(() if arguments.kwarg is None else ((f"**{arguments.kwarg.arg}", arguments.kwarg),)),
        ]
        entries: list[tuple[str, str]] = []
        for name, arg in parameters:
            text = self.strip_doc(arg.annotation)
            if text is not None:
                entries.append((name, text))
        if entries:
            self.add_function_docstring(function, render_arguments(entries))

    def convert_variable(self, body: list[ast.stmt], index: int, stmt: ast.AnnAssign) -> None:
        text = self.strip_doc(stmt.annotation)
        if text is None:
            return
        existing = get_docstring(body, index + 1)
        if existing is not None:
            self.extend_docstring(existing, render_text(text), before_heading=False)
            return

        line_end = self.source.line_end(stmt.end_lineno or stmt.lineno)
        rest = self.source.text(self.source.end(stmt), line_end).strip()
        if rest and not rest.startswith("#"):
            raise ConversionError(f"{self.location(stmt)}: statement is followed by code on the same line")
        indent = self.source.indent_of(stmt.lineno)
        literal = self.new_docstring(render_text(text), indent)
        self.edits.append(Edit(line_end, line_end, self.source.newline + indent + literal))

    def new_docstring(self, render: Renderer, indent: str) -> str:
        newline = self.source.newline
        body = newline.join(indent_block(render(MAX_LINE_LENGTH - len(indent)), indent))
        return f'"""{newline}{body}{newline}{indent}"""'

    def add_function_docstring(self, function: FunctionNode, render: Renderer) -> None:
        existing = get_docstring(function.body, 0)
        if existing is not None:
            self.extend_docstring(existing, render, before_heading=True)
            return

        first = function.body[0]
        newline = self.source.newline
        if self.source.starts_line(first):
            # Insert a new docstring on its own line before the first statement.
            indent = self.source.indent_of(first.lineno)
            line_start = self.source.line_starts[first.lineno - 1]
            literal = self.new_docstring(render, indent)
            self.edits.append(Edit(line_start, line_start, indent + literal + newline))
        else:
            # `def f(...): ...` -> move the body onto its own lines below the docstring.
            indent = self.source.indent_of(function.lineno) + " " * 4
            start = self.source.start(first)
            while start > 0 and self.source.data[start - 1 : start] in (b" ", b"\t"):
                start -= 1
            literal = self.new_docstring(render, indent)
            self.edits.append(Edit(start, self.source.start(first), newline + indent + literal + newline + indent))

    def extend_docstring(self, docstring: ast.Expr, render: Renderer, *, before_heading: bool) -> None:
        """Add a paragraph to an existing docstring, keeping its original layout."""
        literal = self.source.segment(docstring.value)
        indent = self.source.indent_of(docstring.lineno)
        if not self.source.starts_line(docstring):
            indent += " " * 4
        newline = self.source.newline
        block = indent_block(render(MAX_LINE_LENGTH - len(indent)), indent)

        quote_start = len(literal) - len(literal.lstrip("rRuUbBfF"))
        prefix = literal[:quote_start]
        if "r" in prefix.lower() or not literal[quote_start:].startswith('"""') or not literal.endswith('"""'):
            # Unusual literal: rebuild it from its value.
            constant = docstring.value
            assert isinstance(constant, ast.Constant) and isinstance(constant.value, str)
            value = inspect.cleandoc(constant.value)
            prefix = ""
            lines = ["", *indent_block(escape_docstring(value).splitlines(), indent)] if value else [""]
        else:
            lines = literal[quote_start + 3 : -3].split(newline)
        lines = insert_block(lines, block, before_heading=before_heading)
        replacement = f'{prefix}"""{newline.join(lines)}{newline}{indent}"""'
        self.edits.append(Edit(self.source.start(docstring.value), self.source.end(docstring.value), replacement))


def apply_edits(data: bytes, edits: Iterable[Edit]) -> bytes:
    result = data
    previous_start = len(data) + 1
    for edit in sorted(edits, key=lambda edit: (edit.start, edit.end), reverse=True):
        if edit.end > previous_start:
            raise ConversionError(f"overlapping edits at byte {edit.start}")
        result = result[: edit.start] + edit.text.encode() + result[edit.end :]
        previous_start = edit.start
    return result


def used_names(tree: ast.Module) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            counts[node.id] = counts.get(node.id, 0) + 1
    return counts


def remove_unused_imports(data: bytes, before: dict[str, int]) -> bytes:
    """
    Remove top-level `annotated_doc` imports that are unused, and `Annotated` imports whose
    last usage was removed by the conversion.
    """
    source = Source(data)
    tree = ast.parse(data)
    after = used_names(tree)

    def removable(module: str | None, alias: ast.alias) -> bool:
        local = alias.asname or alias.name.partition(".")[0]
        if after.get(local, 0):
            return False
        if module == DOC_MODULE or (module is None and alias.name.partition(".")[0] == DOC_MODULE):
            return True
        return module in ANNOTATED_MODULES and alias.name == "Annotated" and before.get(local, 0) > 0

    edits: list[Edit] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.ImportFrom):
            module = stmt.module if stmt.level == 0 else None
            keep = [alias for alias in stmt.names if module is None or not removable(module, alias)]
        elif isinstance(stmt, ast.Import):
            keep = [alias for alias in stmt.names if not removable(None, alias)]
        else:
            continue
        if len(keep) == len(stmt.names):
            continue
        if keep:
            stmt.names = keep
            edits.append(Edit(source.start(stmt), source.end(stmt), ast.unparse(stmt)))
        else:
            start = source.line_starts[stmt.lineno - 1]
            end_lineno = stmt.end_lineno or stmt.lineno
            end = source.line_starts[end_lineno] if end_lineno < len(source.line_starts) else len(data)
            edits.append(Edit(start, end, ""))
    return apply_edits(data, edits)


def remaining_doc_usages(tree: ast.Module) -> Iterator[ast.Call]:
    names = Names(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and names.is_doc(node):
            yield node


def convert_file(path: Path) -> bool:
    data = path.read_bytes()
    tree = ast.parse(data, filename=str(path))
    converter = Converter(path, Source(data), tree)
    converter.run()

    result = remove_unused_imports(apply_edits(data, converter.edits), used_names(tree))
    if result == data:
        return False
    new_tree = ast.parse(result, filename=str(path))
    for call in remaining_doc_usages(new_tree):
        print(f"{path}:{call.lineno}: Doc() left in place (not a top-level Annotated metadata)", file=sys.stderr)
    _ = path.write_bytes(result)
    return True


def iter_files(paths: Iterable[Path]) -> Iterator[Path]:
    for path in paths:
        if path.is_dir():
            yield from sorted(file for pattern in ("*.py", "*.pyi") for file in path.rglob(pattern))
        else:
            yield path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert annotated_doc.Doc metadata into plain docstrings.")
    _ = parser.add_argument("paths", nargs="*", type=Path, default=[Path("typings")], help="files or directories")
    paths = cast("list[Path]", parser.parse_args(argv).paths)

    changed = 0
    try:
        for path in iter_files(paths):
            if convert_file(path):
                changed += 1
                print(f"converted {path}")
    except ConversionError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"{changed} file(s) converted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
