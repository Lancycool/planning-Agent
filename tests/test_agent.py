import copy
import json

import pytest
from pydantic import ValidationError

from content_agent.cli import main
from content_agent.engine import Agent
from content_agent.models import MockModel, ModelFailure, OnlineModel
from content_agent.schemas import Request, Scenario
from content_agent.tools import current_script, projection


def test_normal_output_is_backed_by_readable_plan(run_agent):
    result, store, _ = run_agent()
    assert result["status"] == "completed"
    plan = store.read_plan(result["request_id"])
    assert plan["script"] == result["script"]
    assert plan["total_spent"] == result["cost"]["spent"] == 12
    assert sum(event["amount"] for event in result["cost"]["events"]) == 12
    assert result["cost"]["api_fee"] is None
    assert result["model_mode"] == "mock"
    assert all(step["status"] == "succeeded" for step in result["plan"]["steps"])


@pytest.mark.parametrize("missing", ["theme", "budget", "deadline"])
def test_missing_input_never_calls_model_or_spends(run_agent, missing):
    result, store, _ = run_agent({missing: None})
    assert result["status"] == "waiting_input"
    assert missing in result["missing_fields"]
    assert result["calls"] == {"model": 0, "tools": 0}
    assert store.count_plans() == 0


def test_replan_twelve_to_eight_does_not_spend_estimate(run_agent):
    result, _, _ = run_agent({"budget": 10})
    assert result["status"] == "completed"
    assert [p["variant"] for p in result["plan_history"]] == ["premium", "basic"]
    estimates = [s["result"]["data"] for s in result["steps"] if s["tool"] == "estimate_plan"]
    assert estimates[0]["total_fee"] == 12 and estimates[0]["budget_gap"] == 2
    assert estimates[0]["spent"] == 0
    assert estimates[1]["total_fee"] == 8
    assert result["cost"]["spent"] == 8
    assert len(result["cost"]["events"]) == 1


def test_no_feasible_plan_reports_gap_and_never_saves(run_agent):
    result, store, _ = run_agent({"budget": 5})
    assert result["status"] == "incomplete" and result["cost"]["spent"] == 0
    assert result["cost"]["estimate"]["budget_gap"] == 3
    assert store.count_plans() == 0


def test_failure_preserves_materials_and_time_but_not_charge(run_agent):
    result, _, _ = run_agent(config={"failures": {"generate_script": 1}})
    assert result["status"] == "completed"
    assert result["plan"]["variant"] == "basic"
    assert result["materials"]["M01"]
    failed = [s for s in result["steps"] if s["status"] == "failed"]
    assert len(failed) == 1 and failed[0]["result"]["charged"] == 0
    assert failed[0]["result"]["elapsed_minutes"] == 8
    assert result["cost"]["spent"] == 8
    assert result["time"]["simulated_minutes"] == 16
    assert len([s for s in result["steps"] if s["tool"] == "search_materials"]) == 1


def test_save_failure_never_reports_completed(run_agent):
    result, store, _ = run_agent(config={"failures": {"save_plan": 1}})
    assert result["status"] == "incomplete" and result["saved"] is None
    assert result["script"] is not None and result["cost"]["spent"] == 12
    assert store.count_plans() == 0


def test_duplicate_is_persistent_and_does_not_run_again(run_agent):
    first, store, agent = run_agent()

    class NeverCall(MockModel):
        def choose(self, state):
            raise AssertionError("重复请求不应再次调用模型")

    second = Agent(store, NeverCall(), agent.catalog).run(Request.model_validate(first["request"]))
    assert second["replayed"] is True
    assert second["run_id"] == first["run_id"]
    assert second["cost"] == first["cost"] and second["trace"] == first["trace"]
    assert store.count_plans() == 1


def test_conflicting_duplicate_does_not_overwrite_first(run_agent):
    first, store, _ = run_agent()
    second, _, _ = run_agent({"budget": 30})
    assert second["reason_code"] == "REQUEST_CONFLICT"
    assert store.get(first["request_id"])["state"]["request"]["budget"] == 20


@pytest.mark.parametrize("config,code", [({"max_tool_calls": 1}, "CALL_LIMIT"),
                                         ({"max_model_calls": 1}, "CALL_LIMIT"),
                                         ({"recursion_limit": 2}, "GRAPH_LIMIT")])
def test_limits_produce_explicit_incomplete_state(run_agent, config, code):
    result, _, _ = run_agent(config=config)
    assert result["status"] == "incomplete" and result["reason_code"] == code
    assert result["trace"][-1]["kind"] == "terminal"


