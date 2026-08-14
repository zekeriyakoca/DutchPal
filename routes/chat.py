from fastapi import APIRouter
from httpx import AsyncClient
from tools.agent import language_agent, SessionLocal, Deps
from pydantic import BaseModel
from utils.agent_result import agent_output
from utils.provider_errors import raise_openai_unavailable_if_provider_error

router = APIRouter()


class ChatRequest(BaseModel):
    message: str  # raw chat input


@router.post("/chat")
async def chat(req: ChatRequest):
    async with AsyncClient() as client:
        db = SessionLocal()
        deps = Deps(client=client, db=db)
        try:
            result = await language_agent.run(req.message, deps=deps)
        except Exception as exc:
            raise_openai_unavailable_if_provider_error(exc)
        return {"response": agent_output(result)}
