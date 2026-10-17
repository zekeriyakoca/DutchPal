import asyncio
import re
from typing import Callable, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LlmJsonError(Exception):
    """The LLM's reply was not the JSON object we asked for; main.py turns it into a 502."""

    def __init__(self, message: str = "The AI returned an answer we could not read. Please try again."):
        super().__init__(message)


def extract_json_object(text: str) -> str:
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end >= start:
        return cleaned[start : end + 1]
    return cleaned


def parse_llm_json(text: str, model: type[T]) -> T:
    try:
        return model.model_validate_json(extract_json_object(text))
    except ValidationError as exc:
        raise LlmJsonError() from exc


async def ask_llm_json(chat: Callable[[str], str], prompt: str, model: type[T], attempts: int = 2) -> T:
    """
    Sends `prompt` to a sync chat function and validates the reply against `model`.
    A malformed reply is retried once before giving up with LlmJsonError.
    """
    for attempt in range(1, attempts + 1):
        reply = await asyncio.to_thread(chat, prompt)
        try:
            return parse_llm_json(reply, model)
        except LlmJsonError:
            print(f"Unreadable LLM reply (attempt {attempt}/{attempts}): {reply!r}")
    raise LlmJsonError()