def test_time_insufficient_and_past_deadline(run_agent):
    result, store, _ = run_agent({"deadline": "2026-10-29T17:02:00+08:00"})
    assert result["status"] == "incomplete"
    assert result["cost"]["estimate"]["time_gap_minutes"] > 0
    assert store.count_plans() == 0
    past, _, _ = run_agent({"request_id": "past", "deadline": "2026-10-29T16:59:00+08:00"})
    assert past["reason_code"] == "DEADLINE_PASSED" and past["calls"]["model"] == 0


def test_equal_budget_and_deadline_are_allowed(run_agent):
    # search=1, estimate=1, generate=8, estimate=1, save=1 => 12 minutes
    result, _, _ = run_agent({"budget": 12, "deadline": "2026-10-29T17:12:00+08:00"})
    assert result["status"] == "completed" and result["time"]["simulated_minutes"] == 12


def test_no_materials_requests_information(run_agent):
    result, store, _ = run_agent({"theme": "完全无关xyz"})
    assert result["status"] == "waiting_input" and "materials" in result["missing_fields"]
    assert store.count_plans() == 0


class Scripted(MockModel):
    def __init__(self, actions):
        self.actions = iter(actions)

    def choose(self, state):
        return next(self.actions)


def act(name, **args):
    return {"name": name, "arguments": {"reason": "测试动作", **args}}


def test_false_completion_is_rejected(run_agent):
    result, store, _ = run_agent(model=Scripted([act("finish_task", status="completed")]))
    assert result["reason_code"] == "UNVERIFIED_COMPLETION" and store.count_plans() == 0


def test_unknown_actions_are_observed_and_bounded(run_agent):
    result, _, _ = run_agent(config={"max_model_calls": 2}, model=Scripted([act("shell"), act("shell")]))
    assert result["reason_code"] == "CALL_LIMIT"
    assert result["calls"]["tools"] == 0
    assert result["trace"][0]["observation"]["error_code"] == "INVALID_ACTION"


def test_stale_estimate_cannot_generate_or_save(run_agent):
    actions = [act("search_materials", query="字幕"), act("update_plan", variant="premium", material_ids=["M01"]),
               act("estimate_plan"), act("update_plan", variant="basic", material_ids=["M01"]),
               act("generate_script"), act("finish_task", status="incomplete")]
    result, store, _ = run_agent(model=Scripted(actions))
    assert result["steps"][-1]["status"] == "rejected"
    assert result["cost"]["spent"] == 0 and store.count_plans() == 0


def test_model_error_never_silently_falls_back(run_agent):
    class Broken(MockModel):
        mode = "online"

        def choose(self, state):
            raise ModelFailure("测试连接失败")

    result, _, _ = run_agent(model=Broken())
    assert result["status"] == "incomplete" and result["model_mode"] == "online"
    assert result["reason_code"] == "MODEL_ERROR"


def test_generated_script_requires_new_estimate_before_save(run_agent):
    actions = [act("search_materials", query="字幕"), act("update_plan", variant="premium", material_ids=["M01"]),
               act("estimate_plan"), act("generate_script"), act("save_plan"), act("finish_task", status="incomplete")]
    result, store, _ = run_agent(model=Scripted(actions))
    assert result["steps"][-1]["status"] == "rejected" and store.count_plans() == 0
    assert result["cost"]["spent"] == 12


def test_prior_spend_is_not_erased_by_replanning(run_agent):
    actions = [act("search_materials", query="字幕"), act("update_plan", variant="premium", material_ids=["M01"]),
               act("estimate_plan"), act("generate_script"), act("update_plan", variant="basic", material_ids=["M01"]),
               act("estimate_plan"), act("generate_script"), act("finish_task", status="incomplete")]
    result, _, _ = run_agent({"budget": 19}, model=Scripted(actions))
    assert result["cost"]["spent"] == 12
    assert result["cost"]["estimate"]["total_fee"] == 20
    assert result["steps"][-1]["status"] == "rejected"


def test_successful_script_is_reused_after_plan_change(run_agent):
    actions = [act("search_materials", query="字幕"), act("update_plan", variant="basic", material_ids=["M01"]),
               act("estimate_plan"), act("generate_script"), act("update_plan", variant="premium", material_ids=["M01"]),
               act("update_plan", variant="basic", material_ids=["M01"]), act("estimate_plan"), act("save_plan"),
               act("finish_task", status="completed")]
    result, _, _ = run_agent(model=Scripted(actions))
    assert result["status"] == "completed" and result["cost"]["spent"] == 8
    assert len(result["cost"]["events"]) == 1


@pytest.mark.parametrize("updates", [{"budget": -1}, {"budget": True}, {"budget": 1.5},
                                     {"deadline": "2026-10-29T18:00:00"}, {"request_id": "../escape"}])
