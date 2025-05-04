from fastapi import APIRouter
from httpx import AsyncClient
from tools.agent import language_agent, SessionLocal, Deps
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class QueryRequest(BaseModel):
    message: str
    page: str
    level: str = "All Levels"
    difficulty: int = 5
    number_of_entries: int = 1
    book_id: Optional[int] = None
    word_type: Optional[str] = None
    quiz_type: Optional[str] = None


@router.post("/ask")
async def ask_language_agent(req: QueryRequest):
    async with AsyncClient() as client:
        db = SessionLocal()
        deps = Deps(client=client, db=db)
        prompt = build_prompt(
            req.page,
            req.message,
            req.level,
            req.difficulty,
            req.number_of_entries,
            req.book_id,
            req.word_type,
            req.quiz_type,
        )
        result = await language_agent.run(prompt, deps=deps)
        return {"response": result.data}


def build_prompt(
    page: str,
    input_text: str,
    level: str,
    difficulty: int,
    number_of_entries: int,
    book_id: Optional[int],
    word_type: str,
    quiz_type,
) -> str:
    book_selection_directive = (
        f"- Target book is the book with ID {book_id}.\n" if book_id else ""
    )

    if page == "vocab":
        return f"""
            Generate a **Markdown table** of Dutch vocabulary.
            {get_translation_directive(input_text,number_of_entries)}
            {book_selection_directive}
            - CEFR Level should be: {level}
            - Type of the word should be: {word_type}
            ...
            """
    elif page == "sentences":
        return f"""
            Return {number_of_entries} random Dutch sentences.
            - CEFR Level: {level}
            {book_selection_directive}
            ...
            """
    elif page == "quiz":
        return f"""
            Generate a **Dutch {quiz_type} quiz**.
            - CEFR Level: {level}
            - Difficulty: {difficulty}
            - Number of questions: {number_of_entries}
            {book_selection_directive}
            ...
            """
    elif page == "translate-sentence":
        return f"Translate the sentence '{input_text}' into English. Highlight the important words."
    elif page == "grammar":
        return f"Explain the Dutch grammar in this sentence: {input_text}"
    return input_text


def get_translation_directive(input_text: str, number_of_entries: int) -> str:
    return (
        f"- Translate the word '{input_text}'."
        if input_text.strip()
        else f"- Total number of vocabulary entries: {number_of_entries}\n- Select words **randomly from the dataset**"
    )
