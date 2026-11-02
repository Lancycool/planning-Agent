# 验收与实际评估

## 本轮结果

项目在 2026-11-02 完成审阅后的修复与复跑。开发环境通过 55 项 Python 测试，独立 wheel 环境通过 50 项核心测试，前端通过 3 项请求 ID 测试。开发环境包含网页 HTTP 测试；独立 wheel 测试没有包含依赖源码静态资源的网页测试。

检查程序重新核对 38 组案例：15 组离线案例和 23 组真实模型案例。所有案例均达到各自预期，费用、耗时、保存产物和源文件哈希检查也均通过。23 组真实模型运行的实际终态为 12 组 completed、9 组 incomplete 和 2 组 waiting_input。预算不足、持续失败或资料不足时返回明确未完成，也属于正确结果。这些数字不是“23 次任务全部完成”，也不能推算线上成功率。

当前报告对应 [Python 测试报告](../examples/test-results.xml)、[独立 wheel 核心测试报告](../examples/clean-environment-tests.xml)、[前端测试报告](../examples/web-request-tests.tap)和[证据重算结果](../examples/evidence-check.json)。

## 验收矩阵

| 编号 | 场景 | 实际材料与结果 |
| --- | --- | --- |
| E01 | 正常完成。 | [离线目录](../examples/mock/E01-normal)、[真实目录](../examples/online/E01-normal)。系统保存方案，累计模拟费用为 12。 |
| E02 | 缺预算。 | [离线目录](../examples/mock/E02-missing-budget)。系统返回 waiting_input，且不调用模型、不收费。 |
| E03 | 缺截止时间。 | [离线目录](../examples/mock/E03-missing-deadline)。系统返回 waiting_input。 |
| E04 | 生成工具失败一次。 | [真实 Trace](../examples/online/E04-tool-failure/trace.json)。模型观察失败后改选精简方案，保留素材并完成保存。 |
| E05 | 首次估算 12，预算 10。 | [真实 Trace](../examples/online/E05-replan/trace.json)。模型观察缺口 2 后改选费用 8 的方案，再估算并保存。 |
| E06 | 所有方案都超预算。 | 扩展真实模型两轮均返回 incomplete，支出为 0。 |
| E07 | 相同请求重复执行。 | 扩展真实模型两轮均完成首个任务。重复请求不再调用模型，数据库只保存一份方案；每轮包含 replay 和 storage-check。 |
| E08 | 保存工具失败一次。 | 扩展真实模型两轮均重试保存并成功。Trace 保留最初失败记录。离线模型选择停止，也符合停止时不得虚报成功的规则。 |
| E09 | 工具额度仅为 1。 | 扩展真实模型两轮均在调用工具前主动停止。实际 CALL_LIMIT 和 GRAPH_LIMIT 由自动测试验证，这两条在线记录不能证明运行时触发上限。 |
| E10 | 截止时间只有 2 分钟。 | 扩展真实模型两轮均返回 incomplete，支出为 0，且没有保存方案。 |
| E11 | 完整方案改为费用 6，精简方案改为费用 11，预算为 10。 | 扩展真实模型两轮均选择完整方案，支出为 6。每轮 catalog 文件保留实际价格。 |
| E12 | 模型先评估完整方案，但截止时间只有 8 分钟。 | 扩展真实模型两轮均改选精简方案，并在模拟第 8 分钟保存成功。 |
| E13 | 生成工具连续失败两次。 | 第一轮在两次失败后停止，费用为 0；第二轮继续尝试并成功生成精简脚本，费用为 8。两轮均保留成功素材和实际失败记录。 |
| E14 | 保存工具持续失败。 | 扩展真实模型两轮均返回 incomplete，保留已成功脚本和已发生费用，且没有保存凭据。 |
| E15 | 实际资料表为空。 | 扩展真实模型两轮均补查后请求补充，状态为 waiting_input，支出为 0。 |

E01—E07 覆盖任务 1 的全部必验收要求。E08—E15 扩大异常和边界验证。自动测试还覆盖费用等于预算、时间恰好满足截止时间、旧估算失效、累计历史支出、脚本复用、模型不可用、非法动作、输入冲突和数据库保存错误。

## 真实模型逐次结果

项目重新运行 3 条核心路径，并对另外 10 个场景各独立运行两次。每次运行使用独立数据库。模型不知道尚未发生的注入故障。模型收到实际工具结果后自行选择重试、改方案、请求补充或停止。项目没有删去某次运行来替换为更好看的结果。