def test_invalid_business_input_is_rejected(updates):
    from conftest import BASE
    with pytest.raises(ValidationError):
        Request.model_validate({**BASE, **updates})


def test_missing_key_is_safe_and_explicit(run_agent, monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    result, _, _ = run_agent(model=OnlineModel())
    assert result["reason_code"] == "MODEL_ERROR" and "MISSING_API_KEY" in result["reason"]


def test_cli_can_export_mock_results(tmp_path, capsys):
    from conftest import BASE, CLOCK, ROOT
    input_path, scenario_path = tmp_path / "input.json", tmp_path / "scenario.json"
    input_path.write_text(json.dumps(BASE), encoding="utf-8")
    scenario_path.write_text(json.dumps({"start_at": CLOCK}), encoding="utf-8")
    code = main(["--mode", "mock", "--input", str(input_path), "--scenario", str(scenario_path),
                 "--catalog", str(ROOT / "data/catalog.json"), "--db", str(tmp_path / "cli.sqlite3"),
                 "--output-dir", str(tmp_path / "evidence")])
    assert code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "completed"
    assert (tmp_path / "evidence/saved-plan.json").exists()


def test_sqlite_save_error_does_not_create_false_receipt(run_agent, monkeypatch):
    import sqlite3
    from content_agent.storage import Store
    original = Store.write

    def fail_on_plan(self, state, plan=None):
        if plan is not None:
            raise sqlite3.OperationalError("simulated disk failure")
        return original(self, state, plan)

    monkeypatch.setattr(Store, "write", fail_on_plan)
    result, store, _ = run_agent()
    assert result["reason_code"] == "RUNTIME_ERROR"
    assert result["saved"] is None and store.count_plans() == 0
    assert result["cost"]["spent"] == 12 and result["script"] is not None


def test_provider_error_does_not_leak_raw_message(run_agent, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-only-not-real")
    model = OnlineModel()

    def fail(**kwargs):
        raise RuntimeError("sensitive-request-body-test-only-not-real")

    monkeypatch.setattr(model.client.chat.completions, "create", fail)
    result, _, _ = run_agent(model=model)
    assert result["reason_code"] == "MODEL_ERROR"
    assert "sensitive-request" not in json.dumps(result)
    assert "test-only-not-real" not in json.dumps(result)


def test_rejected_retry_preserves_successful_plan_step(run_agent):
    actions = [act("search_materials", query="字幕"), act("update_plan", variant="premium", material_ids=["M01"]),
               act("estimate_plan"), act("generate_script"), act("generate_script"), act("estimate_plan"),
               act("save_plan"), act("finish_task", status="completed")]
    result, store, _ = run_agent(model=Scripted(actions))
    assert result["status"] == "completed"
    attempts = [s for s in result["steps"] if s["tool"] == "generate_script"]
    assert [s["status"] for s in attempts] == ["succeeded", "rejected"]
    assert all(s["status"] == "succeeded" for s in result["plan"]["steps"])
    assert store.read_plan(result["request_id"])["plan"] == result["plan"]
    assert result["cost"]["spent"] == 12 and len(result["cost"]["events"]) == 1


def test_export_removes_previous_plan_and_scenario(tmp_path):
    from content_agent.cli import export_result

    export_result(tmp_path, {"request_id": "old"}, {"status": "completed"}, {"start_at": "old"}, {"plan_id": "old"})
    export_result(tmp_path, {"request_id": "new"}, {"status": "waiting_input"})
    assert json.loads((tmp_path / "output.json").read_text())["status"] == "waiting_input"
    assert not (tmp_path / "saved-plan.json").exists()
    assert not (tmp_path / "scenario.json").exists()


def test_conflict_export_does_not_attach_existing_plan(tmp_path, capsys):
    from conftest import BASE, CLOCK, ROOT

    input_path, scenario_path = tmp_path / "input.json", tmp_path / "scenario.json"
    input_path.write_text(json.dumps(BASE), encoding="utf-8")
    scenario_path.write_text(json.dumps({"start_at": CLOCK}), encoding="utf-8")
    argv = ["--mode", "mock", "--input", str(input_path), "--scenario", str(scenario_path),
            "--catalog", str(ROOT / "data/catalog.json"), "--db", str(tmp_path / "tasks.sqlite3"),
            "--output-dir", str(tmp_path / "export")]
    assert main(argv) == 0
    capsys.readouterr()
    input_path.write_text(json.dumps({**BASE, "budget": 30}), encoding="utf-8")
    assert main(argv) == 2
    assert json.loads(capsys.readouterr().out)["reason_code"] == "REQUEST_CONFLICT"
    assert not (tmp_path / "export/saved-plan.json").exists()
