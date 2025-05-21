from fastapi import APIRouter
from httpx import AsyncClient
from services.app_service import get_paragraph_questions
from tools.agent import language_agent, SessionLocal, Deps
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class QuizRequest(BaseModel):
    level: str = "ALL LEVELS"
    difficulty: int = 5
    number_of_entries: int = 5
    book_id: Optional[int] = None
    quiz_type: Optional[str] = None  # e.g., "grammar", "vocab", etc.


@router.post("/quiz")
async def generate_quiz(req: QuizRequest):
    db = SessionLocal()

    if req.quiz_type == "PARAGRAPH":
        questionGroups = get_paragraph_questions(
            db,
            limit=req.number_of_entries,
            cefr_level=req.level,
        )
        return {"response": convert_question_groups_to_markdown(questionGroups)}

    prompt = build_quiz_prompt(
        level=req.level,
        difficulty=req.difficulty,
        number_of_entries=req.number_of_entries,
        book_id=req.book_id,
        quiz_type=req.quiz_type,
    )

    async with AsyncClient() as client:
        deps = Deps(client=client, db=db)
        result = await language_agent.run(prompt, deps=deps)
        return {"response": result.data}


def convert_question_groups_to_markdown(data: list) -> str:
    """
    Converts question group data into Markdown:
    - # Title
    - Paragraph
    - ### Vragen (with spacing)
    - #### Antwoorden (at bottom, lowercase, with newlines between)
    """
    question_lines = []
    answer_lines = []

    for group in data:
        question_lines.append(f"# {group['title'].strip()}")
        question_lines.append(group["text"].strip())
        question_lines.append("")
        question_lines.append("### Vragen")

        for i, question in enumerate(group["questions"], 1):
            question_lines.append(f"{i}- {question['question_text'].strip()}")
            question_lines.append("")  # blank line after each question

        for i, question in enumerate(group["questions"], 1):
            answer_text = " / ".join(a.strip().lower() for a in question["answers"])
            answer_lines.append(f"{i}: {answer_text}")

        question_lines.append("")  # space between groups
        answer_lines.append("")  # space between answer groups

    question_lines.append("#### Antwoorden")
    question_lines.append("")
    question_lines.extend(answer_lines)

    return "\n".join(question_lines)


def build_quiz_prompt(
    level: str,
    difficulty: int,
    number_of_entries: int,
    book_id: Optional[int],
    quiz_type: Optional[str],
) -> str:
    book_selection_directive = (
        f"- Use words or examples from book ID {book_id} when possible.\n"
        if book_id
        else ""
    )

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
