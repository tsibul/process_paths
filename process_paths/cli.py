"""Command line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import analysis
from .engine import run_variant
from .model import Model, ModelError, load_model
from .render import render_markdown


def cmd_check(model: Model) -> int:
    """Validate the model, run all variants, run the split and word checks.

    :param model: the model.
    :return: exit code.
    :rtype: int
    """
    problems = []
    for v in model.variants:
        try:
            run_variant(model, v)
        except ModelError as exc:
            problems.append(str(exc))
    if not problems:
        problems += [f"same quadruple: {a} = {b}" for a, b in analysis.duplicate_kinds(model)]
        problems += [f"decomposable: {k} = {' + '.join(c)}" for k, c in analysis.decomposable_kinds(model)]
        hits = analysis.forbidden_hits(model, render_markdown(model))
        problems += [f"forbidden word: {w}" for w in hits]
    for p in problems:
        print(p)
    print("OK" if not problems else f"{len(problems)} problem(s)")
    return 0 if not problems else 1


def cmd_counts(model: Model) -> int:
    """Print the dictionary counts.

    :param model: the model.
    :return: exit code.
    :rtype: int
    """
    n = analysis.dictionary_counts(model)
    for key in ("entities", "axes", "values", "kinds", "executors", "instruments", "scopes"):
        print(f"{key}: {n[key]}")
    for e in model.entities:
        print(f"  {e.name}: axes {n['axes_by_entity'][e.name]}, values {n['values_by_entity'][e.name]}")
    return 0


def cmd_split(model: Model) -> int:
    """Print the split check.

    :param model: the model.
    :return: exit code.
    :rtype: int
    """
    dup = analysis.duplicate_kinds(model)
    dec = analysis.decomposable_kinds(model)
    for a, b in dup:
        print(f"same quadruple: {a} = {b}")
    for k, c in dec:
        print(f"decomposable: {k} = {' + '.join(c)}")
    print("OK" if not dup and not dec else "violations found")
    return 0 if not dup and not dec else 1


def cmd_variants(model: Model) -> int:
    """Print transitions and kinds per variant.

    :param model: the model.
    :return: exit code.
    :rtype: int
    """
    print("variant\ttransitions\tkinds")
    for code, title, a, b in analysis.variant_counts(model):
        print(f"{code} {title}\t{a}\t{b}")
    return 0


def cmd_unused(model: Model) -> int:
    """Print the kinds used in no variant.

    :param model: the model.
    :return: exit code.
    :rtype: int
    """
    for k in analysis.unused_kinds(model):
        print(k)
    return 0


def cmd_same(model: Model) -> int:
    """Print equal slices between variants (slice 0 is the initial one).

    :param model: the model.
    :return: exit code.
    :rtype: int
    """
    for r in analysis.identical_slices(model):
        if not r["full"] and not r["common"]:
            continue
        full = ", ".join(f"{i}={j}" for i, j in r["full"]) or "-"
        common = ", ".join(f"{i}={j}" for i, j in r["common"]) or "-"
        print(f"{r['a']} / {r['b']}: full {len(r['full'])} [{full}]; "
              f"on {r['common_axes']} common axes {len(r['common'])} [{common}]")
    return 0


def cmd_cost(model: Model, batch: int) -> int:
    """Print cost per document and safety per variant, and the batch-size run.

    :param model: the model.
    :param batch: batch size.
    :return: exit code.
    :rtype: int
    """
    for v in model.variants:
        cost = analysis.path_cost(model, v, batch)
        safe = analysis.path_safety(model, v)
        miss = "" if cost is not None else " (missing: " + ", ".join(analysis.cost_missing(model, v)) + ")"
        print(f"{v.code}: cost {'not set' if cost is None else cost}{miss}; "
              f"safety {'not set' if safe is None else safe}")
    ranking = analysis.cost_ranking(model)
    if ranking is None:
        print("batch-size run: not possible, costs not set")
    else:
        for n, codes in ranking.items():
            print(f"batch {n}: {', '.join(codes)}")
        print("order changes with batch size" if len({tuple(c) for c in ranking.values()}) > 1
              else "order does not change with batch size")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    :param argv: arguments without the program name.
    :return: exit code.
    :rtype: int
    """
    p = argparse.ArgumentParser(prog="process_paths", description="Path model checks and output.")
    p.add_argument("command", choices=["check", "counts", "split", "variants", "unused", "same",
                                       "cost", "markdown"])
    p.add_argument("model", type=Path, help="model JSON file")
    p.add_argument("-o", "--output", type=Path, help="markdown: output file (default: stdout)")
    p.add_argument("--batch", type=int, default=analysis.DEFAULT_BATCH, help="cost: batch size")
    a = p.parse_args(argv)
    try:
        model = load_model(a.model)
        if a.command == "markdown":
            text = render_markdown(model)
            if a.output:
                a.output.write_text(text, encoding="utf-8")
            else:
                sys.stdout.write(text)
            return 0
        if a.command == "cost":
            return cmd_cost(model, a.batch)
        return {"check": cmd_check, "counts": cmd_counts, "split": cmd_split, "variants": cmd_variants,
                "unused": cmd_unused, "same": cmd_same}[a.command](model)
    except ModelError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
