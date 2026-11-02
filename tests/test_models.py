import json
from types import SimpleNamespace

from content_agent.models import OnlineModel


def test_online_model_only_receives_observed_failures(run_agent, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "local-test-only")
    model = OnlineModel()
    captured = []

    def respond(**kwargs):
        captured.append(kwargs)
        function = SimpleNamespace(name="finish_task", arguments=json.dumps({"reason": "测试结束", "status": "incomplete"}))
        return SimpleNamespace(usage=None, model=model.model_id,
                               choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[SimpleNamespace(function=function)]))])

    monkeypatch.setattr(model.client.chat.completions, "create", respond)
    result, _, _ = run_agent(config={"failures": {"generate_script": 1}}, model=model)
    content = captured[0]["messages"][1]["content"]
    assert "failures" not in content and "failures_left" not in content
    assert "local-test-only" not in content
    assert result["model_mode"] == "online"
    assert captured[0]["tool_choice"] == "required"
