# 代码走读（v1）

> 目的：让你能逐模块解释代码，而不是把 AI 生成的成品直接交上去。建议对照源码读一遍，并把下面“可个性化”的点改成自己的写法。

## 1. 数据层

- `models.py`
  - `TimeWindow`：分钟制时间窗，`contains/overlaps`。
  - `Package`：包裹（目的地、重量、优先级、时间窗、时段 bucket）。
  - `Task`：按 `(配送点, 时间窗)` 聚合后的任务；`priority_score` 是包裹数加权优先级，避免 `max` 把特急信号抹平。
  - `Campus`：中心、30 个配送点、10 个格口、路网节点/边/接入边。
- `io.py`：JSON/YAML 读写与基础校验；时间统一存分钟，展示时格式化为 `HH:MM`。
- `data_gen.py`
  - `generate_packages`：按种子生成 100/300/500 件；先保证覆盖（n≥30 时每点至少 1 件），再按宿舍/教学/其他热度补足；生成后做容量/重量可行性校验。
  - `aggregate_tasks`：按 `(point, bucket)` 聚合；任务窗口取组内包裹窗口的**交集**，保留特急/加急的紧窗口。
- `graph.py`
  - 邻接表存路网；`dijkstra` 用 `heapq`，支持 `length_m`/`time_s` 两种权重。
  - `distance_matrix` 对中心 + 30 点做全源最短路，供分拣 TSP 代理和路径规划使用。

## 2. 分拣层

- `sorting/baselines.py`
  - `sort_grid`：按 x 排序切 10 段，忽略需求/容量，作为“行政分区”基线。
  - `sort_sweep`：按极角排序，用前缀和 + 分位点切 10 段，保证非空；仍可能容量溢出。
- `sorting/kmeans.py`
  - `_init_kmeanspp`：D² 采样初始化；重复坐标时退化为加权均匀采样。
  - `kmeanspp`：多起点、可选需求加权。
  - `_capacity_aware_assignment`：按需求降序，优先放入最近且有剩余容量的簇；否则放最近簇并记溢出。
  - `_repair_capacity`：把溢出簇的小点移到有空位的簇。
  - `capacitated_kmeans`：多起点 + 容量分配 + 溢出修复；`score_fn` 可按 TSP 代理选最优起点。
- `sorting/local_search.py`
  - `improve_assignment`：relocate/swap 两种邻域；目标 `TSP 代理 + cv_penalty×CV`，字典序比较 `(空簇, 溢出, 目标, CV)`；禁止把簇清空。
  - `sort_capacitated`：容量 K-Means + 局部搜索的完整入口。
- `sorting/common.py`
  - `evaluate_assignment`：簇内 TSP 代理（最近邻 + 2-opt）、CV、最大负载率、溢出、空簇、轮廓系数（辅助）。
  - `assignment_key`：先可行、再紧凑、再均衡。

## 3. 路径层

- `routing/common.py`
  - `schedule_route`：从中心出发，按任务顺序计算到达/等待/服务/回程；硬时间窗超时记 `feasible=False`，软窗只记 tardiness；同时检查容量、重量、班次。
  - `RoutingContext.evaluate`：汇总距离、makespan、准时率、优先级加权到达、负载 CV、未分配、目标值。
- `routing/baselines.py`
  - `nn_edd`：每名快递员反复选“可行且截止最早”的任务，装不下换人。
  - `cheapest_insertion`：按紧迫度排序，逐个插到最便宜的可行位置。
- `routing/savings.py`
  - `clarke_wright`：单点路线 → 按节约值合并（只合并端点）→ 路线池装进 4 名快递员；装不下时逐任务 cheapest insertion 兜底。
- `routing/local_search.py`
  - `two_opt_route`：反转子段，检查时间窗与距离改进。
  - `or_opt_route`：移动 1–3 个连续任务。
  - `relocate/swap`：跨路径移动/交换，整体评估目标。
  - `improve`：2-opt/Or-opt + 可选的跨路径搜索。
- `routing/alns.py`
  - destroy：`random_removal`（随机移除 q 个）、`shaw_removal`（距离+时间窗+优先级相关）。
  - repair：`greedy_insertion`、`regret2_insertion`；失败的插入进入 `unassigned`，候选解不可行则拒绝。
  - 接受：SA（T0=0.05·J0，Tend=0.001·J0，几何降温）。
  - 自适应：每 100 次按得分更新 destroy/repair 轮盘权重。
- `routing/exact.py`
  - `held_karp`：无时间窗 TSP，O(n²2^n)，n≤12。
  - `brute_force_tw` / `branch_and_bound_tw`：单路径硬时间窗，n≤8/9。
  - 只对单路径小规模声称最优性；多快递员不宣称全局最优。

## 4. 系统层

- `solver.py`
  - `build_context_from_data`：数据 → 路网 → 最短路矩阵 → 任务 → 4 名快递员 → `RoutingContext`。
  - `solve_sorting`：grid/sweep/kmeans/cap_kmeans/cap_ls。
  - `solve_routing`：nn/insertion/savings/savings_2opt/alns；ALNS 从 savings+2opt 与 insertion 中较好的一个出发。
  - `solve`：分拣 + 路径 + 指标 + 路线详情。
- `cli.py`
  - 子命令 `gen-data/sort/route/solve/inspect/benchmark`；无子命令时进入 `input()` 交互菜单。
- `experiments/run_benchmark.py`：E1–E8，输出 `results/metrics.csv` 与 `results/summary.json`。

## 5. 报告流水线

- `docs/report/js/build_paper.js`：改自你已有的 JS 论文管线；`--body-only --campus-template` 输出单节、无页码、H2/H3/H4 映射的正文。
- `docs/report/prepare_base.py`：保留模板封面/评分表/目录，删除通知与示例正文，重建 4 节 + `BODY_INSERT` 书签。
- `docs/report/merge_into_template.py`：Word COM 复制正文（排除末尾段落标记）、粘贴、更新 TOC 两遍、导出 PDF。
- `docs/report/figures.py`：从数据/结果生成全部图。
- `scripts/make_git_log_figure.py`：真实 `git log` 渲染为图。

## 6. 建议的个性化修改

1. 把 `data_gen.py` 里宿舍/教学热度、优先级比例改成你自己设定的值，并在报告里说明依据。
2. 给 `capacitated_kmeans` 增加一个你写的初始化策略（例如按象限撒点），对比原版。
3. 把 `alns.py` 的 `destroy_fraction`、SA 温度、权重更新系数调几组，记录哪组更好。
4. 在 `tests/` 里加 2–3 个你自己构造的边界用例（如“同一配送点两个不相交时间窗”）。
5. 重写报告 5.1 的“问题与解决”，用你实际调试时遇到的报错/现象，不要照抄 DEVLOG。
6. 至少手改关键函数的注释与变量名，确保你能不看稿解释 K-Means 容量分配、Savings 合并、2-opt 检查、ALNS 接受准则。
