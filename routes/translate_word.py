import asyncio
from fastapi import APIRouter
from pydantic import BaseModel
from tools.chat_with_ai import (
    chat_fast,
    chat_smart,
    chat_with_openai_5_mini,
    chat_with_openai_5_nano,
)

import json
import re
from utils.provider_errors import raise_openai_unavailable_if_provider_error

router = APIRouter()


class TranslateRequest(BaseModel):
    message: str  # the sentence to translate
    response_quality: int = (
        1  # 3 for high-quality model, 2 for medium-quality model, 1 for low-quality model
    )


@router.post("/translate-word")
async def translate_word(req: TranslateRequest):
    prompt = build_vocab_prompt(req.message)

    try:
        if req.response_quality == 3:
            result = await asyncio.to_thread(chat_with_openai_5_nano, prompt)
        elif req.response_quality == 2:
            result = await asyncio.to_thread(chat_smart, prompt)
        else:
            result = await asyncio.to_thread(chat_fast, prompt)
    except Exception as exc:
        raise_openai_unavailable_if_provider_error(exc)

    return {"response": result}


def build_vocab_prompt(word: str) -> str:
    return f"""
    Generate a **Markdown table** of Dutch word : {word}.
    There will be only one row in the table.

    - **Include the following columns**:

    - Word (e.g. wonen; base/dictionary form, 'infinitive' column if verb)
    - Translation (short English meaning)  
    - Examples (2 example sentences with your own knowledge. Make 'Word' or any for of it under 'Prensent', 'V2', 'V3' column bold in the sentence. Seperate each example with a <br> tag. e.g. Uit welk land komt u?<br>Uit welk land kom je?)  
    - Present present column if verb (e.g. woon/woont/wonen)
    - V2(past) v2_form column if verb (e.g. woonde/woonde/woonden)
    - V3(past perfect) v3_form if verb (e.g. gewoond)

    Return the result **as a Markdown table only** — do not include any explanation or extra text.
    """


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


def extract_json_object(text: str) -> str:
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end >= start:
        return cleaned[start : end + 1]
    return cleaned
