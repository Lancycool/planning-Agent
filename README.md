# 内容任务规划 Agent

项目对应考核题目 1。系统帮助运营人员在预算和截止时间内完成内容活动方案。

项目使用 Python、LangGraph、百炼模型和 SQLite。真实模型选择动作，程序校验约束并执行四类本地业务工具。离线入口使用固定规则模拟动作选择。脚本生成工具使用本地模板。所有费用、素材和工具耗时都是合成数据。

## 评审入口

仓库地址为 [Lancycool/planning-Agent](https://github.com/Lancycool/planning-Agent)。仓库目前公开。最终交付使用标签 `submission-2026-11-02`；评审者可以用 `git rev-parse HEAD` 获取检出版本的完整 commit SHA。完整提交说明见 [交付清单](docs/09-delivery.md)。

评审者可以先阅读 [验收结果](docs/03-evaluation.md)，再查看 [修复记录](docs/10-code-review-fixes.md)。项目保留每组输入、实际输出、Trace、实际费用表和检查结论。项目不要求评审者调用收费 API。开发环境的 55 项 Python 测试、独立 wheel 的 50 项核心测试和 3 项前端测试已经通过。15 组离线与 23 组真实模型运行均达到各自预期，并通过证据重算。

## 安装

开发者需要 Python 3.11 及以上。项目实际验证的环境使用 Windows 和 Python 3.12.13。开发者从仓库根目录运行：

```powershell
git clone git@github.com:Lancycool/planning-Agent.git
cd planning-Agent
git checkout submission-2026-11-02
uv --cache-dir .runtime/uv-cache sync --frozen --extra dev
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath env.sample -Destination .env
}
```

离线运行不需要密钥。在线运行需要开发者在 `.env` 填写 `DASHSCOPE_API_KEY`。模板包含 Base URL、模型 ID、超时和输出 token 上限。已有环境变量优先于 `.env`。项目不会把密钥写入输出或 Trace。

如果开发者没有 uv，开发者可以先建立虚拟环境，再执行 `python -m pip install -e ".[dev]"`。这个方式使用依赖范围；锁定版本复现需要使用 `uv.lock`。

## 运行

以下命令均从仓库根目录运行。固定时钟场景用于复现已过去的示例截止时间。

```powershell
# 离线：模型替身观察费用 12 超出预算 10，再改选费用 8 的方案。
.venv/Scripts/python.exe -m content_agent.cli --mode mock --input data/requests/replan.json --scenario data/scenarios/fixed-clock.json --output-dir .runtime/demo

# 在线：真实模型选择动作，API 会消耗额度。
.venv/Scripts/python.exe -m content_agent.cli --mode online --input data/requests/normal.json --scenario data/scenarios/fixed-clock.json --db .runtime/online.sqlite3 --output-dir .runtime/online-demo

# 网页：开发者打开 http://127.0.0.1:8765。
.venv/Scripts/python.exe -m content_agent.web
```

开发者需要在新业务任务中使用当前截止时间和新请求 ID。不带 `--scenario` 的任务使用当前带时区时间。Linux 和 macOS 用户需要把 `.venv/Scripts/python.exe` 换成 `.venv/bin/python`；项目尚未在这两个平台复跑。

CLI 在任务完成时返回退出码 0，在缺信息、未完成或输入无效时返回 2。CLI 输出 JSON。SQLite 保存实际方案。`--output-dir` 导出输入、输出、Trace、场景和已保存方案。复用目录时，程序会移除不属于新结果的旧方案文件。

系统用相同数据库、请求 ID 和输入识别重复执行。重复请求返回原结果，并标记 `replayed=true`。系统不会再次调用模型或收费。相同 ID 携带不同输入会返回 `REQUEST_CONFLICT`。网页在同一标签页内保留请求 ID，刷新或重试也会复用。用户改变输入、改变模式或点击“新建任务”时，网页会创建新 ID。

## 测试与证据

```powershell
# Python 测试不调用真实 API。
.venv/Scripts/python.exe -X utf8 -m pytest -q --junitxml=examples/test-results.xml

# 前端请求 ID 测试需要 Node.js；本机使用 Node.js v24.14.1。
node --test --test-isolation=none --test-reporter=tap tests/web_request.test.cjs

# 这项检查不调用模型。检查程序重算费用、耗时、约束和保存一致性。
.venv/Scripts/python.exe -X utf8 scripts/check_evidence.py

# 这项命令重新生成 15 组离线材料。
.venv/Scripts/python.exe -X utf8 scripts/run_examples.py --mode mock

# 以下两项命令消耗真实 API 额度，并会更新对应证据目录。
.venv/Scripts/python.exe -X utf8 scripts/run_examples.py --mode online --cases E01 E04 E05
.venv/Scripts/python.exe -X utf8 scripts/run_examples.py --mode online --cases E06 E07 E08 E09 E10 E11 E12 E13 E14 E15 --repeat 2 --output examples/online-expanded

# 这项检查核对文档链接，并检查本地密钥是否进入交付文本。
.venv/Scripts/python.exe -X utf8 scripts/audit_project.py
```

检查脚本按案例目标判定结果。预算不足时明确返回未完成，属于正确结果。运行脚本发现案例未达预期时会返回退出码 1，且保留失败证据。在线重跑可能产生不同的合法动作。

## 费用、耗时与限制

默认完整脚本收费 12，精简脚本收费 8。生成成功才发生模拟支出；失败调用不收费，但消耗模拟时间。检索、估算和保存各耗时 1 分钟，完整生成耗时 8 分钟，精简生成耗时 3 分钟。预算检查使用累计支出。重规划不会清除费用、时间或已成功脚本。

模型 API 用量与模拟费用分开记录。API 账单金额尚未查询，输出中的 `api_fee` 保持 null。程序默认限制 16 次模型请求、12 次业务工具尝试和 100 个图执行步。程序达到上限后返回明确未完成状态。

项目只保证本地串行执行。项目没有实现失败续跑、并发、真实素材服务、支付、发布或线上部署。SQLite 快照用于查询和防重复，不提供 LangGraph 断点恢复。在线验证使用有限的合成场景，不能代表生产环境成功率。

源码仓库的可编辑安装支持网页。独立 wheel 验证覆盖 CLI 和核心逻辑；网页静态文件和历史案例仍依赖源码目录。网页说明见 [网页 demo](docs/08-web-demo.md)。

## 设计与依据

- [需求与成功标准](docs/01-requirements.md)说明任务范围。
- [方案设计](docs/02-solution.md)说明模型、执行程序和工具的职责。
- [验收结果](docs/03-evaluation.md)说明实际验证与已知限制。
- [AI 使用记录](docs/04-ai-usage.md)与[复盘](docs/05-retrospective.md)说明开发过程。
- [决策记录](docs/06-decisions.md)记录已确认的业务口径。
- [题目](题目.md)与[考核规则](考核规则.md)提供原始要求。
