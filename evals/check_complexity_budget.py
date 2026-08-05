#!/usr/bin/env python3
"""Keep the deterministic evidence surface small and honestly counted.

Contract tables already expose every example and assertion.  Python fixtures
historically hid many predicates behind one manifest row, so their final
pass/fail expression is expanded through local boolean assignments.  This is
an outcome count, not a claim that every AST node is a separate product test.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import sys

from _check_support import ROOT, run, load_evals  # noqa: E402,F401
from _check_support import validate_contract_table  # noqa: E402


MAX_EXECUTABLE_EXAMPLES = 80
MAX_EXPANDED_OUTCOME_PREDICATES = 400
CONTRACT_FAMILIES = (
    "scanner-examples",
    "preservation-examples",
    "maintenance-examples",
)
CONTRACT_WRAPPERS = {
    "evals/check_scanner_contract.py",
    "evals/check_preservation_contract.py",
    "evals/check_maintenance_contract.py",
}
META_CHECKS = {"evals/check_complexity_budget.py"}


def _command_script(row: dict) -> str | None:
    command = row.get("command")
    if not isinstance(command, list):
        return None
    return next(
        (part for part in command if isinstance(part, str) and part.endswith(".py")),
        None,
    )


def _expanded_fixture_predicates_from_source(source: str, label: str) -> int:
    """Expand a canonical final outcome through assignments and local helpers."""
    tree = ast.parse(source, filename=label)
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    main = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "main"
        ),
        None,
    )
    if main is None:
        raise RuntimeError(f"{label}: executable check needs main()")

    assignments_by_scope: dict[str, dict[str, ast.expr]] = {}
    for function_name, function in functions.items():
        scoped: dict[str, ast.expr] = {}
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                scoped[node.targets[0].id] = node.value
            elif (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.value is not None
            ):
                scoped[node.target.id] = node.value
        assignments_by_scope[function_name] = scoped
    def count(
        node: ast.AST,
        scope: str = "main",
        seen_names: frozenset[tuple[str, str]] = frozenset(),
        seen_functions: frozenset[str] = frozenset(),
    ) -> int:
        if isinstance(node, ast.IfExp):
            return count(node.test, scope, seen_names, seen_functions)
        if isinstance(node, ast.BoolOp):
            return sum(
                count(value, scope, seen_names, seen_functions)
                for value in node.values
            )
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return count(node.operand, scope, seen_names, seen_functions)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.BitAnd, ast.BitOr)):
            return count(node.left, scope, seen_names, seen_functions) + count(
                node.right, scope, seen_names, seen_functions
            )
        if isinstance(node, ast.Compare):
            if (
                len(node.ops) == 1
                and isinstance(node.ops[0], (ast.Eq, ast.Is))
                and isinstance(node.left, (ast.List, ast.Tuple))
                and isinstance(node.comparators[0], (ast.List, ast.Tuple))
                and len(node.left.elts) == len(node.comparators[0].elts)
            ):
                return sum(
                    count(value, scope, seen_names, seen_functions)
                    for value in node.left.elts
                )
            return max(1, len(node.ops))
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in {"all", "any"}:
                if node.args and isinstance(node.args[0], (ast.List, ast.Tuple, ast.Set)):
                    return sum(
                        count(value, scope, seen_names, seen_functions)
                        for value in node.args[0].elts
                    )
                if node.args and isinstance(node.args[0], ast.GeneratorExp):
                    generator = node.args[0]
                    multiplier = 1
                    for clause in generator.generators:
                        if isinstance(clause.iter, (ast.List, ast.Tuple, ast.Set)):
                            multiplier *= len(clause.iter.elts)
                    return multiplier * count(
                        generator.elt, scope, seen_names, seen_functions
                    )
            if (
                isinstance(node.func, ast.Name)
                and node.func.id in {"bool", "int"}
                and node.args
            ):
                return count(node.args[0], scope, seen_names, seen_functions)
            if (
                isinstance(node.func, ast.Name)
                and node.func.id in functions
                and node.func.id not in seen_functions
            ):
                return function_outcome(
                    node.func.id, seen_functions | {node.func.id}
                )
            return 1
        scoped_assignments = assignments_by_scope.get(scope, {})
        if (
            isinstance(node, ast.Name)
            and node.id in scoped_assignments
            and (scope, node.id) not in seen_names
        ):
            return count(
                scoped_assignments[node.id],
                scope,
                seen_names | {(scope, node.id)},
                seen_functions,
            )
        return 1

    def function_outcome(
        function_name: str, seen_functions: frozenset[str] = frozenset()
    ) -> int:
        function = functions[function_name]
        returns = [
            child
            for child in ast.walk(function)
            if isinstance(child, ast.Return) and child.value is not None
        ]
        if not returns:
            raise RuntimeError(f"{label}: {function_name}() needs an explicit outcome")
        total = 0
        guarded_returns: set[int] = set()
        for branch in ast.walk(function):
            if not isinstance(branch, ast.If):
                continue
            terminals = [
                child
                for statement in branch.body
                for child in ast.walk(statement)
                if isinstance(child, (ast.Return, ast.Raise))
            ]
            if not terminals:
                continue
            total += count(
                branch.test,
                function_name,
                frozenset(),
                seen_functions,
            )
            for terminal in terminals:
                if isinstance(terminal, ast.Return):
                    guarded_returns.add(id(terminal))
                    if terminal.value is not None and not isinstance(
                        terminal.value, ast.Constant
                    ):
                        total += count(
                            terminal.value,
                            function_name,
                            frozenset(),
                            seen_functions,
                        )
        final_return = max(returns, key=lambda node: node.lineno)
        if id(final_return) not in guarded_returns:
            value = final_return.value
            if isinstance(value, ast.IfExp):
                total += count(
                    value.test, function_name, frozenset(), seen_functions
                )
            elif not isinstance(value, ast.Constant):
                total += count(value, function_name, frozenset(), seen_functions)
        return max(1, total)

    return function_outcome("main")


def _expanded_fixture_predicates(path: Path) -> int:
    return _expanded_fixture_predicates_from_source(
        path.read_text(encoding="utf-8"), str(path)
    )


def _verify_counter() -> None:
    bundled = """
