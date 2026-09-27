"""Command-line interface."""

from __future__ import annotations

import os

# Limit BLAS threads before NumPy/Pandas/SciPy import (Windows OpenBLAS OOM fix).
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_var, "4")

import logging
from typing import Optional

import typer

app = typer.Typer(help="India district-wise rainfall maps (NDAP/IMD)")


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging"),
) -> None:
    _setup_logging(verbose)


@app.command("a-fix")
def cmd_a_fix() -> None:
    from rainfall.a_fix import run_all_a_fix

    run_all_a_fix()


@app.command("audit")
def cmd_audit(
    sample: bool = typer.Option(False, "--sample", help="Use 5k sample CSV"),
) -> None:
    from rainfall.audit import run_audit

    run_audit(sample=sample)


@app.command("ingest")
def cmd_ingest(
    sample: bool = typer.Option(False, "--sample", help="Use 5k sample CSV"),
    force: bool = typer.Option(False, "--overwrite", help="Rebuild parquet"),
) -> None:
    from rainfall.io import ingest_command

    path = ingest_command(sample=sample, force=force)
    typer.echo(f"Parquet: {path}")


@app.command("validate")
def cmd_validate() -> None:
    from rainfall.validate_crosswalk import run_a1_validation

    print(run_a1_validation())


@app.command("paint-groups")
def cmd_paint_groups() -> None:
    from rainfall.paint_groups import build_paint_groups, reconcile_counts

    build_paint_groups()
    print(reconcile_counts())


@app.command("clean")
def cmd_clean(
    sample: bool = typer.Option(False, "--sample"),
    years: Optional[str] = typer.Option(None, "--years", help="Comma years e.g. 2021 or 2021,2022"),
    merge: bool = typer.Option(False, "--merge", help="Merge year checkpoints to final enriched"),
    all_years: bool = typer.Option(False, "--all", help="Full clean in one pass"),
    fresh: bool = typer.Option(False, "--fresh", help="Delete checkpoints and rebuild enriched"),
) -> None:
    from rainfall.m3_clean import merge_year_checkpoints, run_m3, run_m3_fresh

    year_list = [int(y.strip()) for y in years.split(",")] if years else None
    if merge:
        merge_year_checkpoints()
    elif all_years and fresh:
        run_m3_fresh(sample=sample)
    else:
        run_m3(years=year_list, sample=sample)


@app.command("verify")
def cmd_verify(sample: bool = typer.Option(False, "--sample")) -> None:
    from rainfall.verify import run_verify

    print(run_verify(sample=sample))


@app.command("p1-gate")
def cmd_p1_gate() -> None:
    from rainfall.p1_gate import print_dedupe_summary, run_p1_gate

    payload = run_p1_gate()
    print_dedupe_summary()
    print(payload)


@app.command("geo")
def cmd_geo(sample: bool = typer.Option(False, "--sample")) -> None:
    from rainfall.geo import run_geo_pipeline

    run_geo_pipeline()


@app.command("crosswalk")
def cmd_crosswalk(sample: bool = typer.Option(False, "--sample")) -> None:
    from rainfall.crosswalk import build_crosswalk_from_gpkg

    build_crosswalk_from_gpkg()


@app.command("duplicates")
def cmd_duplicates() -> None:
    from rainfall.duplicates import run_duplicates_analysis

    run_duplicates_analysis()


@app.command("finalize")
def cmd_finalize() -> None:
    from rainfall.m3_finalize import run_finalize

    run_finalize()


@app.command("gates")
def cmd_gates(part: str = typer.Option("all", "--part", help="a, b, c, or all")) -> None:
    from rainfall import gates

    if part in ("a", "all"):
        gates.print_part_a_gate()
    if part in ("b", "all"):
        gates.print_part_b_gate()
    if part in ("c", "all"):
        gates.print_part_c_gate()


@app.command("render")
def cmd_render(
    sample: bool = typer.Option(False, "--sample"),
    date: Optional[str] = typer.Option(None, "--date"),
    trial: bool = typer.Option(False, "--trial"),
    overwrite: bool = typer.Option(False, "--overwrite"),
) -> None:
    from rainfall.render import build_render_matrix, render_trial, run_trial_maps
    import pandas as pd
    from rainfall.config import load_config, resolve_path

    cfg = load_config()
    if trial:
        run_trial_maps(cfg)
        return
    en = pd.read_parquet(resolve_path(cfg["paths"]["processed_enriched"]))
    poly = pd.read_csv(resolve_path("data/processed/paint_group_polygons.csv"))
    build_render_matrix(en, poly)
    if date:
        d = pd.Timestamp(date)
        out = resolve_path("outputs/maps/trial") / f"rainfall_actual_{d.date()}.png"
        print(render_trial(d, out, cfg))


@app.command("video")
def cmd_video(sample: bool = typer.Option(False, "--sample")) -> None:
    typer.echo("video: not implemented (out of scope)")


@app.command("analytics")
def cmd_analytics(sample: bool = typer.Option(False, "--sample")) -> None:
    typer.echo("analytics: not implemented (out of scope)")


if __name__ == "__main__":
    app()
