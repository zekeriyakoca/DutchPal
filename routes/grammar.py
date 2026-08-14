from fastapi import APIRouter
from httpx import AsyncClient
from pydantic import BaseModel
from services.app_service import explain_grammar, explain
from utils.provider_errors import raise_openai_unavailable_if_provider_error

router = APIRouter()


class ExplanationRequest(BaseModel):
    message: str  # the sentence to analyze


@router.post("/explain-grammar")
async def explain_grammar_of_sentence(req: ExplanationRequest):

    async with AsyncClient() as client:
        try:
            result = await explain_grammar(client, req.message)
        except Exception as exc:
            raise_openai_unavailable_if_provider_error(exc)
        return {"response": result}


@router.post("/explain")
async def explain_text(req: ExplanationRequest):
    try:
        result = await explain(req.message)
    except Exception as exc:
        raise_openai_unavailable_if_provider_error(exc)
    return {"response": result}
