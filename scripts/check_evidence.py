"""Recompute evidence checks without calling a model or rewriting case records."""

import argparse
import hashlib
import json
from pathlib import Path

from content_agent.cli import write_json
from content_agent.evaluation import evaluate_result
from content_agent.tools import load_catalog
from run_examples import case_errors


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--roots", nargs="*", type=Path,
                        default=[Path("examples/mock"), Path("examples/online"), Path("examples/online-expanded")])
    args = parser.parse_args()
    checked, errors = [], []
    for root in args.roots:
        manifest = read(root / "manifest.json")
        for name, expected in manifest["source_sha256"].items():
            path = Path(name)
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                errors.append(f"{root}: 源文件已变化：{name}")
        for entry in manifest["cases"]:
            directory = root / entry["case"]
            result = read(directory / "output.json")
            scenario = read(directory / "scenario.json")
            catalog = load_catalog(directory / "catalog.json")
            saved_path = directory / "saved-plan.json"
            saved = read(saved_path) if saved_path.exists() else None
            checks = evaluate_result(result, saved, scenario, catalog)
            checks += case_errors(entry["scenario"], result)
            if result["model_mode"] != manifest["mode"] or result["model_name"] != manifest["model"]:
                checks.append("模型标记与清单不一致")
            if result["trace"] != read(directory / "trace.json"):
                checks.append("独立 Trace 与输出不一致")
            if result["request"] != read(directory / "input.json"):
                checks.append("实际输入与输出不一致")
            if result["catalog_version"] != catalog["version"]:
                checks.append("费用表版本不一致")
            for key, actual in {"status": result["status"], "reason_code": result["reason_code"],
                                "model_calls": result["calls"]["model"], "tool_calls": result["calls"]["tools"],
                                "spent": result["cost"]["spent"]}.items():
                if entry[key] != actual:
                    checks.append(f"清单字段 {key} 与结果不一致")
            if entry["scenario"] == "E07-duplicate":
                replay = read(directory / "replay.json")
                storage = read(directory / "storage-check.json")
                if replay != {**result, "replayed": True} or storage != {"saved_plan_count": 1, "replay_unchanged": True}:
                    checks.append("重复执行证据不一致")
            verdict = {"passed": not checks, "errors": checks}
            if verdict != read(directory / "evaluation.json") or verdict != entry["evaluation"]:
                errors.append(f"{directory}: 保存的评估结论与重算不一致")
            checked.append({"directory": directory.as_posix(), "scenario": entry["scenario"],
                            "model_mode": result["model_mode"], "status": result["status"],
                            "spent": result["cost"]["spent"], "model_calls": result["calls"]["model"],
                            "simulated_minutes": result["time"]["simulated_minutes"],
                            "total_tokens": sum(u.get("total_tokens", 0) for u in result["cost"]["api_usage"]),
                            "evaluation": verdict})
    report = {"verified": not errors, "cases_checked": len(checked), "consistency_errors": errors,
              "all_cases_passed": all(case["evaluation"]["passed"] for case in checked), "cases": checked}
    write_json(Path("examples/evidence-check.json"), report)
    print(json.dumps({key: value for key, value in report.items() if key != "cases"}, ensure_ascii=False, indent=2))
    return 0 if report["verified"] and report["all_cases_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
