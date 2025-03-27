# main.py
import os
from fastapi import FastAPI, Request
from pydantic import BaseModel
from agent import language_agent, SessionLocal, Deps
from httpx import AsyncClient

app = FastAPI()

class QueryRequest(BaseModel):
    message: str
    page: str
    level: str = 'All Levels'

@app.post("/ask")
async def ask_language_agent(req: QueryRequest):
    async with AsyncClient() as client:
        db = SessionLocal()
        deps = Deps(client=client, db=db)
        result = await language_agent.run(req.message, deps=deps)
        prompt = build_prompt(req.page, req.message, req.level)
        result = await language_agent.run(prompt, deps=deps)
        return {"response": result.data}
    
def build_prompt(page: str, input_text: str, level: str = 'All Levels') -> str:
    if page == "vocab":
        return (
           f"""
            Generate a **Markdown table** of Dutch vocabulary.

            - Total number of vocabulary entries: {input_text}
            - Select words **randomly from the dataset**
            - Include the following columns:

            - Word  
            - Level (CEFR)  
            - Translation (short English meaning)  
            - Examples (3 example sentences; use book examples if available, or create them)  
            - Present ik/jij/wij   (empty if not verb)
            - V2 ik/jij/wij  (empty if not verb)
            - V3 ik/jij/wij  (empty if not verb)
            - Imperative  (empty if not verb)
            - Synonym  
            - Antonym  

            Ensure **all columns are filled**. If any information is missing from the dataset, intelligently generate it.

            Return the result **as a Markdown table only** — do not include any explanation or extra text.
            """

        )
    elif page == "sentences":
        return (
            f"""
            Return {input_text} random Dutch sentences from the dataset.

            For each sentence, include:
            - The original Dutch sentence  
            - Its English translation  

            Format the result as a **Markdown list**, with each item showing both the Dutch and English translation clearly.

            Use only sentences from the dataset. If there aren't enough, generate similar ones intelligently.  
            Return **only the Markdown table** with two column, Dutch and Translation, with no explanation or extra text.
            """
        )
    elif page == "quiz":
        return (
            f"Generate a CEFR-level ('{level}') Dutch vocabulary quiz. Difficulty level on a scale of 0-10 is: '{input_text}'.\n"
            "Return in markdown to be shown in a website."
        )
    elif page == "chat":
        return input_text  # raw message from user
    elif page == "grammar":
        return f"Explain the Dutch grammar in this sentence: {input_text}"
    ...

