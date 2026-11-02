"""Check actual outcomes, independently of the model's explanation text."""

from datetime import datetime, timedelta


def evaluate_result(result: dict, saved: dict | None, scenario: dict, catalog: dict | None = None) -> list[str]:
    errors = []

    def check(condition, message):
        if not condition:
            errors.append(message)

    request, cost, steps = result["request"], result["cost"], result["steps"]
    check(result["status"] in {"completed", "incomplete", "waiting_input"}, "任务必须返回明确终态")
    check(bool(result["trace"]) and result["trace"][-1].get("status") == result["status"], "Trace 终态必须一致")
    check(sum(event["amount"] for event in cost["events"]) == cost["spent"], "费用事件合计必须等于支出")
    check(cost["spent"] >= 0 and all(event["amount"] >= 0 for event in cost["events"]), "费用不得为负数")
    check(cost["spent"] <= request["budget"] if request["budget"] is not None else cost["spent"] == 0,
          "支出不得超过预算")
    check(sum(step["result"].get("elapsed_minutes", 0) for step in steps)
          == result["time"]["simulated_minutes"], "工具耗时合计必须等于模拟耗时")
    check(result["calls"]["tools"] == len(steps), "工具计数必须对应实际调用记录")
    check(result["calls"]["tools"] <= scenario.get("max_tool_calls", 12), "工具调用不得超过上限")
    check(result["calls"]["model"] <= scenario.get("max_model_calls", 16), "模型调用不得超过上限")
    charged = [step for step in steps if step["tool"] == "generate_script" and step["status"] == "succeeded"]
    check(len(charged) == len(cost["events"]), "成功生成必须逐次对应费用事件")
    check(sum(step["result"].get("charged", 0) for step in steps) == cost["spent"], "工具费用必须等于支出")
    for step in steps:
        if step["status"] != "succeeded":
            check(step["result"].get("charged", 0) == 0, "失败或拒绝调用不得收费")
        if catalog is not None:
            plans = {plan["version"]: plan for plan in result["plan_history"]}
            variant = catalog["variants"][plans[step["plan_version"]]["variant"]] if step["plan_version"] else None
            minutes = (0 if step["status"] == "rejected" else
                       variant["generation_minutes"] if step["tool"] == "generate_script" else
                       catalog["tools"][step["tool"]]["minutes"])
            check(step["result"].get("elapsed_minutes", 0) == (0 if step["status"] == "rejected" else minutes),
                  "每次工具耗时必须符合费用耗时表")
            fee = variant["generation_fee"] if step["tool"] == "generate_script" and step["status"] == "succeeded" else 0
            check(step["result"].get("charged", 0) == fee, "每次工具费用必须符合费用表")
            if step["tool"] == "estimate_plan" and step["status"] == "succeeded":
                estimate = step["result"]["data"]
                remaining = 0 if estimate["script_exists"] else variant["generation_fee"]
                remaining_time = catalog["tools"]["save_plan"]["minutes"]
                if not estimate["script_exists"]:
                    remaining_time += variant["generation_minutes"] + catalog["tools"]["estimate_plan"]["minutes"]
                finish = datetime.fromisoformat(result["time"]["start_at"]) + timedelta(
                    minutes=step["elapsed_after"] + remaining_time)
                deadline = datetime.fromisoformat(request["deadline"])
                total = step["spent_after"] + remaining
                check(estimate["spent"] == step["spent_after"] and estimate["remaining_fee"] == remaining
                      and estimate["total_fee"] == total, "估算费用必须符合累计支出和费用表")
                check(estimate["budget_gap"] == max(0, total - request["budget"]), "预算缺口必须正确")
                check(estimate["remaining_minutes"] == remaining_time
                      and datetime.fromisoformat(estimate["estimated_finish"]) == finish, "估算时间必须符合耗时表")
                check(estimate["time_gap_minutes"] == max(0, (finish - deadline).total_seconds() / 60), "时间缺口必须正确")
                check(estimate["feasible"] == (total <= request["budget"] and finish <= deadline), "可行性必须符合预算和截止时间")
    check(bool(result["saved"]) == (saved is not None), "保存凭据必须对应实际保存产物")
    if saved is not None:
        check(saved["request_id"] == result["request_id"], "保存产物必须属于当前请求")
        check(saved["plan_id"] == result["saved"]["plan_id"], "保存凭据必须一致")
        check(saved["plan"] == result["plan"] and saved["script"] == result["script"], "计划与脚本必须和保存产物一致")
        check(saved["total_spent"] == cost["spent"] and saved["cost_events"] == cost["events"], "保存费用必须一致")
        finish = datetime.fromisoformat(result["time"]["start_at"]) + timedelta(minutes=result["time"]["simulated_minutes"])
        check(finish <= datetime.fromisoformat(request["deadline"]), "保存不得超过截止时间")
        check(datetime.fromisoformat(saved["simulated_finish"]) == finish, "保存时间必须与实际工具耗时一致")
        check(all(step["status"] in {"succeeded", "skipped"} for step in result["plan"]["steps"]),
              "保存计划必须保留所有成功步骤")
    if result["status"] == "completed":
        check(saved is not None and result["script"] is not None, "完成状态必须有脚本和实际保存产物")
    else:
        check(bool(result["reason"]), "未完成状态必须说明原因")
    return errors
