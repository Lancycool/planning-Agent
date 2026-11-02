import copy
import json

import pytest
from pydantic import ValidationError

from content_agent.cli import main
from content_agent.tools import load_catalog
from conftest import BASE, ROOT


@pytest.mark.parametrize("case", ["deliverable", "duplicate_id", "bad_tags", "negative_time", "boolean_fee",
                                  "billing", "tool_fee", "missing_variant"])
def test_invalid_catalog_is_rejected_before_execution(tmp_path, case, monkeypatch, capsys):
    catalog = copy.deepcopy(load_catalog(ROOT / "data/catalog.json"))
    if case == "deliverable":
        del catalog["variants"]["premium"]["deliverable"]
    elif case == "duplicate_id":
        catalog["materials"].append(copy.deepcopy(catalog["materials"][0]))
    elif case == "bad_tags":
        catalog["materials"][0]["tags"] = "字幕"
    elif case == "negative_time":
        catalog["tools"]["search_materials"]["minutes"] = -1
    elif case == "boolean_fee":
        catalog["variants"]["premium"]["generation_fee"] = True
    elif case == "billing":
        catalog["billing"]["failed_call_fee"] = 1
    elif case == "tool_fee":
        catalog["tools"]["save_plan"]["fee"] = 1
    else:
        del catalog["variants"]["basic"]
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_catalog(path)

    def never_call(self, state):
        raise AssertionError("无效配置不得调用模型")

    monkeypatch.setattr("content_agent.models.MockModel.choose", never_call)
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(BASE), encoding="utf-8")
    db_path = tmp_path / "tasks.sqlite3"
    assert main(["--mode", "mock", "--input", str(input_path), "--catalog", str(path), "--db", str(db_path)]) == 2
    assert json.loads(capsys.readouterr().out)["reason_code"] == "INVALID_INPUT_OR_CONFIG"
    assert not db_path.exists()
