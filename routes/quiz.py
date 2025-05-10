from fastapi import APIRouter
from httpx import AsyncClient
from tools.agent import language_agent, SessionLocal, Deps
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class QuizRequest(BaseModel):
    level: str = "All Levels"
    difficulty: int = 5
    number_of_entries: int = 5
    book_id: Optional[int] = None
    quiz_type: Optional[str] = None  # e.g., "grammar", "vocab", etc.

@router.post("/quiz")
async def generate_quiz(req: QuizRequest):
    prompt = build_quiz_prompt(
        level=req.level,
        difficulty=req.difficulty,
        number_of_entries=req.number_of_entries,
        book_id=req.book_id,
        quiz_type=req.quiz_type
    )

    async with AsyncClient() as client:
        db = SessionLocal()
        deps = Deps(client=client, db=db)
        result = await language_agent.run(prompt, deps=deps)
        return {"response": result.data}


def build_quiz_prompt(level: str, difficulty: int, number_of_entries: int, book_id: Optional[int], quiz_type: Optional[str]) -> str:
    book_selection_directive = f"- Use words or examples from book ID {book_id} when possible.\n" if book_id else ""

    return f"""
    Generate a **Dutch {quiz_type} quiz**.

    - CEFR Level: {level}  
    - Difficulty: {difficulty} (0–10 scale)  
    - Number of questions: {number_of_entries}  
    {book_selection_directive}
    - Do **not** include meta data like question type. Just the question number, question, and answer options as in 1. Question, A) Option 1, B) Option 2, etc.
    - Give the list of correct answers at the end of the quiz as in "Correct answers: 1. A, 2. B, 3. C, 4. D, 5. E" Make answers pale gray

    The quiz should be varied and engaging. Use multiple formats like:
    - Multiple choice
    - Fill in the blank
    - Sentence completion
    - Choose the correct translation
    - Paragraph-based questions (3 relevant questions. paragraph length is based on the CEFR level and difficulty) if question quantity is more than 10

    All questions should match the selected CEFR level and difficulty.

    Return the quiz as a **Markdown-formatted content** — **do not** include any explanation or extra text.
    """
