from copenet.browser_agent.decision import DecisionError, parse_action_json


def test_parse_action_json_success() -> None:
    action = parse_action_json(
        '{"action":"click","element_id":"e1","reason":"Click result","confidence":0.8,"risk":2}'
    )
    assert action.action == "click"
    assert action.element_id == "e1"


def test_parse_action_json_rejects_invalid_json() -> None:
    try:
        parse_action_json("not json")
    except DecisionError as exc:
        assert "invalid JSON action" in str(exc)
    else:
        raise AssertionError("Expected DecisionError")


def test_parse_action_json_rejects_unknown_action() -> None:
    try:
        parse_action_json(
            '{"action":"explode","reason":"bad","confidence":0.1,"risk":1}'
        )
    except DecisionError as exc:
        assert "unknown action type" in str(exc)
    else:
        raise AssertionError("Expected DecisionError")
