"""StateGraph execution with deterministic guards and model-selected business actions."""

import copy
import hashlib
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import TypedDict
from uuid import uuid4

from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from .models import ModelFailure
from .schemas import ACTION_MODELS, Request, Scenario
from .storage import Store, dumps
from .tools import BUSINESS_TOOLS, BusinessTools, current_script


class GraphState(TypedDict):
    # A single full snapshot avoids accidental partial dict/list reducer merges.
    task: dict


class Agent:
    def __init__(self, store: Store, model, catalog: dict):
        self.store, self.model, self.catalog = store, model, catalog
        self.tools = BusinessTools(catalog)
        self.latest: dict | None = None
        graph = StateGraph(GraphState)
        for name in ("intake", "decide", "validate_action", "execute", "finalize"):
            graph.add_node(name, getattr(self, name))
        graph.add_edge(START, "intake")
        graph.add_conditional_edges("intake", lambda s: "finalize" if s["task"]["status"] != "running" else "decide")
        graph.add_conditional_edges("decide", lambda s: "validate_action" if s["task"]["status"] == "running" else "finalize")
        graph.add_conditional_edges("validate_action", lambda s: s["task"].get("route", "finalize"))
        graph.add_conditional_edges("execute", lambda s: "decide" if s["task"]["status"] == "running" else "finalize")
        graph.add_edge("finalize", END)
        self.graph = graph.compile()

    def checkpoint(self, state: dict, plan: dict | None = None) -> dict:
        self.store.write(state, plan)
        self.latest = copy.deepcopy(state)
        return {"task": state}

    def run(self, request: Request, scenario: Scenario | None = None) -> dict:
        scenario = scenario or Scenario()
        payload = request.model_dump(mode="json")
        fingerprint = hashlib.sha256(dumps(payload).encode()).hexdigest()
        previous = self.store.get(request.request_id)
        if previous:
            if previous["fingerprint"] != fingerprint:
                return {"request_id": request.request_id, "status": "incomplete", "reason_code": "REQUEST_CONFLICT",
                        "reason": "相同请求 ID 携带不同输入，请使用新 ID", "replayed": False, "trace": []}
            # Replaying never resumes running/interrupted work or makes model calls.
            return self.output(previous["state"], replayed=True)
        start = scenario.start_at or datetime.now(timezone(timedelta(hours=8)))
        state = {"run_id": str(uuid4()), "request": payload, "fingerprint": fingerprint,
                 "model_mode": self.model.mode, "model_name": self.model.model_id,
                 "catalog_version": self.catalog["version"], "status": "running", "reason_code": None,
                 "reason": None, "missing_fields": [], "start_at": start.isoformat(), "elapsed_minutes": 0,
                 "model_calls": 0, "tool_calls": 0,
                 "limits": {"max_model_calls": scenario.max_model_calls, "max_tool_calls": scenario.max_tool_calls,
                            "recursion_limit": scenario.recursion_limit},
                 "plan": None, "plans": [], "materials": {}, "scripts": {}, "estimate": None,
                 "steps": [], "trace": [], "usage": [], "spent": 0, "cost_events": [], "saved": None,
                 "last_observation": None, "action": None, "failures_left": dict(scenario.failures),
                 "wall_seconds": 0.0}
        self.latest = state
        clock = time.perf_counter()
        try:
            state = self.graph.invoke({"task": state}, config={"recursion_limit": scenario.recursion_limit})["task"]
        except GraphRecursionError:
            state = copy.deepcopy(self.latest)
            state.update(status="incomplete", reason_code="GRAPH_LIMIT", reason="LangGraph 执行上限已达到")
            state = self.finalize({"task": state})["task"]
        except (OSError, RuntimeError, sqlite3.Error) as exc:
            state = copy.deepcopy(self.latest)
            state.update(status="incomplete", reason_code="RUNTIME_ERROR", reason=f"执行失败：{type(exc).__name__}")
            state = self.finalize({"task": state})["task"]
        state["wall_seconds"] = round(time.perf_counter() - clock, 4)
        self.checkpoint(state)
        return self.output(state)

    def intake(self, wrapper: GraphState) -> dict:
        state = copy.deepcopy(wrapper["task"])
        missing = [field for field in ("theme", "budget", "deadline") if state["request"][field] is None
                   or (field == "theme" and not state["request"][field].strip())]
        if missing:
            state.update(status="waiting_input", reason_code="MISSING_FIELDS", missing_fields=missing,
                         reason="请补充：" + ", ".join(missing))
        elif datetime.fromisoformat(state["request"]["deadline"]) < datetime.fromisoformat(state["start_at"]):
            state.update(status="incomplete", reason_code="DEADLINE_PASSED", reason="截止时间已经过去")
        return self.checkpoint(state)

    def decide(self, wrapper: GraphState) -> dict:
        state = copy.deepcopy(wrapper["task"])
        if (state["model_calls"] >= state["limits"]["max_model_calls"]
                or (state["tool_calls"] >= state["limits"]["max_tool_calls"] and not state["saved"])):
            state.update(status="incomplete", reason_code="CALL_LIMIT", reason="模型或工具调用上限已达到")
            return self.checkpoint(state)
        state["model_calls"] += 1
        try:
            state["action"] = self.model.choose(copy.deepcopy(state))
        except ModelFailure as exc:
            state.update(status="incomplete", reason_code="MODEL_ERROR", reason=str(exc))
            state["trace"].append({"step": len(state["trace"]) + 1, "kind": "model_error",
                                   "model_mode": state["model_mode"], "message": str(exc)})
        return self.checkpoint(state)

    def validate_action(self, wrapper: GraphState) -> dict:
        state = copy.deepcopy(wrapper["task"])
        action = state["action"]
        name, args = action.get("name"), action.get("arguments")
        if action.get("usage"):
            state["usage"].append(action["usage"])
        if state["trace"]:
            state["trace"][-1]["next_action"] = name
        entry = {"step": len(state["trace"]) + 1, "kind": "decision", "model_mode": state["model_mode"],
                 "response_model": action.get("response_model"), "action": name,
                 "parameters": args, "reason": args.get("reason") if isinstance(args, dict) else None,
                 "plan_version": state["plan"]["version"] if state["plan"] else None,
                 "model_call": state["model_calls"], "tool_calls": state["tool_calls"]}
        state["trace"].append(entry)
        try:
            if name not in ACTION_MODELS:
                raise ValueError("未知动作或模型没有返回一个函数调用")
            args = ACTION_MODELS[name].model_validate(args).model_dump()
            state["action"]["arguments"] = args
            if state["saved"] and name != "finish_task":
                raise ValueError("方案已经保存，请结束任务，不再执行其他动作")
            if name in BUSINESS_TOOLS:
                if state["tool_calls"] >= state["limits"]["max_tool_calls"]:
                    state.update(status="incomplete", reason_code="CALL_LIMIT", reason="工具调用上限已达到")
                    state["route"] = "finalize"
                else:
                    state["route"] = "execute"
            elif name == "update_plan":
                if args["variant"] not in self.catalog["variants"]:
                    raise ValueError("variant 不存在")
                if len(set(args["material_ids"])) != len(args["material_ids"]):
                    raise ValueError("素材 ID 不得重复")
                if any(mid not in state["materials"] for mid in args["material_ids"]):
                    raise ValueError("模型只能选用已经检索到的素材")
                version = len(state["plans"]) + 1
                state["plan"] = {"version": version, "variant": args["variant"], "material_ids": args["material_ids"],
                                 "objective": state["request"]["theme"],
                                 "steps": [{"id": "search", "tool": "search_materials", "depends_on": []},
                                           {"id": "estimate_before", "tool": "estimate_plan", "depends_on": ["search"]},
                                           {"id": "script", "tool": "generate_script", "depends_on": ["estimate_before"]},
                                           {"id": "estimate_after", "tool": "estimate_plan", "depends_on": ["script"]},
                                           {"id": "save", "tool": "save_plan", "depends_on": ["estimate_after"]}]}
                state["plans"].append(copy.deepcopy(state["plan"]))
                for step in state["plan"]["steps"]:
                    step["status"] = "succeeded" if step["id"] == "search" else "pending"
                if current_script(state):
                    state["plan"]["steps"][1]["status"] = "skipped"
                    state["plan"]["steps"][2].update(status="succeeded", reused=True)
                state["plans"][-1] = copy.deepcopy(state["plan"])
                state["estimate"] = None
                observation = {"status": "succeeded", "plan": state["plan"]}
                entry["observation"] = observation
                state["last_observation"] = observation
                state["route"] = "decide"
            elif name == "request_information":
                state.update(status="waiting_input", reason_code="NEEDS_INFORMATION", reason=args["reason"],
                             missing_fields=args["missing_fields"], route="finalize")
            else:
                state.update(status=args["status"], reason=args["reason"], reason_code="MODEL_FINISH", route="finalize")
        except (ValueError, ValidationError, TypeError):
            observation = {"status": "rejected", "error_code": "INVALID_ACTION", "message": "动作名、参数或依赖无效；请检查现有素材，已保存方案只能结束"}
            entry["observation"] = observation
            state["last_observation"] = observation
            state["route"] = "decide"
        return self.checkpoint(state)

    def execute(self, wrapper: GraphState) -> dict:
        state = copy.deepcopy(wrapper["task"])
        name, args = state["action"]["name"], state["action"]["arguments"]
        state["tool_calls"] += 1
        observation, plan = self.tools.invoke(state, name, args)
        observation["tool"] = name
        step = {"id": len(state["steps"]) + 1, "tool": name, "status": observation["status"],
                "plan_version": state["plan"]["version"] if state["plan"] else None,
                "result": observation, "spent_after": state["spent"], "elapsed_after": state["elapsed_minutes"]}
        state["steps"].append(step)
        if state["plan"]:
            step_id = {"generate_script": "script", "save_plan": "save", "search_materials": "search"}.get(name)
            if name == "estimate_plan":
                step_id = "estimate_after" if current_script(state) else "estimate_before"
            for planned_step in state["plan"]["steps"]:
                if planned_step["id"] == step_id:
                    # Attempts are recorded above. A rejected retry cannot erase
                    # a usable result already produced for this plan version.
                    if (observation["status"] == "succeeded"
                            or planned_step["status"] not in {"succeeded", "skipped"}):
                        planned_step["status"] = observation["status"]
            state["plans"][-1] = copy.deepcopy(state["plan"])
            if plan is not None:
                plan["plan"] = copy.deepcopy(state["plan"])
        state["last_observation"] = observation
        state["trace"][-1].update(observation=observation, tool_calls=state["tool_calls"],
                                  spent_after=state["spent"], elapsed_after=state["elapsed_minutes"])
        return self.checkpoint(state, plan)

    def finalize(self, wrapper: GraphState) -> dict:
        state = copy.deepcopy(wrapper["task"])
        if state["status"] == "completed":
            stored = self.store.read_plan(state["request"]["request_id"])
            finish = datetime.fromisoformat(state["start_at"]) + timedelta(minutes=state["elapsed_minutes"])
            if (not state["saved"] or not stored or not current_script(state)
                    or state["spent"] > state["request"]["budget"]
                    or finish > datetime.fromisoformat(state["request"]["deadline"])
                    or stored["plan"] != state["plan"]
                    or stored["script"] != current_script(state)
                    or stored["total_spent"] != state["spent"]
                    or any(step["status"] not in {"succeeded", "skipped"}
                           for step in state["plan"]["steps"])):
                state.update(status="incomplete", reason_code="UNVERIFIED_COMPLETION", reason="完成声明没有通过保存与约束核验")
        state.pop("route", None)
        state["trace"].append({"step": len(state["trace"]) + 1, "kind": "terminal", "status": state["status"],
                               "reason_code": state["reason_code"], "reason": state["reason"]})
        return self.checkpoint(state)

    @staticmethod
    def output(state: dict, replayed: bool = False) -> dict:
        status = state["status"]
        reason = state["reason"]
        code = state["reason_code"]
        if replayed and status == "running":
            status, code, reason = "incomplete", "INTERRUPTED", "先前执行已中断；重复请求不会自动续跑"
        return {"request_id": state["request"]["request_id"], "run_id": state["run_id"],
                "status": status, "reason_code": code, "reason": reason, "replayed": replayed,
                "model_mode": state["model_mode"], "model_name": state["model_name"],
                "catalog_version": state["catalog_version"], "request": state["request"],
                "plan": state["plan"], "plan_history": state["plans"], "steps": state["steps"],
                "materials": state["materials"], "script": current_script(state), "saved": state["saved"],
                "cost": {"spent": state["spent"], "events": state["cost_events"], "estimate": state["estimate"],
                         "api_usage": state["usage"], "api_fee": None},
                "time": {"start_at": state["start_at"], "simulated_minutes": state["elapsed_minutes"],
                         "wall_seconds": state["wall_seconds"]},
                "calls": {"model": state["model_calls"], "tools": state["tool_calls"]},
                "missing_fields": state["missing_fields"], "trace": state["trace"]}