def main():
    ok = left and right
    return 0 if ok else 1
"""
    helper = """
def packed():
    ok = left and right and center
    return ok
def main():
    return 0 if packed() else 1
"""
    generator = """
def main():
    return 0 if all(item for item in (left, right, center)) else 1
"""
    bitwise = """
def main():
    return 0 if left & right & center else 1
"""
    tuple_compare = """
def main():
    return 0 if (left, right, center) == (True, True, True) else 1
"""
    helper_early_return = """
def packed():
    if left:
        return right
    return center
def main():
    return 0 if packed() else 1
"""
    early_return = """
def main():
    if ok:
        return 0
    return 1
"""
    if _expanded_fixture_predicates_from_source(bundled, "bundled") != 2:
        raise RuntimeError("complexity counter failed to expand a bundled assignment")
    if _expanded_fixture_predicates_from_source(helper, "helper") != 3:
        raise RuntimeError("complexity counter failed to expand a local helper")
    for source, name in (
        (generator, "generator"),
        (bitwise, "bitwise"),
        (tuple_compare, "tuple-compare"),
    ):
        if _expanded_fixture_predicates_from_source(source, name) != 3:
            raise RuntimeError(f"complexity counter failed to expand {name}")
    if _expanded_fixture_predicates_from_source(early_return, "early-return") != 1:
        raise RuntimeError("complexity counter failed to expand early-return packaging")
    if (
        _expanded_fixture_predicates_from_source(
            helper_early_return, "helper-early-return"
        )
        != 3
    ):
        raise RuntimeError("complexity counter failed to expand helper early returns")


def main() -> int:
    try:
        _verify_counter()
        script_rows = [row for row in load_evals() if row.get("target") == "script"]
        nested_examples: list[dict] = []
        hidden_wrappers: list[str] = []
        for family in CONTRACT_FAMILIES:
            path = ROOT / "evals" / "fixtures" / "contracts" / f"{family}.json"
            table = json.loads(path.read_text(encoding="utf-8"))
            examples = validate_contract_table(family, table, str(path))
            nested_examples.extend(examples)
            hidden_wrappers.extend(
                row["id"] for row in examples if row.get("category") == "contract_batch"
            )
    except (OSError, UnicodeError, json.JSONDecodeError, RuntimeError, SyntaxError) as exc:
        print(f"complexity budget setup error: {exc}", file=sys.stderr)
        return 2

    executable_rows: list[tuple[dict, str]] = []
    missing_scripts: list[str] = []
    for row in script_rows:
        script = _command_script(row)
        if script is None:
            missing_scripts.append(row["id"])
            continue
        if script not in CONTRACT_WRAPPERS | META_CHECKS:
            executable_rows.append((row, script))

    expanded_by_fixture = {
        row["id"]: _expanded_fixture_predicates(ROOT / script)
        for row, script in executable_rows
    }
    example_count = len(nested_examples) + len(executable_rows)
    predicate_count = sum(
        len(row.get("assertions", [])) for row in nested_examples
    ) + sum(expanded_by_fixture.values())

    print(f"executable examples <= {MAX_EXECUTABLE_EXAMPLES}: {example_count}")
    print(
        "expanded outcome predicates <= "
        f"{MAX_EXPANDED_OUTCOME_PREDICATES}: {predicate_count}"
    )
    print(
        "fixture predicates: "
        + ", ".join(
            f"{case_id}={count}"
            for case_id, count in sorted(expanded_by_fixture.items())
        )
    )
    print("counter self-test: bundled=expanded helper=expanded early-return=rejected")
    if hidden_wrappers:
        print("nested aggregate wrappers: " + ", ".join(sorted(hidden_wrappers)))
    if missing_scripts:
        print("script rows without Python entrypoint: " + ", ".join(missing_scripts))
    return int(
        example_count > MAX_EXECUTABLE_EXAMPLES
        or predicate_count > MAX_EXPANDED_OUTCOME_PREDICATES
        or bool(hidden_wrappers)
        or bool(missing_scripts)
    )


if __name__ == "__main__":
    raise SystemExit(main())
