"""Strict action contracts shared by online and offline models."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Request(Contract):
    request_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    theme: str | None = Field(default=None, max_length=500)
    budget: StrictInt | None = Field(default=None, ge=0)
    deadline: datetime | None = None

    @field_validator("deadline")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("deadline 必须包含时区，例如 +08:00")
        return value


class Reason(Contract):
    reason: str = Field(min_length=1, max_length=500, description="简要说明动作依据，不输出内部思维过程")


class Search(Reason):
    query: str = Field(min_length=1, max_length=200)


class Plan(Reason):
    variant: str = Field(min_length=1)
    material_ids: list[str] = Field(min_length=1, max_length=10)


class EmptyArgs(Reason):
    pass


class Finish(Reason):
    status: Literal["completed", "incomplete"]


class Ask(Reason):
    missing_fields: list[str] = Field(min_length=1)


ACTION_MODELS = {
    "search_materials": Search,
    "update_plan": Plan,
    "estimate_plan": EmptyArgs,
    "generate_script": EmptyArgs,
    "save_plan": EmptyArgs,
    "finish_task": Finish,
    "request_information": Ask,
}

DESCRIPTIONS = {
    "search_materials": "按查询检索本地合成素材。返回素材事实和可选方案费用、耗时。",
    "update_plan": "模型选定方案 variant 与检索过的素材 ID，建立新计划版本。不会执行内容制作。",
    "estimate_plan": "核算当前计划的已发生费用、剩余费用、时间与缺口。估算不收费。生成后必须重新估算。",
    "generate_script": "按当前计划生成本地模拟脚本。必须先取得当前计划的可行估算。成功时收取方案费用。",
    "save_plan": "保存当前脚本。必须有生成后的可行估算。只有成功保存才可报告完成。",
    "finish_task": "根据实际结果结束任务。无法满足约束时选 incomplete，说明具体原因。",
    "request_information": "关键输入或素材不足时请求补充，任务进入 waiting_input。",
}


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {"type": "function", "function": {"name": name, "description": DESCRIPTIONS[name],
         "parameters": schema.model_json_schema()}}
        for name, schema in ACTION_MODELS.items()
    ]


class Scenario(Contract):
    start_at: datetime | None = None
    failures: dict[str, int] = Field(default_factory=dict)
    max_model_calls: int = Field(default=16, ge=1, le=100)
    max_tool_calls: int = Field(default=12, ge=1, le=100)
    recursion_limit: int = Field(default=100, ge=2, le=1000)

    @field_validator("start_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        return Request.require_timezone(value)

    @field_validator("failures")
    @classmethod
    def validate_failures(cls, value: dict[str, int]) -> dict[str, int]:
        if any(k not in {"search_materials", "estimate_plan", "generate_script", "save_plan"}
               or type(v) is not int or v < 0 for k, v in value.items()):
            raise ValueError("failures 只接受业务工具名和非负整数次数")
        return value
