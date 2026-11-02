# 最终交付清单

## 提交信息

| 项目 | 内容 |
| --- | --- |
| 题号 | 任务 1：内容任务规划 Agent。 |
| GitHub URL | https://github.com/Lancycool/planning-Agent |
| 仓库范围 | 仓库在本轮检查时公开，程序没有修改仓库权限。 |
| 交付标签 | `submission-2026-11-02`。 |
| 最终 commit SHA | 评审者检出交付标签后运行 `git rev-parse HEAD`。交付回复同时给出完整 SHA。 |
| 本轮验证源码 commit | `6df4289af9c1df7da0693d7167f5b3f85a98ca2f`。 |
| 运行入口 | 项目提供 CLI，也提供本地网页。 |
| 配置 | 项目提供 `.env.example` 和 `env.sample`。离线运行无需配置。 |
| 测试 | 项目提供 Python 测试、前端请求 ID 测试和证据检查脚本。 |

Git 提交内容不能包含该提交自身的完整 SHA。项目使用标签固定最终版本，并在交付回复中提供最终 SHA。评审者可以运行 `git rev-parse submission-2026-11-02^{commit}` 核对标签。

## 材料位置

| 材料 | 文件或目录 |
| --- | --- |
| 环境、安装、复现命令 | [README](../README.md)。 |
| 需求、设计、评估、AI 使用和复盘 | `docs/01-requirements.md` 至 `docs/05-retrospective.md`。 |
| 代码审阅后的修改 | [修复记录](10-code-review-fixes.md)。 |
| 合成资料与费用耗时规则 | `data/catalog.json`。 |
| 离线运行记录 | `examples/mock/manifest.json` 及对应案例目录。 |
| 核心真实模型记录 | `examples/online/manifest.json` 及对应案例目录。 |
| 扩展真实模型记录 | `examples/online-expanded/manifest.json` 及对应案例目录。 |
| 本轮结果摘要 | `examples/revision-summary.json`。 |
| Python 测试报告 | `examples/test-results.xml`。 |
| 独立 wheel 核心测试报告 | `examples/clean-environment-tests.xml`。 |
| 前端测试报告 | `examples/web-request-tests.tap`。 |
| 证据复核与文件检查 | `examples/evidence-check.json` 和 `examples/project-audit.json`。 |

每个新生成的案例目录都包含输入、输出、Trace、场景、实际 catalog 和 evaluation。成功保存的案例还包含 saved-plan。重复执行案例还包含 replay 和 storage-check。manifest 使用仓库相对路径记录源文件 SHA256，也记录实际运行所用的源码 commit。最终交付提交在这个源码提交之后补充文档和证据。检查脚本会核对最终源码是否仍与运行记录一致。

## 评审步骤

评审者先按 README 安装依赖，再运行离线示例和自动测试。评审者可以运行 `scripts/check_evidence.py` 检查已提交的真实模型材料。这个过程不需要 API 密钥。评审者需要重新验证真实模型时，再在本地配置密钥并执行 README 的在线命令。

项目不提交 `.env`、运行数据库、虚拟环境或真实密钥。项目没有实现的功能与实际验证范围均在 README 和评估文档中说明。

项目用 `.gitattributes` 保留源文件字节，避免不同平台在检出时转换换行符而破坏证据哈希。运行记录中的源码 commit 与当时工作区字节一致。
