#!/usr/bin/env python3
"""
Convert `annotated_doc.Doc` metadata into plain docstrings.

- `Annotated[T, Doc("...")]` is unwrapped to `T`.
- `Annotated[T, X, Doc("...")]` keeps the other metadata: `Annotated[T, X]`.
- Documentation of function parameters is appended to the function docstring as a
  `## Parameters` section, with one `` ### `name` `` heading per parameter, following
  the Markdown headings (`## Example`, `## Usage`) already used in the docstrings.
- Documentation of variables and class attributes becomes an attribute docstring right
  after the declaration.
- `Doc` and `Annotated` imports that become unused are removed.

Only the edited spans are rewritten; the rest of each file is left untouched.

Usage:
    python scripts/doc_to_docstring.py [PATH ...]  # default: typings
"""

from __future__ import annotations

import argparse
import ast
import inspect
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

PARAMETERS_HEADING = "## Parameters"

DOC_MODULE = "annotated_doc"
ANNOTATED_MODULES = frozenset({"typing", "typing_extensions"})

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


class ConversionError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Edit:
    start: int
    end: int
    text: str


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

    def start(self, node: ast.AST) -> int:
        return self.offset(node.lineno, node.col_offset)  # type: ignore[attr-defined]

    def end(self, node: ast.AST) -> int:
        return self.offset(node.end_lineno, node.end_col_offset)  # type: ignore[attr-defined]

    def text(self, start: int, end: int) -> str:
        return self.data[start:end].decode()

    def segment(self, node: ast.AST) -> str:
        return self.text(self.start(node), self.end(node))

    def line_end(self, lineno: int) -> int:
        end = self.line_starts[lineno] - 1 if lineno < len(self.line_starts) else len(self.data)
        if end > 0 and self.data[end - 1 : end] == b"\r":
            end -= 1
        return end

    def indent_of(self, lineno: int) -> str:
        line = self.data[self.line_starts[lineno - 1] : self.line_end(lineno)].decode()
        return line[: len(line) - len(line.lstrip(" \t"))]

    def starts_line(self, node: ast.AST) -> bool:
        """Whether only whitespace precedes `node` on its first line."""
        line_start = self.line_starts[node.lineno - 1]  # type: ignore[attr-defined]
        return not self.data[line_start : self.start(node)].strip()


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


def indent_lines(text: str, indent: str, newline: str) -> str:
    return newline.join(indent + line if line.strip() else "" for line in text.splitlines())


def docstring_literal(text: str, indent: str, newline: str) -> str:
    body = indent_lines(escape_docstring(text), indent, newline)
    return f'"""{newline}{body}{newline}{indent}"""'


def get_docstring(body: list[ast.stmt], index: int) -> ast.Expr | None:
    if index < len(body):
        stmt = body[index]
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
            return stmt
    return None


