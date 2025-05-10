from fastapi import APIRouter
from httpx import AsyncClient
from tools.agent import language_agent, SessionLocal, Deps
from pydantic import BaseModel

router = APIRouter()

class TranslateRequest(BaseModel):
    message: str  # the sentence to translate

@router.post("/translate")
async def translate_sentence(req: TranslateRequest):
    prompt = build_translation_prompt(req.message)

    async with AsyncClient() as client:
        db = SessionLocal()
        deps = Deps(client=client, db=db)
        result = await language_agent.run(prompt, deps=deps)
        return {"response": result.data}


def build_translation_prompt(sentence: str) -> str:
    return f"Translate the sentence '{sentence}' into English. Highlight the important words in the sentence. No extra text or explanation needed. If the sentence is not in good shape, intelligently correct it."
