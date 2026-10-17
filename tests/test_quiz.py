import asyncio
import os

# The app reads these at import time; dummy values so no real DB or API key is needed.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("LOGFIRE_SEND_TO_LOGFIRE", "false")

from types import SimpleNamespace

from routes import quiz
from routes.quiz import Quiz, QuizQuestion, QuizRequest, valid_questions


def question(text="Ik ___ in Delft.", options=("woon", "woont", "wonen"), answer="woon"):
    return QuizQuestion(type="fill_in_the_blank", question=text, options=list(options), answer=answer)


def test_keeps_valid_question_and_strips_values():
    [q] = valid_questions([question(text=" Ik ___ hier. ", options=(" woon", "woont "), answer="woon ")])
    assert (q.question, q.options, q.answer) == ("Ik ___ hier.", ["woon", "woont"], "woon")


def test_drops_invalid_questions():
    invalid = [
        question(text="  "),
        question(answer="wonen!"),  # answer not an option
        question(options=("woon", "Woon", "wonen")),  # duplicate options
        question(options=("woon", "", "wonen")),  # empty option
        question(options=("woon",)),  # nothing to choose from
    ]
    assert valid_questions(invalid) == []


def test_retries_once_for_missing_questions(monkeypatch):
    runs = [
        Quiz(questions=[question(), question(answer="nope")]),
        Quiz(questions=[question(text="Hij ___ in Delft.", answer="woont")]),
    ]
    prompts = []

    async def fake_run(prompt, deps=None, output_type=None):
        prompts.append(prompt)
        return SimpleNamespace(output=runs[len(prompts) - 1])

    monkeypatch.setattr(quiz.language_agent, "run", fake_run)

    result = asyncio.run(quiz.generate_questions(QuizRequest(number_of_entries=2), deps=None))

    assert [q.answer for q in result] == ["woon", "woont"]
    assert len(prompts) == 2
    assert "Number of questions: 1" in prompts[1]


def test_stops_after_one_retry(monkeypatch):
    calls = []

    async def fake_run(prompt, deps=None, output_type=None):
        calls.append(prompt)
        return SimpleNamespace(output=Quiz(questions=[question(answer="nope")]))

    monkeypatch.setattr(quiz.language_agent, "run", fake_run)

    assert asyncio.run(quiz.generate_questions(QuizRequest(number_of_entries=3), deps=None)) == []
    assert len(calls) == 2
