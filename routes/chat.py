from fastapi import APIRouter
from httpx import AsyncClient
from tools.agent import language_agent, SessionLocal, Deps
from pydantic import BaseModel

router = APIRouter()

class ChatRequest(BaseModel):
    message: str  # raw chat input

@router.post("/chat")
async def chat(req: ChatRequest):
    async with AsyncClient() as client:
        db = SessionLocal()
        deps = Deps(client=client, db=db)
        result = await language_agent.run(req.message, deps=deps)
        return {"response": result.data}
