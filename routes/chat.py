from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from httpx import AsyncClient
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, SystemPromptPart, TextPart, UserPromptPart
from tools.agent import language_agent, Deps, system_prompt
from pydantic import BaseModel
from utils.agent_result import agent_output
from utils.db import get_db
from utils.provider_errors import raise_openai_unavailable_if_provider_error

router = APIRouter()

MAX_HISTORY_TURNS = 20


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str  # raw chat input
    history: list[ChatTurn] = []  # earlier turns on the page, oldest first; not stored


@router.post("/chat")
async def chat(req: ChatRequest, db: Session = Depends(get_db)):
    async with AsyncClient(timeout=60) as client:
        deps = Deps(client=client, db=db)
        try:
            result = await language_agent.run(
                req.message, deps=deps, message_history=to_message_history(req.history)
            )
        except Exception as exc:
            raise_openai_unavailable_if_provider_error(exc)
        return {"response": agent_output(result)}


def to_message_history(history: list[ChatTurn]) -> list[ModelMessage]:
    # pydantic-ai only adds the system prompt when the history is empty, so it goes first here.
    if not history:
        return []
    messages: list[ModelMessage] = [ModelRequest(parts=[SystemPromptPart(system_prompt)])]
    for turn in history[-MAX_HISTORY_TURNS:]:
        if turn.role == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(turn.content)]))
        else:
            messages.append(ModelResponse(parts=[TextPart(turn.content)]))
    return messages