class Converter:
    def __init__(self, path: Path, source: Source, tree: ast.Module) -> None:
        self.path = path
        self.source = source
        self.names = Names(tree)
        self.tree = tree
        self.edits: list[Edit] = []

    def location(self, node: ast.AST) -> str:
        return f"{self.path}:{node.lineno}"  # type: ignore[attr-defined]

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
                body = getattr(node, field, None)
                if isinstance(body, list):
                    for index, stmt in enumerate(body):
                        if isinstance(stmt, ast.AnnAssign):
                            self.convert_variable(body, index, stmt)

    def convert_function(self, function: FunctionNode) -> None:
        arguments = function.args
        parameters: list[tuple[str, ast.arg]] = [
            *((arg.arg, arg) for arg in (*arguments.posonlyargs, *arguments.args)),
            *(() if arguments.vararg is None else ((f"*{arguments.vararg.arg}", arguments.vararg),)),
            *((arg.arg, arg) for arg in arguments.kwonlyargs),
            *(() if arguments.kwarg is None else ((f"**{arguments.kwarg.arg}", arguments.kwarg),)),
        ]
        sections: list[str] = []
        for name, arg in parameters:
            text = self.strip_doc(arg.annotation)
            if text is not None:
                sections.append(f"### `{name}`\n\n{text}" if text else f"### `{name}`")
        if sections:
            self.append_docstring(function.body, 0, function, "\n\n".join([PARAMETERS_HEADING, *sections]))

    def convert_variable(self, body: list[ast.stmt], index: int, stmt: ast.AnnAssign) -> None:
        text = self.strip_doc(stmt.annotation)
        if text is None:
            return
        existing = get_docstring(body, index + 1)
        if existing is not None:
            self.extend_docstring(existing, text)
            return

        line_end = self.source.line_end(stmt.end_lineno or stmt.lineno)
        rest = self.source.text(self.source.end(stmt), line_end).strip()
        if rest and not rest.startswith("#"):
            raise ConversionError(f"{self.location(stmt)}: statement is followed by code on the same line")
        indent = self.source.indent_of(stmt.lineno)
        newline = self.source.newline
        self.edits.append(Edit(line_end, line_end, newline + indent + docstring_literal(text, indent, newline)))

    def append_docstring(self, body: list[ast.stmt], index: int, owner: FunctionNode, text: str) -> None:
        existing = get_docstring(body, index)
        if existing is not None:
            self.extend_docstring(existing, text)
            return

        first = body[index]
        newline = self.source.newline
        if self.source.starts_line(first):
            # Insert a new docstring on its own line before the first statement.
            indent = self.source.indent_of(first.lineno)
            line_start = self.source.line_starts[first.lineno - 1]
            literal = docstring_literal(text, indent, newline)
            self.edits.append(Edit(line_start, line_start, indent + literal + newline))
        else:
            # `def f(...): ...` -> move the body onto its own lines below the docstring.
            indent = self.source.indent_of(owner.lineno) + " " * 4
            start = self.source.start(first)
            while start > 0 and self.source.data[start - 1 : start] in (b" ", b"\t"):
                start -= 1
            literal = docstring_literal(text, indent, newline)
            self.edits.append(Edit(start, self.source.start(first), newline + indent + literal + newline + indent))

    def extend_docstring(self, docstring: ast.Expr, text: str) -> None:
        """Append paragraphs to an existing docstring, keeping its original layout."""
        literal = self.source.segment(docstring.value)
        indent = self.source.indent_of(docstring.lineno)
        if not self.source.starts_line(docstring):
            indent += " " * 4
        newline = self.source.newline
        quote_start = len(literal) - len(literal.lstrip("rRuUbBfF"))
        prefix = literal[:quote_start]
        if "r" in prefix.lower() or not literal[quote_start:].startswith('"""') or not literal.endswith('"""'):
            # Unusual literal: rebuild it from its value.
            value = inspect.cleandoc(docstring.value.value)  # type: ignore[attr-defined]
            combined = f"{value}\n\n{text}" if value else text
            replacement = docstring_literal(combined, indent, newline)
        else:
            content = literal[:-3].rstrip()
            added = indent_lines(escape_docstring(text), indent, newline)
            if content == literal[: quote_start + 3]:
                replacement = f'{content}{newline}{added}{newline}{indent}"""'
            else:
                replacement = f'{content}{newline}{newline}{added}{newline}{indent}"""'
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
    """Remove `Doc`/`Annotated` imports whose last usage was removed by the conversion."""
    source = Source(data)
    tree = ast.parse(data)
    after = used_names(tree)

    def removable(module: str | None, alias: ast.alias, *, from_import: bool) -> bool:
        local = alias.asname or alias.name.partition(".")[0]
        if from_import:
            relevant = module == DOC_MODULE or (module in ANNOTATED_MODULES and alias.name == "Annotated")
        else:
            relevant = alias.name == DOC_MODULE
        return relevant and before.get(local, 0) > 0 and after.get(local, 0) == 0

    edits: list[Edit] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.ImportFrom):
            keep = [alias for alias in stmt.names if not removable(stmt.module, alias, from_import=True)]
        elif isinstance(stmt, ast.Import):
            keep = [alias for alias in stmt.names if not removable(None, alias, from_import=False)]
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
    if not converter.edits:
        return False

    before = used_names(tree)
    result = remove_unused_imports(apply_edits(data, converter.edits), before)
    new_tree = ast.parse(result, filename=str(path))
    for call in remaining_doc_usages(new_tree):
        print(f"{path}:{call.lineno}: Doc() left in place (not a top-level Annotated metadata)", file=sys.stderr)
    path.write_bytes(result)
    return True


def iter_files(paths: Iterable[Path]) -> Iterator[Path]:
    for path in paths:
        if path.is_dir():
            yield from sorted(file for pattern in ("*.py", "*.pyi") for file in path.rglob(pattern))
        else:
            yield path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert annotated_doc.Doc metadata into plain docstrings.")
    parser.add_argument("paths", nargs="*", type=Path, default=[Path("typings")], help="files or directories")
    args = parser.parse_args(argv)

    changed = 0
    try:
        for path in iter_files(args.paths):
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
