# v1 Git 提交计划（由你手动执行）

> 约定：仓库已在 `main` 分支初始化；所有 commit/tag/push 由你执行。下面给出建议的拆分方式。你可以合并相邻提交，也可以分到多天完成——**不要一天之内生成全部历史**，报告需要真实的版本痕迹。

## 0. 提交前检查

```bash
cd E:/collage/_project/算法课程设计
python -m pytest -q
python run.py --help
git status
```

确认 `node_modules/`、`~$*.docx`、`results/run_*` 没有被 `git add`。`.gitignore` 已排除它们。

## 1. 建议的提交序列

```bash
# 1) 项目骨架 + 课程材料
git add .gitignore README.md requirements.txt pyproject.toml config/default.yaml run.py
git add data/campus.json scripts/build_campus.py
git add "算法课程设计通知及报告模版2026.docx" "选题.md"
git commit -m "chore: init project skeleton, config, campus map and course materials"

# 2) 数据模型与 IO
git add src/campus_express/__init__.py src/campus_express/models.py src/campus_express/io.py
git add tests/conftest.py tests/test_models_io.py
git commit -m "feat(models): dataclasses, time windows, json io and validation"

# 3) 校园路网与 Dijkstra
git add src/campus_express/graph.py tests/test_graph.py
git commit -m "feat(graph): campus road network and dijkstra shortest paths"

# 4) 可复现数据生成
git add src/campus_express/data_gen.py data/packages_100.json data/packages_300.json data/packages_500.json
git commit -m "feat(datagen): seeded 100/300/500 package datasets and task aggregation"

# 5) 分拣基线
git add src/campus_express/sorting/__init__.py src/campus_express/sorting/common.py src/campus_express/sorting/baselines.py
git add tests/test_sorting.py
git commit -m "feat(sorting): grid and sweep baselines with metrics"

# 6) K-Means++ 与容量约束
git add src/campus_express/sorting/kmeans.py
git commit -m "feat(sorting): kmeans++ and capacity-aware assignment"

# 7) 分拣局部搜索与完整流水线
git add src/campus_express/sorting/local_search.py src/campus_express/solver.py
git commit -m "feat(sorting): relocate/swap local search and sorting pipeline"

# 8) 路径构造基线
git add src/campus_express/routing/__init__.py src/campus_express/routing/common.py src/campus_express/routing/baselines.py
git add tests/test_routing.py
git commit -m "feat(routing): schedule, nn/edd and cheapest insertion"

# 9) Clarke-Wright 与局部搜索
git add src/campus_express/routing/savings.py src/campus_express/routing/local_search.py
git commit -m "feat(routing): clarke-wright, 2-opt, or-opt and inter-route moves"

# 10) ALNS
git add src/campus_express/routing/alns.py
git commit -m "feat(routing): minimal alns with sa and adaptive operator weights"

# 11) 精确验证
git add src/campus_express/routing/exact.py tests/test_exact.py
git commit -m "feat(exact): held-karp and branch-and-bound time-window validation"

# 12) CLI 与集成测试
git add src/campus_express/cli.py src/campus_express/__main__.py tests/test_integration.py tests/test_edge_cases.py
git commit -m "feat(cli): subcommands and interactive menu; integration tests"

# 13) 实验与图
git add experiments/run_benchmark.py docs/report/figures.py
git commit -m "exp: benchmark matrix and report figures"

# 14) 实验结果
git add results/metrics.csv results/summary.json results/convergence docs/report/figures
git commit -m "exp: v1 metrics, convergence logs and figures"

# 15) 报告流水线
git add docs/report/js docs/report/prepare_base.py docs/report/merge_into_template.py docs/report/sample_body.md
git commit -m "build(report): body-only docx pipeline and template merge"

# 16) 报告正文
git add docs/report/report.md docs/report/report_template.md
git add "docs/算法_班级_学号_姓名.docx" "docs/算法_班级_学号_姓名.pdf"
git commit -m "docs(report): v1 report draft, figures and pdf"

# 17) 开发文档
git add docs/DEVLOG.md docs/GIT_COMMIT_PLAN.md docs/code_walkthrough.md docs/personalization_checklist.md
git commit -m "docs: devlog, code walkthrough and personalization checklist"

# 18) 版本标签
git log --graph --oneline --decorate --all
git tag -a v1.0.0 -m "v1: core algorithms, tests, experiments and report draft"
```

## 2. 提交后生成 Git 日志图

```bash
python scripts/make_git_log_figure.py
# 然后重新构建报告，替换占位图：
python docs/report/build_report.py --git-log docs/report/figures/git_log.png
```

如果还没有写 `build_report.py`，先手动把 `docs/report/figures/git_log.png` 插入报告，或在 Word 中替换占位图。

## 3. 推送到 GitHub

```bash
git remote add origin <你的仓库地址>
git push -u origin main
git push origin v1.0.0
```

## 4. v1 之后

- 先确认 v1 的代码、测试、报告和指标。
- 确认后再创建 `dev` 分支做 v2（终端图形界面）。**不要提前设计 v2/v3。**
- 每次大版本结束都停下，由你手动 commit/tag/push。

## 5. 提交信息风格

建议英文前缀 + 中文摘要，例如：

```text
feat(sorting): K-Means++ 与容量约束分配
feat(routing): 最小 ALNS（random/Shaw + greedy/regret-2）
test: 100/300/500 端到端与边界用例
docs(report): v1 报告正文与图表
```

提交信息不必与上面完全一致；关键是能看出“每个提交解决了什么问题”。
