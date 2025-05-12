from fastapi import APIRouter
from httpx import AsyncClient
from tools.agent import language_agent, SessionLocal, Deps
from pydantic import BaseModel
from services.app_service import explain_grammar

router = APIRouter()


class GrammarRequest(BaseModel):
    message: str  # the sentence to analyze


@router.post("/grammar")
async def explain_grammar_of_sentence(req: GrammarRequest):

    result = explain_grammar(req.message)
    return {"response": result.data}


#     prompt = build_grammar_prompt(req.message)

#     async with AsyncClient() as client:
#         db = SessionLocal()
#         deps = Deps(client=client, db=db)
#         result = await language_agent.run(prompt, deps=deps)
#         return {"response": result.data}


# def build_grammar_prompt(sentence: str) -> str:
#     return f"Explain the Dutch grammar in this sentence: {sentence}"
