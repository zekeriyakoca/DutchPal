from fastapi import APIRouter
from services.app_service import find_or_get_sentences
from tools.agent import SessionLocal
from pydantic import BaseModel
from typing import Optional
from tabulate import tabulate


router = APIRouter()


class SentenceRequest(BaseModel):
    level: str = "ALL LEVELS"
    number_of_entries: int = 1
    book_id: Optional[int] = None


@router.post("/sentences")
async def get_sentences(req: SentenceRequest):

    result = await find_or_get_sentences(
        db=SessionLocal(),
        limit=req.number_of_entries,
        cefr_level=req.level,
        book_id=req.book_id,
    )

    if not result:
        return {"response": "No sentences found."}

    table_data = [[item["sentence"], item["translation"]] for item in result]
    headers = ["Dutch Sentence", "English Translation"]

    md_table = tabulate(table_data, headers=headers, tablefmt="github")

    return {"response": md_table}


# def build_sentences_prompt(
#     level: str, number_of_entries: int, book_id: Optional[int]
# ) -> str:
#     book_selection_directive = (
#         f"- Target book is the book with ID {book_id}.\n" if book_id else ""
#     )

#     return f"""
#     Return {number_of_entries} random Dutch sentences from the dataset.

#     - Sentences should be at CEFR Level should be: {level}
#     {book_selection_directive}

#     For each sentence, include:
#     - The original Dutch sentence
#     - Its English translation

#     Format the result as a **Markdown list**, with each item showing both the Dutch and English translation clearly.

#     Use only sentences from the dataset. If there aren't enough for the given level, generate similar ones intelligently.
#     Return **only the Markdown table** with two column, Dutch and Translation, with no explanation or extra text.
#     """
