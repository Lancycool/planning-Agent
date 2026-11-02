"""CLI entry point. No credentials are included in output or trace."""

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from .engine import Agent
from .models import MockModel, OnlineModel
from .schemas import Request, Scenario
from .storage import Store
from .tools import load_catalog


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def export_result(directory: Path, payload: dict, result: dict, scenario: dict | None = None, plan=None) -> None:
    write_json(directory / "input.json", payload)
    write_json(directory / "output.json", result)
    write_json(directory / "trace.json", result.get("trace", []))
    if scenario is not None:
        write_json(directory / "scenario.json", scenario)
    else:
        (directory / "scenario.json").unlink(missing_ok=True)
    if plan is not None:
        write_json(directory / "saved-plan.json", plan)
    else:
        (directory / "saved-plan.json").unlink(missing_ok=True)


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="内容任务规划 Agent（本地业务工具）")
    parser.add_argument("--input", type=Path, required=True, help="业务输入 JSON")
    parser.add_argument("--mode", choices=("mock", "online"), required=True, help="必须明确选择真实模型或离线流程模拟")
    parser.add_argument("--scenario", type=Path, help="测试专用：固定起点、工具失败次数、执行上限")
    parser.add_argument("--catalog", type=Path, default=Path("data/catalog.json"))
    parser.add_argument("--db", type=Path, default=Path(".runtime/tasks.sqlite3"))
    parser.add_argument("--output-dir", type=Path, help="导出实际输入、输出、Trace 和已保存方案")
    args = parser.parse_args(argv)
    # Environment variables take priority; only the exact local .env is read.
    load_dotenv(Path.cwd() / ".env", override=False)
    store = None
    try:
        payload = read_json(args.input)
        scenario_payload = read_json(args.scenario) if args.scenario else {}
        request = Request.model_validate(payload)
        scenario = Scenario.model_validate(scenario_payload)
        catalog = load_catalog(args.catalog)
        store = Store(args.db)
        model = MockModel() if args.mode == "mock" else OnlineModel()
        result = Agent(store, model, catalog).run(request, scenario)
        if args.output_dir:
            plan = store.read_plan(request.request_id) if result.get("saved") else None
            export_result(args.output_dir, payload, result, scenario_payload, plan)
    except (ValueError, ValidationError, OSError) as exc:
        # Do not stringify config exceptions, which might contain credentials.
        result = {"status": "incomplete", "reason_code": "INVALID_INPUT_OR_CONFIG",
                  "reason": f"输入或配置无效（{type(exc).__name__}），请检查 JSON 字段、时区、整数预算和文件路径"}
    finally:
        if store is not None:
            store.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    sys.exit(main())
