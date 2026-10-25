# 提交前个性化检查清单

课程明确允许 AI 作为辅助工具，但禁止直接提交未修改的完整 AI 成品。请逐项完成并在报告/提交记录中体现：

## 代码

- [ ] 能独立解释 `graph.py` 的 Dijkstra 松弛过程与复杂度。
- [ ] 能解释 `sorting/kmeans.py` 的 K-Means++ 初始化、容量分配、溢出修复。
- [ ] 能解释 `sorting/local_search.py` 的 relocate/swap 与 `assignment_key` 的字典序。
- [ ] 能解释 `routing/savings.py` 的节约值公式与合并可行性检查。
- [ ] 能解释 `routing/local_search.py` 的 2-opt 反转与时间窗重算。
- [ ] 能解释 `routing/alns.py` 的 destroy/repair、SA 接受、自适应权重。
- [ ] 至少修改 3 处：注释、参数、变量名、测试用例或一处分枝逻辑。
- [ ] 至少新增 2 个自己的测试用例，并让它们通过。

## 报告

- [ ] 5.1 “问题与解决”写的是你实际遇到的报错/现象，不是泛泛而谈。
- [ ] 2.1 的“思路草稿”有你自己的取舍理由（为什么先试网格、为什么放弃某方案）。
- [ ] 4.3 的结果分析有你自己的解释（为什么 ALNS 在 500 件提升更大、为什么 2 辆车距离更长）。
- [ ] 图表题、正文引用、参考文献编号一致。
- [ ] 封面个人信息已填写；评分表保留空白。

## Git

- [ ] 提交分散在多天，提交信息能看出每步做了什么。
- [ ] 没有提交 `node_modules/`、`~$*.docx`、`results/run_*`。
- [ ] 打 `v1.0.0` 标签；Git 日志图来自真实提交。
- [ ] 能向老师解释任意一个 commit 的改动。

## 运行

```bash
python -m pytest -q
python run.py --help
python run.py solve --packages data/packages_300.json --method savings_2opt
python experiments/run_benchmark.py --quick
```
