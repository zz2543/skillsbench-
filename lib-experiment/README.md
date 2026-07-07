# lib-experiment — 库化技能基线实验

**课题**：《库化部署下智能体技能的组合干扰》第一阶段——实验初始化 + 库化基线测量。
（研究计划见仓库根目录 `选题A_开题报告_库化技能组合干扰.html`。）

## 这一步做什么

官方 [SkillsBench](https://github.com/benchflow-ai/skillsbench) 的原生协议是"每个任务只装它自己的 skill"。本实验把**全部任务的 skill 合并成一个统一的库**，让 agent 面对全量 skill 元数据**自己选择**要用哪些（模拟 Anthropic 渐进式披露的真实库化部署），测量"库化后 agent 执行效果的变化"。

- **Agent 运行时**：OpenHands（与官方 DeepSeek V4 Pro 榜单同一 harness，保证可比）
- **模型**：`deepseek-v4-pro`（DeepSeek API）
- **规模**：跨领域分层选 10 个任务
- **条件**：`no-skill`（floor）与 `library`（全量库化自选）
- **对比基准**：官方 SkillsBench 榜单的 DeepSeek V4 Pro 得分
- **本阶段不做**：冲突检测 / CASL / 交互矩阵（后续阶段）

## 目录

```
scripts/    build_library / select_subset / run_eval / collect_results / fetch_baseline / sanitize
config/     OpenHands + DeepSeek 配置模板（不含真钥）
data/       library/(派生，gitignore) · subset_10.json · official_baseline.json
results/    runs/<task>/<cond>/ 的 reward、sanitized trajectory、token 日志 · summary.json
report/     index.html 可视化报告
```

上游基准克隆在同级目录 `../skillsbench-upstream/`（不纳入本仓库）。

## 复现步骤

```bash
# 0. 前置：Docker daemon 运行；uv tool install benchflow；克隆 ../skillsbench-upstream
# 1. 构造库化数据 + 子集 + 基准
python scripts/build_library.py
python scripts/select_subset.py
python scripts/fetch_baseline.py
# 2. 跑评测（DeepSeek key 从 gitignored ../DeepSeek-api 读取，仅注入运行时 env）
python scripts/run_eval.py
# 3. 汇总 + 报告
python scripts/collect_results.py
open report/index.html
```

## 安全

`DeepSeek-api`（含真实密钥）已被根目录 `.gitignore` 排除，**绝不提交**。所有 trajectory/日志经 `scripts/sanitize.py` 打码后才入库。
