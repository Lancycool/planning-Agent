"""Generate actual offline or online evidence with explicit model labels."""

import argparse
import copy
import hashlib
import importlib.metadata
import json
import subprocess
import sys
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from content_agent.cli import export_result, write_json
from content_agent.engine import Agent
from content_agent.evaluation import evaluate_result
from content_agent.models import MockModel, OnlineModel
from content_agent.schemas import Request, Scenario
from content_agent.storage import Store
from content_agent.tools import load_catalog

BASE = {"theme": "字幕产品活动", "budget": 20, "deadline": "2026-10-29T18:00:00+08:00"}
CLOCK = "2026-10-29T17:00:00+08:00"
CASES = [
    ("E01-normal", {}, {}),
    ("E02-missing-budget", {"budget": None}, {}),
    ("E03-missing-deadline", {"deadline": None}, {}),
    ("E04-tool-failure", {}, {"failures": {"generate_script": 1}}),
    ("E05-replan", {"budget": 10, "theme": "字幕产品活动，请先评估完整方案；若预算超限，再考虑精简方案"}, {}),
    ("E06-no-feasible-plan", {"budget": 5}, {}),
    ("E07-duplicate", {}, {}),
    ("E08-save-failure", {}, {"failures": {"save_plan": 1}}),
    ("E09-step-limit", {}, {"max_tool_calls": 1}),
    ("E10-deadline", {"deadline": "2026-10-29T17:02:00+08:00"}, {}),
    ("E11-changed-prices", {"budget": 10}, {}),
    ("E12-time-replan", {"deadline": "2026-10-29T17:08:00+08:00",
                          "theme": "字幕产品活动，请先评估完整方案；若时间不足，再考虑精简方案"}, {}),
    ("E13-repeated-generation-failure", {}, {"failures": {"generate_script": 2}}),
    ("E14-persistent-save-failure", {}, {"failures": {"save_plan": 100}}),
    ("E15-empty-materials", {}, {}),
]


def case_catalog(name: str, catalog: dict) -> dict:
    catalog = copy.deepcopy(catalog)
    if name == "E11-changed-prices":
        catalog["version"] += "-changed-prices"
        catalog["variants"]["premium"]["generation_fee"] = 6
        catalog["variants"]["basic"]["generation_fee"] = 11
    if name == "E15-empty-materials":
        catalog["version"] += "-empty-materials"
        catalog["materials"] = []
    return catalog


