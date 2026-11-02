# 运行材料说明

本轮材料生成于 2026-11-02。评审者以以下清单为准：

- `mock/manifest.json` 登记 15 组离线案例。
- `online/manifest.json` 登记 3 组核心真实模型案例。
- `online-expanded/manifest.json` 登记扩展真实模型的独立重复运行。
- `evidence-check.json` 记录检查程序重新计算的结论。
- `test-results.xml`、`clean-environment-tests.xml` 和 `web-request-tests.tap` 记录本轮自动测试结果。

每个新案例包含 input、output、trace、scenario、catalog 和 evaluation。成功保存的案例还包含 saved-plan。重复执行案例还包含 replay 和 storage-check。manifest 记录源码 commit、仓库相对路径和逐文件 SHA256。

`cli-smoke/` 和网页截图来自首版或网页开发阶段，属于历史材料。本轮评估不把它们算作当前版本运行证据。`development-log.json` 保留首版过程，并追加本轮核对记录。

真实模型案例允许出现不同动作。评估以实际费用、工具状态、保存产物和案例目标为准。任务正确返回未完成，也可以通过该案例检查。模型不可用、执行错误或未达到预期状态会在 evaluation 中保留失败结论。
