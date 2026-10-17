import asyncio
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from services.word_lookup import WordLookup, lookup_word
from tools.chat_with_ai import chat_with_openai_5_mini

import json
from utils.db import get_db
from utils.llm_json import extract_json_object
from utils.provider_errors import raise_openai_unavailable_if_provider_error

router = APIRouter()


class TranslateRequest(BaseModel):
    message: str  # the word to translate


# Kept for the text-selection buttons, which show this Markdown in a toast.
# It renders the grounded /word/lookup result instead of asking an LLM for a table.
@router.post("/translate-word")
async def translate_word(req: TranslateRequest, db: Session = Depends(get_db)):
    try:
        result = await lookup_word(db, req.message)
    except Exception as exc:
        raise_openai_unavailable_if_provider_error(exc)

    return {"response": lookup_as_markdown(result)}


def lookup_as_markdown(lookup: WordLookup) -> str:
    cells = {
        "Word": f"{lookup.article} {lookup.lemma}" if lookup.article else lookup.lemma,
        "Translation": ", ".join(lookup.translations),
        "Level": lookup.cefr_level,
        "Examples": "<br>".join(lookup.examples),
        "Present": lookup.forms.present,
        "V2": lookup.forms.v2,
        "V3": lookup.forms.v3,
    }
    cells = {name: value.replace("|", "\\|") for name, value in cells.items() if value}
    return "\n".join(
        [
            "| " + " | ".join(cells) + " |",
            "|" + " --- |" * len(cells),
            "| " + " | ".join(cells.values()) + " |",
        ]
    )


@router.post("/translate-word-as-json")
async def translate_word_as_json(req: TranslateRequest):
    prompt = build_vocab_prompt_for_json_response(req.message)

    try:
        result = await asyncio.to_thread(chat_with_openai_5_mini, prompt)
    except Exception as exc:
        raise_openai_unavailable_if_provider_error(exc)

    try:
        response_json = json.loads(extract_json_object(result))
    except Exception:
        print(f"Error parsing response: {result}")
        raise Exception(
            "Problem with parsing the response. Make sure the response is a valid JSON."
        )

    return {"response": response_json}


def build_vocab_prompt_for_json_response(word: str) -> str:
    return f"""
    You are a Dutch language assistant.

    - Generate information about the Dutch word: **{word}**.
    - Classify the word as one of the following types: **VERB**, **NOUN**, or **OTHER**.
    - Provide 1 example sentences where the word appears. If the word is a verb, bold the appropriate verb form in the sentence.

    - Return only this JSON object:

    {{
      "word": "<base form of the word>",
      "type": "VERB | NOUN | OTHER",
      "translation": "<short English meaning>",
      "examples": [
        "<Example sentence 1>",
        "<Example sentence 2>"
      ]
    }}

    Do not return any explanation or extra text — only the JSON object.
    """

