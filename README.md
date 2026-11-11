# 校园快递智能分拣与路径规划

模拟一个校园快递分拣中心：30 个配送点、10 个分拣格口、100/300/500 件快递、4 名快递员。系统完成两件事：

1. **分拣**：把配送点划分到 10 个格口（容量约束 + 工作量均衡）。
2. **配送**：为多名快递员规划从分拣中心出发、覆盖全部任务、满足时间窗与容量约束的路线。

算法链：

- 分拣：网格/行政分区 → Sweep → K-Means++ → 容量约束 K-Means + 局部搜索。
- 路径：最近邻 + EDD → Clarke-Wright 节约法 → 2-opt/Or-opt/跨路径 relocate/swap → 最小 ALNS。
- 验证：Held-Karp（无窗 n≤12）、分支限界/暴力（有窗 n≤9/8）。

## 快速开始

```bash
python -m pip install -r requirements.txt
python scripts/build_campus.py
python run.py gen-data --n 300 --seed 1
python run.py solve --packages data/packages_300.json --algorithm alns
python run.py                      # 交互菜单
python -m pytest -q
```

如果不想安装包，所有命令都通过 `run.py` 启动（它会把 `src/` 加入 `sys.path`）。测试使用 `pyproject.toml` 中的 `pythonpath = ["src"]`。

## 目录

```text
config/default.yaml       # 规模、容量、时间窗、算法参数
data/                     # campus.json + packages_*.json
src/campus_express/       # models / io / graph / data_gen / sorting / routing / solver / cli
tests/                    # 单元、集成、边界、精确验证
experiments/              # 批量实验与指标
docs/report/              # Markdown 报告、图、JS 管线、合并脚本
docs/DEVLOG.md            # 开发过程中的真实问题与修复
docs/GIT_COMMIT_PLAN.md   # 手动提交计划
docs/code_walkthrough.md  # 逐模块讲解
docs/personalization_checklist.md
scripts/                  # 数据构建、优化基准、Git 日志图
```

## 说明

- 测试数据由 `config/default.yaml` 与随机种子生成。
- 分拣聚类使用欧氏坐标作为代理，评价与局部搜索使用路网最短路距离。
- 主实验使用硬时间窗；压力实验使用软时间窗 + 迟到罚分。
