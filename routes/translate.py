from fastapi import APIRouter
from httpx import AsyncClient
from services.app_service import translate
from tools.agent import language_agent, SessionLocal, Deps
from pydantic import BaseModel

router = APIRouter()


class TranslateRequest(BaseModel):
    message: str  # the sentence to translate


@router.post("/translate")
async def translate_sentence(req: TranslateRequest):
    response = await translate(req.message)
    return {"response": response}
