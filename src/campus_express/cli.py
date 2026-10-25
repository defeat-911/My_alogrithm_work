"""Command-line interface and simple interactive menu."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from .data_gen import check_instance, generate_packages, save_dataset
from .io import load_campus, load_config, load_packages
from .solver import build_context, solve, solve_routing, solve_sorting

console = Console()


def _print_metrics(title: str, metrics: dict[str, Any]) -> None:
    table = Table(title=title, show_header=True, header_style="bold")
    table.add_column("指标", style="cyan")
    table.add_column("值", justify="right")
    for key in (
        "feasible",
        "n_packages",
        "n_tasks",
        "distance_km",
        "makespan_min",
        "on_time_rate",
        "tardiness_min",
        "priority_weighted_arrival",
        "load_cv",
        "unassigned",
        "objective",
        "runtime_s",
        "tsp_proxy_m",
        "load_cv",
        "overflow_packages",
        "empty_clusters",
    ):
        if key in metrics:
            value = metrics[key]
            if isinstance(value, float):
                table.add_row(key, f"{value:.4f}")
            else:
                table.add_row(key, str(value))
    console.print(table)


def cmd_gen_data(args: argparse.Namespace) -> int:
    campus = load_campus(args.campus)
    config = load_config(args.config)
    packages = generate_packages(campus, args.n, args.seed, config)
    report = check_instance(packages, campus, config)
    out = args.out or f"data/packages_{args.n}.json"
    save_dataset(campus, packages, args.n, args.seed, config, out)
    console.print(f"[green]wrote[/green] {out}")
    _print_metrics("instance feasibility", report)
    return 0


def cmd_sort(args: argparse.Namespace) -> int:
    ctx = build_context(
        campus_path=args.campus,
        packages_path=args.packages,
        config_path=args.config,
        couriers_count=args.couriers,
    )
    assignment = solve_sorting(ctx, method=args.method, seed=args.seed)
    title = f"sorting: {args.method}"
    _print_metrics(title, assignment.metrics)
    loads = Table(title="chute loads", show_header=True)
    loads.add_column("chute")
    loads.add_column("packages", justify="right")
    for i, load in enumerate(assignment.loads):
        loads.add_row(f"C{i + 1:02d}", str(load))
    console.print(loads)
    if args.out:
        payload = {
            "method": args.method,
            "labels": dict(sorted(assignment.labels.items())),
            "loads": assignment.loads,
            "metrics": assignment.metrics,
        }
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        console.print(f"[green]wrote[/green] {args.out}")
    return 0


def cmd_route(args: argparse.Namespace) -> int:
    ctx = build_context(
        campus_path=args.campus,
        packages_path=args.packages,
        config_path=args.config,
        couriers_count=args.couriers,
    )
    solution, alns_result = solve_routing(
        ctx, method=args.method, seed=args.seed, quick=args.quick
    )
    metrics = dict(solution.metrics)
    metrics["n_packages"] = len(ctx.packages)
    metrics["n_tasks"] = len(ctx.tasks)
    if alns_result:
        metrics["runtime_s"] = alns_result.runtime_s
        metrics["alns_iterations"] = alns_result.iterations
    _print_metrics(f"routing: {args.method}", metrics)
    if args.out:
        schedules = {
            route.courier_id: ctx.routing.schedule_route(
                route.courier_id, route.task_ids
            )
            for route in solution.routes
        }
        payload = {
            "method": args.method,
            "n_packages": len(ctx.packages),
            "n_tasks": len(ctx.tasks),
            "metrics": metrics,
            "routes": [
                {
                    "courier_id": route.courier_id,
                    "task_ids": route.task_ids,
                    "point_ids": [
                        ctx.routing.tasks[tid].point_id for tid in route.task_ids
                    ],
                    "load": schedules[route.courier_id].load,
                    "distance_m": schedules[route.courier_id].distance_m,
                    "end_time": schedules[route.courier_id].end_time,
                }
                for route in solution.routes
            ],
            "convergence": alns_result.convergence if alns_result else None,
        }
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        console.print(f"[green]wrote[/green] {args.out}")
    return 0


def cmd_solve(args: argparse.Namespace) -> int:
    result = solve(
        packages_path=args.packages,
        campus_path=args.campus,
        config_path=args.config,
        sorting_method=args.sorting,
        routing_method=args.method,
        couriers_count=args.couriers,
        seed=args.seed,
        quick=args.quick,
    )
    metrics = dict(result.solution.metrics)
    metrics["n_packages"] = result.n_packages
    metrics["n_tasks"] = result.n_tasks
    metrics["runtime_s"] = result.runtime_s
    _print_metrics("full pipeline", metrics)
    _print_metrics("sorting", result.sorting.metrics)
    if args.out:
        result.save(args.out)
        console.print(f"[green]wrote[/green] {args.out}")
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.result).read_text(encoding="utf-8"))
    metrics = payload.get("metrics", {})
    _print_metrics(f"result: {args.result}", metrics)
    if "sorting" in payload:
        _print_metrics("sorting", payload["sorting"].get("metrics", {}))
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    from experiments.run_benchmark import run_benchmark

    run_benchmark(
        scales=args.scales,
        seeds=args.seeds,
        out=args.out,
        quick=args.quick,
        couriers=args.couriers,
    )
    return 0


def _menu() -> int:
    while True:
        console.print("\n[bold]校园快递智能分拣与路径规划[/bold]")
        console.print("1. 生成测试数据")
        console.print("2. 运行分拣算法")
        console.print("3. 运行路径算法")
        console.print("4. 运行完整流水线")
        console.print("5. 查看结果文件")
        console.print("0. 退出")
        choice = input("请选择: ").strip()
        if choice == "0":
            return 0
        try:
            if choice == "1":
                n = int(input("包裹数 [100/300/500]: ") or "100")
                seed = int(input("随机种子 [1]: ") or "1")
                cmd_gen_data(
                    argparse.Namespace(
                        n=n,
                        seed=seed,
                        campus="data/campus.json",
                        config="config/default.yaml",
                        out=None,
                    )
                )
            elif choice in {"2", "3", "4"}:
                n = int(input("包裹数 [100/300/500]: ") or "300")
                seed = int(input("随机种子 [1]: ") or "1")
                couriers = int(input("快递员数 [4]: ") or "4")
                method = input(
                    "算法 [nn/insertion/savings/savings_2opt/alns]: "
                ).strip() or "alns"
                packages = f"data/packages_{n}.json"
                if not Path(packages).exists():
                    console.print(f"[red]{packages} 不存在，请先生成数据[/red]")
                    continue
                if choice == "2":
                    cmd_sort(
                        argparse.Namespace(
                            packages=packages,
                            campus="data/campus.json",
                            config="config/default.yaml",
                            method=method
                            if method in {"grid", "sweep", "kmeans", "cap_kmeans", "cap_ls"}
                            else "cap_ls",
                            seed=seed,
                            couriers=couriers,
                            out=None,
                        )
                    )
                elif choice == "3":
                    cmd_route(
                        argparse.Namespace(
                            packages=packages,
                            campus="data/campus.json",
                            config="config/default.yaml",
                            method=method,
                            seed=seed,
                            couriers=couriers,
                            quick=False,
                            out=None,
                        )
                    )
                else:
                    cmd_solve(
                        argparse.Namespace(
                            packages=packages,
                            campus="data/campus.json",
                            config="config/default.yaml",
                            method=method,
                            sorting="cap_ls",
                            seed=seed,
                            couriers=couriers,
                            quick=False,
                            out=None,
                        )
                    )
            elif choice == "5":
                path = input("结果 JSON 路径: ").strip()
                if path:
                    cmd_inspect(argparse.Namespace(result=path))
            else:
                console.print("[red]无效选项[/red]")
        except Exception as exc:  # pragma: no cover - interactive UX
            console.print(f"[red]错误: {exc}[/red]")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="campus-express",
        description="校园快递智能分拣与路径规划（v1）",
    )
    parser.add_argument("--campus", default="data/campus.json")
    parser.add_argument("--config", default="config/default.yaml")
    sub = parser.add_subparsers(dest="command")

    gen = sub.add_parser("gen-data", help="generate a reproducible package dataset")
    gen.add_argument("--n", type=int, default=100)
    gen.add_argument("--seed", type=int, default=1)
    gen.add_argument("--out", default=None)
    gen.set_defaults(func=cmd_gen_data)

    sort = sub.add_parser("sort", help="run a sorting algorithm")
    sort.add_argument("--packages", required=True)
    sort.add_argument(
        "--method",
        default="cap_ls",
        choices=["grid", "sweep", "kmeans", "cap_kmeans", "cap_ls"],
    )
    sort.add_argument("--seed", type=int, default=1)
    sort.add_argument("--couriers", type=int, default=None)
    sort.add_argument("--out", default=None)
    sort.set_defaults(func=cmd_sort)

    route = sub.add_parser("route", help="run a routing algorithm")
    route.add_argument("--packages", required=True)
    route.add_argument(
        "--method",
        default="alns",
        choices=["nn", "insertion", "savings", "savings_2opt", "alns"],
    )
    route.add_argument("--seed", type=int, default=1)
    route.add_argument("--couriers", type=int, default=None)
    route.add_argument("--quick", action="store_true")
    route.add_argument("--out", default=None)
    route.set_defaults(func=cmd_route)

    solve_cmd = sub.add_parser("solve", help="run sorting + routing")
    solve_cmd.add_argument("--packages", required=True)
    solve_cmd.add_argument(
        "--sorting",
        default="cap_ls",
        choices=["grid", "sweep", "kmeans", "cap_kmeans", "cap_ls"],
    )
    solve_cmd.add_argument(
        "--method",
        default="alns",
        choices=["nn", "insertion", "savings", "savings_2opt", "alns"],
    )
    solve_cmd.add_argument("--seed", type=int, default=1)
    solve_cmd.add_argument("--couriers", type=int, default=None)
    solve_cmd.add_argument("--quick", action="store_true")
    solve_cmd.add_argument("--out", default=None)
    solve_cmd.set_defaults(func=cmd_solve)

    inspect = sub.add_parser("inspect", help="print a saved result")
    inspect.add_argument("--result", required=True)
    inspect.set_defaults(func=cmd_inspect)

    bench = sub.add_parser("benchmark", help="run the experiment matrix")
    bench.add_argument("--scales", type=int, nargs="+", default=[100, 300, 500])
    bench.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    bench.add_argument("--couriers", type=int, default=None)
    bench.add_argument("--quick", action="store_true")
    bench.add_argument("--out", default="results/metrics.csv")
    bench.set_defaults(func=cmd_benchmark)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        return _menu()
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
