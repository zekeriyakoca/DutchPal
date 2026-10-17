from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from httpx import AsyncClient
from tools.agent import language_agent, Deps
from pydantic import BaseModel
from utils.agent_result import agent_output
from utils.db import get_db
from utils.provider_errors import raise_openai_unavailable_if_provider_error

router = APIRouter()


class ChatRequest(BaseModel):
    message: str  # raw chat input


@router.post("/chat")
async def chat(req: ChatRequest, db: Session = Depends(get_db)):
    async with AsyncClient(timeout=60) as client:
        deps = Deps(client=client, db=db)
        try:
            result = await language_agent.run(req.message, deps=deps)
        except Exception as exc:
            raise_openai_unavailable_if_provider_error(exc)
        return {"response": agent_output(result)}
