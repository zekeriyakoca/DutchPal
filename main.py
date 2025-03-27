# main.py
import os
from fastapi import FastAPI, Request
from pydantic import BaseModel
from agent import language_agent, SessionLocal, Deps
from httpx import AsyncClient
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:4200"],  # Angular dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"])

class QueryRequest(BaseModel):
    message: str
    page: str
    level: str = 'All Levels'
    number_of_entries: int = 1

@app.post("/ask")
async def ask_language_agent(req: QueryRequest):
    async with AsyncClient() as client:
        db = SessionLocal()
        deps = Deps(client=client, db=db)
        result = await language_agent.run(req.message, deps=deps)
        prompt = build_prompt(req.page, req.message, req.level, req.number_of_entries)
        result = await language_agent.run(prompt, deps=deps)
        return {"response": result.data}
    
def build_prompt(page: str, input_text: str, level: str = 'All Levels', number_of_entries: int = 1) -> str:
    if page == "vocab":
        return (
           f"""
            Generate a **Markdown table** of Dutch vocabulary.
            {get_translation_directive(input_text,number_of_entries)}
            - For conjugation columns (Present, V2, V3), list only the **conjugated forms** separated by slashes, like: `woon/woont/wonen` — do **not** include pronouns (ik/jij/wij).

            - Include the following columns:

            - Word (e.g. wonen; base/dictionary form)
            - Level (CEFR)  
            - Translation (short English meaning)  
            - Examples (3 example sentences; use book examples if available, or create them. Seperate each example with a <br> tag. e.g. Uit welk land komt u?<br>Uit welk land kom je?)  
            - Present ik/jij/wij (e.g. woon/woont/wonen; empty if not verb)
            - V2 ik/jij/wij (e.g. woonde/woonde/woonden; empty if not verb)
            - V3 ik/jij/wij (e.g. gewoond/gewond/gewonen; empty if not verb)
            - Imperative  (empty if not verb)
            

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
    elif page == "translate-sentence":
        return f"Translate the sentence '{input_text}' into English. Highlight the important words in the sentence. No extra text or explanation needed. If the sentence is not in good shape, intelligently correct it."
        return input_text  # raw message from user
    elif page == "chat":
        return input_text  # raw message from user
    elif page == "grammar":
        return f"Explain the Dutch grammar in this sentence: {input_text}"
    ...

def get_translation_directive(input_text: str, number_of_entries: int) -> str:
    if input_text.strip() != '':
        return f"- Translate the word '{input_text}'.\n"
    else: 
        return f"""
            - Total number of vocabulary entries: {input_text}
            - Select words **randomly from the dataset**
            """
