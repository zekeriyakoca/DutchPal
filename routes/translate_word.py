from fastapi import APIRouter
from pydantic import BaseModel
from tools.chat_with_ai import (
    chat_with_grok,
)

router = APIRouter()


class TranslateRequest(BaseModel):
    message: str  # the sentence to translate


@router.post("/translate-word")
async def translate_word(req: TranslateRequest):
    prompt = build_vocab_prompt(req.message)

    result = chat_with_grok(prompt=prompt)
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
    - Imperative (empty if not verb)

    Return the result **as a Markdown table only** — do not include any explanation or extra text.
    """
