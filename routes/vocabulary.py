from fastapi import APIRouter
from tools.agent import SessionLocal
from pydantic import BaseModel
from typing import Optional
from services.app_service import (
    find_sentence_containing_word,
    get_vocabularies,
)

from tools.chat_with_ai import (
    chat_with_grok,
)

router = APIRouter()


class VocabRequest(BaseModel):
    message: str = ""
    level: str = "ALL LEVELS"
    number_of_entries: int = 1
    book_id: Optional[int] = None
    word_type: Optional[str] = None


@router.post("/vocabulary")
async def get_vocabulary(req: VocabRequest):

    db = SessionLocal()
    vocabularies = await get_vocabularies(
        db=db,
        word_to_search=req.message,
        limit=req.number_of_entries,
        cefr_level=req.level,
        pos=req.word_type,
    )

    if not vocabularies:
        return {"response": "No vocabulary found."}

    print(f"Vocabularies: {vocabularies}")
    data = [
        {
            "word": vocab["lemma"],
            "vocablary": vocab,
            "example sentences": await find_sentence_containing_word(
                db=db,
                word_forms=get_all_forms_of_word(vocab),
                limit=3,
                cefr_level=req.level,
            ),
        }
        for vocab in vocabularies
    ]

    prompt = build_vocab_prompt(data=data)

    result = chat_with_grok(prompt=prompt)
    return {"response": result}


def get_all_forms_of_word(vocab: dict) -> list[str]:
    """
    Get all forms of a word from the vocabulary dictionary.
    """
    return (
        [
            vocab["lemma"],
            *vocab["present_form"].split("/"),
            *vocab["v2_form"].split("/"),
            *vocab["v3_form"].split("/"),
        ]
        if vocab["pos"] == "verb"
        else [vocab["lemma"]]
    )


def build_vocab_prompt(data: str) -> str:
    return f"""
    Generate a **Markdown table** of Dutch vocabulary.
    data to be used : {data}

    - Include the following columns:

    - Word (e.g. wonen; base/dictionary form, 'infinitive' column if verb)
    - Level (CEFR)  
    - Translation (short English meaning)  
    - Examples (3 example sentences in the provided data. Make 'Word' or any for of it under 'Prensent', 'V2', 'V3' column bold in the sentence. Seperate each example with a <br> tag. e.g. Uit welk land komt u?<br>Uit welk land kom je?)  
    - Present present column if verb (e.g. woon/woont/wonen)
    - V2(past) v2_form column if verb (e.g. woonde/woonde/woonden)
    - V3(past perfect) v3_form if verb (e.g. gewoond)
    - Imperative (empty if not verb)

    Ensure **all columns are filled**. If any information is missing from the dataset, intelligently generate it. But first check the dataset for the information.

    Return the result **as a Markdown table only** — do not include any explanation or extra text.
    """


# def build_vocab_prompt(
#     input_text: str,
#     level: str,
#     number_of_entries: int,
#     book_id: Optional[int],
#     word_type: Optional[str],
# ) -> str:
#     book_selection_directive = (
#         f"- Target book is the book with ID {book_id}.\n" if book_id else ""
#     )

#     translation_directive = (
#         f"- Translate the word '{input_text}'."
#         if input_text.strip()
#         else f"""
#         - Total number of vocabulary entries: {number_of_entries}\n- Select words **randomly from the dataset**
#         - CEFR Level should be: {level}
#         - Type of the word should be: {word_type} (pos column in dataset)
#         """
#     )

#     return f"""
#     Generate a **Markdown table** of Dutch vocabulary.
#     {translation_directive}
#     {book_selection_directive}

#     - For conjugation columns (Present, V2, V3), list only the **conjugated forms** separated by slashes, like: `woon/woont/wonen` — do **not** include pronouns (ik/jij/wij).

#     - Include the following columns:

#     - Word (e.g. wonen; base/dictionary form)
#     - Level (CEFR)
#     - Translation (short English meaning)
#     - Examples (3 example sentences containing the word; use book(from dataset) examples if available, otherwise, return empty. Word should be bold. Seperate each example with a <br> tag. e.g. Uit welk land komt u?<br>Uit welk land kom je?)
#     - Present ik/jij/wij (e.g. woon/woont/wonen; empty if not verb)
#     - V2 ik/jij/wij (e.g. woonde/woonde/woonden; empty if not verb)
#     - V3 ik/jij/wij (e.g. gewoond/gewond/gewonen; empty if not verb)
#     - Imperative  (empty if not verb)

#     Ensure **all columns are filled**. If any information is missing from the dataset, intelligently generate it. But first check the dataset for the information.

#     Return the result **as a Markdown table only** — do not include any explanation or extra text.
#     """
