import copy

import pytest

from content_agent.evaluation import evaluate_result


def test_evaluator_accepts_actual_plan(run_agent):
    result, store, agent = run_agent()
    assert evaluate_result(result, store.read_plan(result["request_id"]), {}, agent.catalog) == []


@pytest.mark.parametrize("field", ["spent", "saved", "time", "estimate", "step_status"])
def test_evaluator_rejects_inconsistent_evidence(run_agent, field):
    result, store, agent = run_agent()
    result = copy.deepcopy(result)
    saved = store.read_plan(result["request_id"])
    if field == "spent":
        result["cost"]["spent"] += 1
    elif field == "saved":
        saved = None
    elif field == "time":
        result["time"]["simulated_minutes"] += 1
    elif field == "estimate":
        next(step for step in result["steps"] if step["tool"] == "estimate_plan")["result"]["data"]["budget_gap"] = 100
    else:
        result["plan"]["steps"][2]["status"] = "rejected"
    assert evaluate_result(result, saved, {}, agent.catalog)
