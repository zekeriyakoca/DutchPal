from fastapi import APIRouter
from httpx import AsyncClient
from agent import language_agent, SessionLocal, Deps
from pydantic import BaseModel

router = APIRouter()

class GrammarRequest(BaseModel):
    message: str  # the sentence to analyze

@router.post("/grammar")
async def explain_grammar(req: GrammarRequest):
    prompt = build_grammar_prompt(req.message)

    async with AsyncClient() as client:
        db = SessionLocal()
        deps = Deps(client=client, db=db)
        result = await language_agent.run(prompt, deps=deps)
        return {"response": result.data}


def build_grammar_prompt(sentence: str) -> str:
    return f"Explain the Dutch grammar in this sentence: {sentence}"
