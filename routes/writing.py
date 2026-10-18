"""Feedback on an answer to an exam writing task (Schrijven), scored on the task's own criteria.

One LLM call per evaluation. Nothing is stored yet.
"""

import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from tools.chat_with_ai import chat_with_openai
from tools.content.models import Chapter, Exercise
from utils.db import get_db
from utils.llm_json import LlmJsonError, ask_llm_json
from utils.provider_errors import raise_openai_unavailable_if_provider_error

router = APIRouter()

GRAMMAR_BOOK = "dutch-grammar-in-use"
MAX_GRAMMAR_UNITS = 3
# "Grammaticale correctheid (0–2 punten)": B1 and the B2 sentence tasks.
POINTS = re.compile(r"^(.+?) \(0[–-](\d+) punt")
# "Spelling\n0: …\n1: …\n2: …": the B2 longer tasks.
SCALE = re.compile(r"^(\d+):", re.MULTILINE)
# Generated criteria (Inburgering A2) print no points.
GENERATED_MAX = 2


class WritingRequest(BaseModel):
    exercise_id: int
    answer: str


class CriterionScore(BaseModel):
    name: str
    score: int
    max: int
    comment: str


class Correction(BaseModel):
    original: str
    corrected: str
    explanation: str


class GrammarUnit(BaseModel):
    chapter_id: int
    title: str = ""
    why: str


class WritingEvaluation(BaseModel):
    criteria: list[CriterionScore]
    corrections: list[Correction]
    grammar_units: list[GrammarUnit]
    improved_text: str


def chat_writing(prompt: str) -> str:
    return chat_with_openai(prompt, model="gpt-5-mini", reasoning_effort="medium")


@router.post("/writing/evaluate", tags=["Writing"])
async def evaluate_writing(req: WritingRequest, db: Session = Depends(get_db)):
    """
    Scores the answer per criterion and returns corrections, grammar units to study and an improved text.
    """
    exercise = db.get(Exercise, req.exercise_id)
    if exercise is None or exercise.type != "writing":
        raise HTTPException(status_code=404, detail=f"Writing exercise {req.exercise_id} not found")
    if not req.answer.strip():
        raise HTTPException(status_code=400, detail="Write an answer first.")

    aspects = rubric(exercise.payload.get("criteria", []))
    if not aspects:
        raise HTTPException(status_code=400, detail="This exercise has no criteria to score against.")
    units = dict(
        db.query(Chapter.id, Chapter.title).filter(Chapter.book_id == GRAMMAR_BOOK).order_by(Chapter.number).all()
    )
    prompt = build_writing_prompt(exercise, aspects, units, req.answer.strip())
    try:
        evaluation = await ask_llm_json(chat_writing, prompt, WritingEvaluation)
    except Exception as exc:
        raise_openai_unavailable_if_provider_error(exc)

    criteria = scored(evaluation.criteria, aspects)
    return {
        "criteria": [c.model_dump() for c in criteria],
        "total": sum(c.score for c in criteria),
        "max_total": sum(c.max for c in criteria),
        "corrections": [
            c.model_dump()
            for c in evaluation.corrections
            if c.original.strip() and c.original.strip() != c.corrected.strip()
        ],
        "grammar_units": [
            u.model_copy(update={"title": units[u.chapter_id]}).model_dump()
            for u in evaluation.grammar_units
            if u.chapter_id in units
        ][:MAX_GRAMMAR_UNITS],
        "improved_text": evaluation.improved_text.strip(),
    }


def rubric(criteria: list[str]) -> list[tuple[str, int]]:
    """The aspects an answer is scored on, with their maximum points, read from the printed criteria."""
    aspects = []
    for criterion in criteria:
        if points := POINTS.match(criterion):
            aspects.append((points[1], int(points[2])))
        elif scale := SCALE.findall(criterion):
            aspects.append((criterion.splitlines()[0].strip(), max(map(int, scale))))
    if aspects:
        return aspects
    return [(re.split(r"[:\n]", c)[0].replace("(generated)", "").strip(), GENERATED_MAX) for c in criteria]


def scored(criteria: list[CriterionScore], aspects: list[tuple[str, int]]) -> list[CriterionScore]:
    """The LLM's scores in the rubric's order, with the rubric's names and maxima; scores clamped to them."""
    if len(criteria) != len(aspects):
        print(f"Writing evaluation scored {len(criteria)} criteria, expected {len(aspects)}")
        raise LlmJsonError()
    return [
        c.model_copy(update={"name": name, "max": top, "score": min(max(c.score, 0), top)})
        for c, (name, top) in zip(criteria, aspects)
    ]


def build_writing_prompt(exercise: Exercise, aspects: list[tuple[str, int]], units: dict[int, str], answer: str) -> str:
    chapter = exercise.chapter
    payload = exercise.payload
    task = {
        "situation": payload.get("situation"),
        "prompt": payload.get("prompt"),
        "form_questions": payload.get("items"),
        "criteria": payload.get("criteria"),
        "model_answer": payload.get("model_answer"),
    }
    aspect_lines = "\n".join(f"{i}. {name} (0–{top})" for i, (name, top) in enumerate(aspects, 1))
    unit_lines = "\n".join(f"{chapter_id}: {title}" for chapter_id, title in units.items())

    return f"""
    You are an examiner for the Dutch writing exam "{chapter.book_title}" ({chapter.book_cefr}), task "{exercise.label}".
    Score the candidate's answer strictly by the official criteria, at level {chapter.book_cefr}.

    The task (JSON). In `prompt`, ___ marks the part the candidate writes; the rest is printed.
    {json.dumps(task, ensure_ascii=False)}

    The task may show pictures you cannot see; do not take points off for details only the pictures would show.

    The candidate's answer:
    \"\"\"
    {answer}
    \"\"\"

    Reply with one JSON object:
    - `criteria`: exactly these aspects, in this order, each `{{"name", "score", "max", "comment"}}`;
      `score` is a whole number from 0 to the maximum, `comment` one or two short sentences in English
      on why that score:
    {aspect_lines}
    - `corrections`: every language error in the answer, `{{"original", "corrected", "explanation"}}`;
      `original` is the wrong words copied exactly from the answer, `corrected` the right Dutch,
      `explanation` one short sentence in English. An empty list when there are no errors.
    - `grammar_units`: 0 to {MAX_GRAMMAR_UNITS} units from the grammar book below that would help most with
      these errors, `{{"chapter_id", "why"}}`; `chapter_id` is the number before the title,
      `why` one short sentence in English.
    - `improved_text`: the candidate's own answer, corrected and improved to a good {chapter.book_cefr} answer;
      keep their content and only write the part the candidate writes. Dutch, plain text.

    Grammar book units (chapter_id: title):
    {unit_lines}
    """
