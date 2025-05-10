from fastapi import APIRouter
from httpx import AsyncClient
from tools.agent import language_agent, SessionLocal, Deps
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class VocabRequest(BaseModel):
    message: str = ""
    level: str = "All Levels"
    number_of_entries: int = 1
    book_id: Optional[int] = None
    word_type: Optional[str] = None


@router.post("/vocabulary")
async def get_vocabulary(req: VocabRequest):
    prompt = build_vocab_prompt(
        input_text=req.message,
        level=req.level,
        number_of_entries=req.number_of_entries,
        book_id=req.book_id,
        word_type=req.word_type,
    )

    async with AsyncClient() as client:
        db = SessionLocal()
        deps = Deps(client=client, db=db)
        result = await language_agent.run(prompt, deps=deps)
        return {"response": result.data}


def build_vocab_prompt(
    input_text: str,
    level: str,
    number_of_entries: int,
    book_id: Optional[int],
    word_type: Optional[str],
) -> str:
    book_selection_directive = (
        f"- Target book is the book with ID {book_id}.\n" if book_id else ""
    )

    translation_directive = (
        f"- Translate the word '{input_text}'."
        if input_text.strip()
        else f"""
        - Total number of vocabulary entries: {number_of_entries}\n- Select words **randomly from the dataset**
        - CEFR Level should be: {level}
        - Type of the word should be: {word_type} (pos column in dataset)
        """
    )

    return f"""
    Generate a **Markdown table** of Dutch vocabulary.
    {translation_directive}
    {book_selection_directive}

    - For conjugation columns (Present, V2, V3), list only the **conjugated forms** separated by slashes, like: `woon/woont/wonen` — do **not** include pronouns (ik/jij/wij).

    - Include the following columns:

    - Word (e.g. wonen; base/dictionary form)
    - Level (CEFR)  
    - Translation (short English meaning)  
    - Examples (3 example sentences containing the word; use book(from dataset) examples if available, otherwise, return empty. Word should be bold. Seperate each example with a <br> tag. e.g. Uit welk land komt u?<br>Uit welk land kom je?)  
    - Present ik/jij/wij (e.g. woon/woont/wonen; empty if not verb)
    - V2 ik/jij/wij (e.g. woonde/woonde/woonden; empty if not verb)
    - V3 ik/jij/wij (e.g. gewoond/gewond/gewonen; empty if not verb)
    - Imperative  (empty if not verb)

    Ensure **all columns are filled**. If any information is missing from the dataset, intelligently generate it. But first check the dataset for the information.

    Return the result **as a Markdown table only** — do not include any explanation or extra text.
    """