| 案例 | 终态 | 模型 / 工具次数 | 模拟支出 | 模拟分钟 | 实际秒数 |
| --- | --- | --- | --- | --- | --- |
| E01-normal | completed | 7 / 5 | 12 | 12 | 27.7826 |
| E04-tool-failure | completed | 11 / 8 | 8 | 17 | 38.0890 |
| E05-replan | completed | 9 / 6 | 8 | 8 | 18.9122 |
| E06-no-feasible-plan-r01 | incomplete | 5 / 3 | 0 | 3 | 15.5765 |
| E06-no-feasible-plan-r02 | incomplete | 7 / 5 | 0 | 5 | 28.8109 |
| E07-duplicate-r01 | completed | 7 / 5 | 12 | 12 | 13.4286 |
| E07-duplicate-r02 | completed | 7 / 5 | 12 | 12 | 10.3320 |
| E08-save-failure-r01 | completed | 8 / 6 | 12 | 13 | 12.3320 |
| E08-save-failure-r02 | completed | 8 / 6 | 12 | 13 | 25.4689 |
| E09-step-limit-r01 | incomplete | 1 / 0 | 0 | 0 | 15.3621 |
| E09-step-limit-r02 | incomplete | 1 / 0 | 0 | 0 | 12.5838 |
| E10-deadline-r01 | incomplete | 3 / 1 | 0 | 1 | 23.4387 |
| E10-deadline-r02 | incomplete | 4 / 2 | 0 | 2 | 20.3563 |
| E11-changed-prices-r01 | completed | 7 / 5 | 6 | 12 | 29.5190 |
| E11-changed-prices-r02 | completed | 7 / 5 | 6 | 12 | 15.1921 |
| E12-time-replan-r01 | completed | 10 / 6 | 8 | 8 | 71.6340 |
| E12-time-replan-r02 | completed | 9 / 6 | 8 | 8 | 40.7562 |
| E13-repeated-generation-failure-r01 | incomplete | 8 / 5 | 0 | 14 | 38.8986 |
| E13-repeated-generation-failure-r02 | completed | 13 / 10 | 8 | 21 | 37.7373 |
| E14-persistent-save-failure-r01 | incomplete | 10 / 8 | 12 | 15 | 24.6118 |
| E14-persistent-save-failure-r02 | incomplete | 11 / 9 | 12 | 16 | 18.8306 |
| E15-empty-materials-r01 | waiting_input | 5 / 4 | 0 | 4 | 12.6902 |
| E15-empty-materials-r02 | waiting_input | 5 / 4 | 0 | 4 | 12.6442 |

原始清单为 [核心在线 manifest](../examples/online/manifest.json)和[扩展在线 manifest](../examples/online-expanded/manifest.json)。清单中的每个 case 对应同名目录。各目录保留 input、output、trace、scenario、catalog 和 evaluation；成功保存的目录还保留 saved-plan。

本轮 23 组在线运行的接口 total_tokens 合计为 504528。实际运行秒数合计为 564.9876。两批运行有时间重叠，因此这个合计不是本轮开发总工时。项目没有查询账单，API 金额保持 null。模拟支出也不等于 API 金额。

## 检查方式

`scripts/run_examples.py` 会为每次运行保存检查结论。案例没有达到预期时，脚本返回退出码 1，并保留实际结果。业务任务正确停止不等于测试失败。

`src/content_agent/evaluation.py` 检查实际终态、费用事件、工具费用、工具耗时、预算和时间缺口、可行性、执行上限及保存一致性。检查程序使用每组实际 catalog 重新计算费用与时间。`scripts/check_evidence.py` 会再次读取已导出材料，核对输入、Trace、清单、重复执行记录和源文件 SHA256。这个过程不调用模型。

项目还用测试主动破坏费用、时间、估算、保存凭据和步骤状态，确认检查程序能够发现不一致。代码审阅的四项问题与回归验证见 [修复记录](10-code-review-fixes.md)。

## 版本与复现

本轮 manifest 记录实际运行所用的源码 commit、依赖版本和逐文件 SHA256。所有哈希路径均为仓库相对路径。最终交付提交补充文档和证据，源码内容保持与运行记录一致。交付标签和最终 SHA 的核对方式见 [交付清单](09-delivery.md)。

开发环境使用 Python 3.12.13、LangGraph 1.2.18、OpenAI SDK 2.54.0 和 Pydantic 2.14.1。前端测试使用 Node.js v24.14.1。项目从当前源码构建 wheel，再在独立环境安装并执行 50 项核心测试。这个环境不使用开发环境的可编辑包。

所有运行命令均在 README。固定时钟场景使用 2026-10-29 的业务起点，manifest 另行记录实际运行日期。评审者不应把固定业务时钟当作 API 调用日期。

## 限制

真实模型验证覆盖有限的合成场景。每个扩展场景只有两次独立运行，结果不足以支持稳定成功率结论。脚本工具使用固定模板，在线记录证明的是动作选择、工具观察与调整。

模型有时把模拟单位称为元，也可能在简要理由中误述时间或数字。项目保留原始理由，并以结构化计算字段判断费用、时间与状态。项目没有实现自由文本理由的独立事实校验。

系统未实现失败续跑、并发、真实素材平台、真实支付、真实发布和线上部署。独立 wheel 不包含网页资源与历史案例。项目的源码安装支持本地网页。文件检查会核对文档链接，并检查本地实际密钥是否进入交付文本；[检查报告](../examples/project-audit.json)说明检查范围。
