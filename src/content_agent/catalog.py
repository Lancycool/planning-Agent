"""Validate the complete synthetic catalog before any model or tool runs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator


class CatalogRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Material(CatalogRecord):
    id: str = Field(min_length=1)
    tags: list[str] = Field(min_length=1)
    facts: list[str] = Field(min_length=1)

    @field_validator("tags", "facts")
    @classmethod
    def nonblank_items(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("素材标签和事实不能为空白")
        return values


class Variant(CatalogRecord):
    label: str = Field(min_length=1)
    generation_fee: StrictInt = Field(ge=0)
    generation_minutes: StrictInt = Field(ge=0)
    deliverable: str = Field(min_length=1)


class FreeTool(CatalogRecord):
    fee: StrictInt = Field(ge=0, le=0)
    minutes: StrictInt = Field(ge=0)


class GenerationTool(CatalogRecord):
    fee: Literal["variant.generation_fee"]
    minutes: Literal["variant.generation_minutes"]


class ToolRules(CatalogRecord):
    search_materials: FreeTool
    estimate_plan: FreeTool
    generate_script: GenerationTool
    save_plan: FreeTool


class Billing(CatalogRecord):
    unit: str = Field(min_length=1)
    charge_on: Literal["generate_script 成功返回时"]
    failed_call_fee: StrictInt = Field(ge=0, le=0)
    failed_call_time: Literal["与成功调用相同"]
    estimate_is_spend: Literal[False]
    no_real_payment_or_publication: Literal[True]


class Catalog(CatalogRecord):
    version: str = Field(min_length=1)
    materials: list[Material]
    variants: dict[str, Variant] = Field(min_length=1)
    tools: ToolRules
    billing: Billing

    @field_validator("materials")
    @classmethod
    def unique_ids(cls, values: list[Material]) -> list[Material]:
        ids = [value.id for value in values]
        if len(ids) != len(set(ids)):
            raise ValueError("素材 ID 不得重复")
        return values

    @field_validator("variants")
    @classmethod
    def supported_variants(cls, values: dict[str, Variant]) -> dict[str, Variant]:
        if not {"premium", "basic"} <= values.keys():
            raise ValueError("当前离线模拟器要求 premium 和 basic 两种方案")
        return values
