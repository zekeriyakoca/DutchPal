from fastapi import APIRouter
from httpx import AsyncClient
from agent import language_agent, SessionLocal, Deps
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class SentenceRequest(BaseModel):
    level: str = "All Levels"
    number_of_entries: int = 1
    book_id: Optional[int] = None

@router.post("/sentences")
async def get_sentences(req: SentenceRequest):
    prompt = build_sentences_prompt(
        level=req.level,
        number_of_entries=req.number_of_entries,
        book_id=req.book_id,
    )

    async with AsyncClient() as client:
        db = SessionLocal()
        deps = Deps(client=client, db=db)
        result = await language_agent.run(prompt, deps=deps)
        return {"response": result.data}


def build_sentences_prompt(level: str, number_of_entries: int, book_id: Optional[int]) -> str:
    book_selection_directive = f"- Target book is the book with ID {book_id}.\n" if book_id else ""

    return f"""
    Return {number_of_entries} random Dutch sentences from the dataset.
    
    - Sentences should be at CEFR Level should be: {level}
    {book_selection_directive}

    For each sentence, include:
    - The original Dutch sentence  
    - Its English translation  

    Format the result as a **Markdown list**, with each item showing both the Dutch and English translation clearly.

    Use only sentences from the dataset. If there aren't enough for the given level, generate similar ones intelligently.  
    Return **only the Markdown table** with two column, Dutch and Translation, with no explanation or extra text.
    """
