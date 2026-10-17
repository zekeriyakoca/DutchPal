from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from httpx import AsyncClient
from services.app_service import get_paragraph_questions
from tools.agent import language_agent, Deps
from pydantic import BaseModel
from typing import Optional
from utils.agent_result import agent_output
from utils.db import get_db
from utils.provider_errors import raise_openai_unavailable_if_provider_error

router = APIRouter()


class QuizRequest(BaseModel):
    level: str = "ALL LEVELS"
    difficulty: int = 5
    number_of_entries: int = 5
    book_id: Optional[int] = None
    quiz_type: Optional[str] = None  # e.g., "grammar", "vocab", etc.


class QuizQuestion(BaseModel):
    type: str
    question: str
    options: list[str]
    answer: str
    explanation: Optional[str] = None


class Quiz(BaseModel):
    questions: list[QuizQuestion]


@router.post("/quiz")
async def generate_quiz(req: QuizRequest, db: Session = Depends(get_db)):
    if req.quiz_type == "PARAGRAPH":
        # Stored open questions with free-text answers (no options), so they stay markdown.
        questionGroups = get_paragraph_questions(
            db,
            limit=req.number_of_entries,
            cefr_level=req.level,
        )
        return {"response": convert_question_groups_to_markdown(questionGroups)}

    async with AsyncClient(timeout=60) as client:
        deps = Deps(client=client, db=db)
        try:
            questions = await generate_questions(req, deps)
        except Exception as exc:
            raise_openai_unavailable_if_provider_error(exc)
        return {"questions": [q.model_dump() for q in questions]}


async def generate_questions(req: QuizRequest, deps: Deps) -> list[QuizQuestion]:
    """Asks the agent for questions; retries once for the ones validation dropped."""
    questions: list[QuizQuestion] = []
    for _ in range(2):
        missing = req.number_of_entries - len(questions)
        if missing <= 0:
            break
        prompt = build_quiz_prompt(
            level=req.level,
            difficulty=req.difficulty,
            number_of_entries=missing,
            book_id=req.book_id,
            quiz_type=req.quiz_type,
        )
        result = await language_agent.run(prompt, deps=deps, output_type=Quiz)
        questions += valid_questions(agent_output(result).questions)
    return questions[: req.number_of_entries]


def valid_questions(questions: list[QuizQuestion]) -> list[QuizQuestion]:
    """
    Keeps only questions the UI can grade: non-empty question, at least two
    non-empty unique options, and an answer that is exactly one of the options.
    Values are returned stripped.
    """
    valid = []
    for q in questions:
        question = q.question.strip()
        options = [o.strip() for o in q.options]
        answer = q.answer.strip()
        if (
            question
            and len(options) >= 2
            and all(options)
            and len({o.casefold() for o in options}) == len(options)
            and answer in options
        ):
            valid.append(
                q.model_copy(
                    update={"question": question, "options": options, "answer": answer}
                )
            )
    return valid


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
    Every question is multiple choice:
    - `type`: one of fill_in_the_blank, sentence_completion, translation, vocabulary, grammar, reading
    - `question`: the question text; mark a blank as ___
    - `options`: 3 or 4 different options
    - `answer`: the correct option, copied exactly from `options`; exactly one option is correct
    - `explanation`: one short sentence on why the answer is correct

    The quiz should be varied and engaging. Mix the question types.
    If there are more than 10 questions, include reading questions: a short paragraph (length based on the CEFR level and difficulty) followed by the question, both in `question`.

    All questions should match the selected CEFR level and difficulty.
    Use plain text in every field, no Markdown.
    """
