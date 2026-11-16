# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import analysis, norm
from .engine import run_variant
from .model import Model, ModelError, load_model
from .reach import (Goal, check_same_dictionaries, find_base, load_goals, parse_goal_text,
                    reach_all)
from .reach import render_markdown as reach_markdown
from .reach import render_text as reach_text
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
    """Print the kinds and executors used in no variant.

    :param model: the model.
    :return: exit code.
    :rtype: int
    """
    for k in analysis.unused_kinds(model):
        print(f"kind: {k}")
    for x in analysis.unused_executors(model):
        print(f"executor: {x}")
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


def cmd_reach(paths: list[Path], goal_texts: list[str], goal_files: list[Path], base: str | None,
              batch: int, markdown: bool, output: Path | None) -> int:
    """Measure the stretches of all variants up to each goal.

    :param paths: model files with the same dictionaries.
    :param goal_texts: goals as ``Entity/axis=value; …``.
    :param goal_files: JSON files of named goals.
    :param base: base variant label for the comparison, or ``None``.
    :param batch: batch size for the cost.
    :param markdown: print Markdown instead of text.
    :param output: output file, or ``None`` for stdout.
    :return: exit code.
    :rtype: int
    """
    models = [(p.stem, load_model(p)) for p in paths]
    check_same_dictionaries(models)
    goals: list[Goal] = [parse_goal_text(t) for t in goal_texts]
    for f in goal_files:
        goals += load_goals(f)
    if not goals:
        raise ModelError("no goal: use --goal or --goals")
    results = []
    for g in goals:
        reaches = reach_all(models, g, batch)
        results.append((g, reaches, find_base(reaches, base) if base else None))
    if markdown:
        text = reach_markdown(results, batch)
    else:
        text = "".join(reach_text(g, r, b) for g, r, b in results)
    if output:
        output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


def cmd_norm(model: Model, norm_path: Path | None, slices_path: Path | None, output: Path | None,
             json_path: Path | None) -> int:
    """Labour and skips of all variants by a normalization file.

    :param model: the model.
    :param norm_path: normalization JSON file.
    :param slices_path: named slices JSON file, or ``None`` for the final slice only.
    :param output: Markdown output file, or ``None`` for stdout.
    :param json_path: JSON output file, or ``None``.
    :return: exit code.
    :rtype: int
    """
    if norm_path is None:
        raise ModelError("norm needs --norm")
    nrm = norm.load_normalization(norm_path)
    named = norm.load_slices(slices_path) if slices_path else []
    results = norm.norm_all(model, nrm, named)
    text = norm.render_markdown(model, nrm, results)
    if output:
        output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    if json_path:
        json_path.write_text(json.dumps(norm.to_json(model, nrm, results), ensure_ascii=False, indent=1)
                             + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    :param argv: arguments without the program name.
    :return: exit code.
    :rtype: int
    """
    p = argparse.ArgumentParser(prog="process_paths", description="Path model checks and output.")
    p.add_argument("command", choices=["check", "counts", "split", "variants", "unused", "same",
                                       "cost", "markdown", "reach", "norm"])
    p.add_argument("model", type=Path, nargs="+",
                   help="model JSON file; reach accepts several with the same dictionaries")
    p.add_argument("--goal", action="append", default=[],
                   help="reach: goal 'Entity/axis=value; Entity/axis=value' (repeatable)")
    p.add_argument("--goals", type=Path, action="append", default=[],
                   help="reach: JSON file {name: [[entity, axis, value], ...]} (repeatable)")
    p.add_argument("--base", help="reach: base variant (code, or file/code for several models)")
    p.add_argument("--md", action="store_true", help="reach: Markdown tables instead of text")
    p.add_argument("-o", "--output", type=Path, help="markdown, reach, norm: output file (default: stdout)")
    p.add_argument("--norm", type=Path, help="norm: normalization JSON file")
    p.add_argument("--slices", type=Path, help="norm: named slices JSON file")
    p.add_argument("--json", type=Path, dest="json_out", help="norm: JSON output file")
    p.add_argument("--batch", type=int, default=analysis.DEFAULT_BATCH, help="cost: batch size")
    a = p.parse_args(argv)
    try:
        if a.command == "reach":
            return cmd_reach(a.model, a.goal, a.goals, a.base, a.batch, a.md, a.output)
        if len(a.model) != 1:
            raise ModelError(f"{a.command} takes one model file")
        model = load_model(a.model[0])
        if a.command == "markdown":
            text = render_markdown(model)
            if a.output:
                a.output.write_text(text, encoding="utf-8")
            else:
                sys.stdout.write(text)
            return 0
        if a.command == "norm":
            return cmd_norm(model, a.norm, a.slices, a.output, a.json_out)
        if a.command == "cost":
            return cmd_cost(model, a.batch)
        return {"check": cmd_check, "counts": cmd_counts, "split": cmd_split, "variants": cmd_variants,
                "unused": cmd_unused, "same": cmd_same}[a.command](model)
    except ModelError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