def case_errors(name: str, result: dict) -> list[str]:
    errors = []
    expected = {
        "E01": {"completed"}, "E02": {"waiting_input"}, "E03": {"waiting_input"},
        "E04": {"completed"}, "E05": {"completed"}, "E06": {"incomplete"},
        "E07": {"completed"}, "E08": {"completed", "incomplete"}, "E09": {"incomplete"},
        "E10": {"incomplete"}, "E11": {"completed"}, "E12": {"completed"},
        "E13": {"completed", "incomplete"}, "E14": {"incomplete"}, "E15": {"waiting_input", "incomplete"},
    }
    if result["status"] not in expected[name.split("-")[0]]:
        errors.append("任务没有达到案例预期状态")
    if result["reason_code"] in {"MODEL_ERROR", "RUNTIME_ERROR", "UNVERIFIED_COMPLETION"}:
        errors.append("运行出现模型、执行或完成核验错误")
    if name in {"E04-tool-failure", "E08-save-failure", "E13-repeated-generation-failure", "E14-persistent-save-failure"}:
        if not any(step["status"] == "failed" for step in result["steps"]):
            errors.append("案例没有实际观察到工具失败")
    if name == "E05-replan":
        estimates = [step["result"]["data"] for step in result["steps"]
                     if step["tool"] == "estimate_plan" and step["status"] == "succeeded"]
        if not (estimates and estimates[0]["budget_gap"] == 2 and result["cost"]["spent"] == 8):
            errors.append("案例没有证明观察预算超限后改选费用 8 的方案")
    if name == "E11-changed-prices" and result["cost"]["spent"] != 6:
        errors.append("模型没有按修改后的价格选择费用 6 的方案")
    if name == "E14-persistent-save-failure" and (result["saved"] or not result["script"]):
        errors.append("持续保存失败时必须保留脚本且没有保存凭据")
    if name == "E15-empty-materials" and (result["script"] or result["cost"]["spent"] != 0):
        errors.append("无素材时不得生成脚本或收费")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("mock", "online"), required=True)
    parser.add_argument("--cases", nargs="*", help="案例编号，例如 E01 E04 E05")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeat", type=int, default=1, choices=range(1, 6), help="每个案例独立运行次数（1—5）")
    args = parser.parse_args()
    load_dotenv(Path.cwd() / ".env", override=False)
    output = args.output or Path("examples") / args.mode
    catalog = load_catalog("data/catalog.json")
    model = MockModel() if args.mode == "mock" else OnlineModel()
    if args.mode == "online" and not model.configured:
        print("尚未配置本地 DASHSCOPE_API_KEY；没有发出模型请求。", file=sys.stderr)
        return 2
    summary = {"mode": args.mode, "recorded_at": datetime.now(timezone.utc).isoformat(),
               "model": model.model_id, "python": sys.version, "catalog_version": catalog["version"],
               "versions": {name: importlib.metadata.version(name) for name in ("langgraph", "openai", "pydantic")},
               "repeat": args.repeat, "cases": []}
    revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    summary["commit"] = revision.stdout.strip() if revision.returncode == 0 else None
    sources = [Path("pyproject.toml"), Path("uv.lock"),
               *sorted(Path("scripts").glob("*.py")), *sorted(Path("src").rglob("*.py")),
               *sorted(path for path in Path("tests").iterdir() if path.suffix in {".py", ".cjs"}),
               *sorted(Path("data").rglob("*.json")),
               *sorted(path for path in Path("web").iterdir() if path.is_file())]
    summary["source_sha256"] = {path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    selected = {name.split("-")[0] for name, _, _ in CASES}
    if args.cases and not set(args.cases) <= selected:
        parser.error("案例编号不存在")
    for name, updates, config, repetition in [(*case, repetition) for case in CASES
                                               for repetition in range(1, args.repeat + 1)]:
        if args.cases and name.split("-")[0] not in args.cases:
            continue
        directory_name = name if args.repeat == 1 else f"{name}-r{repetition:02}"
        payload = {**BASE, **updates, "request_id": f"{args.mode}-{directory_name}"}
        scenario_payload = {"start_at": CLOCK, **config}
        actual_catalog = case_catalog(name, catalog)
        temporary = Path(".runtime") / "example-work" / uuid4().hex
        temporary.mkdir(parents=True)
        if temporary:
            store = Store(temporary / "tasks.sqlite3")
            try:
                agent = Agent(store, model, actual_catalog)
                request = Request.model_validate(payload)
                result = agent.run(request, Scenario.model_validate(scenario_payload))
                saved = store.read_plan(request.request_id)
                directory = output / directory_name
                export_result(directory, payload, result, scenario_payload, saved)
                write_json(directory / "catalog.json", actual_catalog)
                errors = evaluate_result(result, saved, scenario_payload, actual_catalog) + case_errors(name, result)
                if name == "E07-duplicate":
                    class NeverCall:
                        def choose(self, state):
                            raise AssertionError("重复执行不得再次调用模型")

                    replay = Agent(store, NeverCall(), actual_catalog).run(request, Scenario.model_validate(scenario_payload))
                    write_json(directory / "replay.json", replay)
                    write_json(directory / "storage-check.json", {"saved_plan_count": store.count_plans(),
                               "replay_unchanged": replay["calls"] == result["calls"] and replay["cost"] == result["cost"]})
                    if not replay["replayed"] or {**result, "replayed": True} != replay or store.count_plans() != 1:
                        errors.append("重复执行改变了结果或保存数量")
                verdict = {"passed": not errors, "errors": errors}
                write_json(directory / "evaluation.json", verdict)
                summary["cases"].append({"case": directory_name, "scenario": name, "repetition": repetition,
                                         "status": result["status"], "reason_code": result["reason_code"],
                                         "model_calls": result["calls"]["model"], "tool_calls": result["calls"]["tools"],
                                         "spent": result["cost"]["spent"], "evaluation": verdict})
                print(f"{directory_name}: {result['status']} ({result['reason_code']}), checks={'passed' if not errors else errors}", flush=True)
            finally:
                store.close()
        # Preserve progress even if a later online run is interrupted.
        write_json(output / "manifest.json", summary)
    summary["passed"] = all(entry["evaluation"]["passed"] for entry in summary["cases"])
    write_json(output / "manifest.json", summary)
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
