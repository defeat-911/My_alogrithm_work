from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from campus_express.io import load_packages
from campus_express.solver import solve

ROOT = Path(__file__).resolve().parents[1]


def test_full_pipeline_100():
    result = solve(
        packages_path=ROOT / "data" / "packages_100.json",
        sorting_method="cap_ls",
        routing_method="savings_2opt",
    )
    assert result.n_packages == 100
    assert result.solution.metrics["feasible"] == 1.0
    assert result.solution.metrics["unassigned"] == 0
    assert sum(len(r.task_ids) for r in result.solution.routes) == result.n_tasks
    assert result.sorting.overflow(60) == 0
    assert result.sorting.empty_clusters() == 0
    assert "tsp_proxy_m" in result.sorting.metrics


def test_cli_help():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "run.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    assert proc.returncode == 0
    assert "gen-data" in proc.stdout


def test_cli_gen_data(tmp_path):
    out = tmp_path / "packages_20.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "run.py"),
            "gen-data",
            "--n",
            "20",
            "--seed",
            "5",
            "--out",
            str(out),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    assert proc.returncode == 0, proc.stderr
    assert out.exists()
    assert len(load_packages(out)) == 20
