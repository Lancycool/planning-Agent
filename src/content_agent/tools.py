"""Deterministic local business tools; no publication, payments or arbitrary paths."""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from .catalog import Catalog
from .storage import dumps

BUSINESS_TOOLS = {"search_materials", "estimate_plan", "generate_script", "save_plan"}


def load_catalog(path: str | Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return Catalog.model_validate(payload).model_dump()


def script_key(state: dict) -> str:
    plan = state["plan"]
    return hashlib.sha256(dumps({"theme": state["request"]["theme"], "variant": plan["variant"],
                                 "material_ids": sorted(plan["material_ids"])}).encode()).hexdigest()


def current_script(state: dict) -> dict | None:
    return state["scripts"].get(script_key(state)) if state["plan"] else None


def projection(state: dict, catalog: dict, extra_minutes: int = 0) -> dict:
    spec = catalog["variants"][state["plan"]["variant"]]
    exists = current_script(state) is not None
    remaining_fee = 0 if exists else spec["generation_fee"]
    # A generated script needs a fresh estimate before saving.
    remaining_minutes = catalog["tools"]["save_plan"]["minutes"]
    if not exists:
        remaining_minutes += spec["generation_minutes"] + catalog["tools"]["estimate_plan"]["minutes"]
    total = state["spent"] + remaining_fee
    finish = datetime.fromisoformat(state["start_at"]) + timedelta(
        minutes=state["elapsed_minutes"] + extra_minutes + remaining_minutes)
    deadline = datetime.fromisoformat(state["request"]["deadline"])
    return {"plan_version": state["plan"]["version"], "script_key": script_key(state),
            "script_exists": exists, "spent": state["spent"], "remaining_fee": remaining_fee,
            "total_fee": total, "budget": state["request"]["budget"],
            "budget_gap": max(0, total - state["request"]["budget"]),
            "remaining_minutes": remaining_minutes, "estimated_finish": finish.isoformat(),
            "time_gap_minutes": max(0, (finish - deadline).total_seconds() / 60),
            "feasible": total <= state["request"]["budget"] and finish <= deadline}


class BusinessTools:
    def __init__(self, catalog: dict):
        self.catalog = catalog

    def guard(self, state: dict, name: str) -> str | None:
        if name == "search_materials":
            return None
        if state["plan"] is None:
            return "请先通过 update_plan 选择方案与素材"
        if name == "estimate_plan":
            return None
        estimate = state.get("estimate")
        if (not estimate or estimate["plan_version"] != state["plan"]["version"]
                or estimate["script_key"] != script_key(state)):
            return "当前方案缺少有效估算，请先调用 estimate_plan"
        if name == "generate_script" and current_script(state):
            return "当前输入已有成功脚本，请复用结果并估算、保存"
        if name == "save_plan" and (not current_script(state) or not estimate["script_exists"]):
            return "保存需要已生成脚本及生成后的新估算"
        if not estimate["feasible"] or not projection(state, self.catalog)["feasible"]:
            return "当前方案超出预算或截止时间，请调整计划或结束"
        return None

    def invoke(self, state: dict, name: str, args: dict) -> tuple[dict, dict | None]:
        """Mutate a private full-state copy; the caller persists each node snapshot."""
        reason = self.guard(state, name)
        if reason:
            return {"status": "rejected", "error_code": "PRECONDITION", "message": reason,
                    "retryable": False}, None
        spec = self.catalog["variants"][state["plan"]["variant"]] if state["plan"] else None
        minutes = spec["generation_minutes"] if name == "generate_script" else self.catalog["tools"][name]["minutes"]
        state["elapsed_minutes"] += minutes
        if state["failures_left"].get(name, 0) > 0:
            state["failures_left"][name] -= 1
            return {"status": "failed", "error_code": "INJECTED_FAILURE", "message": "合成场景注入工具失败",
                    "retryable": True, "charged": 0, "elapsed_minutes": minutes}, None
        if name == "search_materials":
            query = args["query"].casefold()
            found = [m for m in self.catalog["materials"] if m["id"].casefold() in query
                     or any(tag.casefold() in query for tag in m["tags"])]
            for material in found:
                state["materials"][material["id"]] = material
            data = {"materials": found, "variants": self.catalog["variants"],
                    "tool_rules": self.catalog["tools"], "catalog_version": self.catalog["version"]}
        elif name == "estimate_plan":
            data = projection(state, self.catalog)
            state["estimate"] = data
        elif name == "generate_script":
            facts = [fact for mid in state["plan"]["material_ids"] for fact in state["materials"][mid]["facts"]]
            script = {"theme": state["request"]["theme"], "variant": state["plan"]["variant"],
                      "source_ids": state["plan"]["material_ids"],
                      "sections": [{"title": "主题", "text": f"本次活动围绕{state['request']['theme']}展开。"},
                                   {"title": "素材事实", "text": "；".join(facts)},
                                   {"title": "行动提示", "text": "参与者可以了解素材信息，并选择后续关注内容。"}],
                      "generation_mode": "local_mock", "deliverable": spec["deliverable"]}
            state["scripts"][script_key(state)] = script
            state["spent"] += spec["generation_fee"]
            state["cost_events"].append({"tool": name, "script_key": script_key(state),
                                         "amount": spec["generation_fee"], "plan_version": state["plan"]["version"]})
            state["estimate"] = None
            data = {"script": script, "charged": spec["generation_fee"], "total_spent": state["spent"]}
        else:
            # Guard included the save duration; recheck after accounting for it.
            finish = datetime.fromisoformat(state["start_at"]) + timedelta(minutes=state["elapsed_minutes"])
            if finish > datetime.fromisoformat(state["request"]["deadline"]):
                return {"status": "failed", "error_code": "DEADLINE", "message": "保存已超过截止时间",
                        "retryable": False, "charged": 0}, None
            plan = {"plan_id": "plan_" + state["fingerprint"][:16], "request_id": state["request"]["request_id"],
                    "plan": state["plan"], "script": current_script(state), "cost_events": state["cost_events"],
                    "total_spent": state["spent"], "simulated_finish": finish.isoformat()}
            state["saved"] = {"plan_id": plan["plan_id"], "storage": "sqlite:plans", "request_id": plan["request_id"]}
            return {"status": "succeeded", "data": state["saved"], "charged": 0, "elapsed_minutes": minutes}, plan
        return {"status": "succeeded", "data": data, "charged": spec["generation_fee"] if name == "generate_script" else 0,
                "elapsed_minutes": minutes}, None
