from typing import Any


def agent_output(result: Any) -> Any:
    return getattr(result, "output", getattr(result, "data", result))
