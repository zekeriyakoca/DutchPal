from fastapi import APIRouter
from httpx import AsyncClient
from services.app_service import translate
from tools.agent import language_agent, SessionLocal, Deps
from pydantic import BaseModel
from utils.provider_errors import raise_openai_unavailable_if_provider_error

router = APIRouter()


class TranslateRequest(BaseModel):
    message: str  # the sentence to translate


@router.post("/translate")
async def translate_sentence(req: TranslateRequest):
    try:
        response = await translate(req.message)
    except Exception as exc:
        raise_openai_unavailable_if_provider_error(exc)
    return {"response": response}
