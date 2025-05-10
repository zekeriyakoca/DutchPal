import os
import re
import pdfplumber
from chat_with_ai import chat_with_openai, chat_with_command_r_plus

def process_grammar_in_use_book(pdf_path: str, output_path: str):
    print(f"📘 Processing grammar book: {os.path.basename(pdf_path)}")
    
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    full_text = re.sub(r"\n{2,}", "\n", full_text).strip()

    unit_pattern = re.compile(r"(Unit\s+\d+.*?)(?=(Unit\s+\d+)|\Z)", re.DOTALL | re.IGNORECASE)
    units = unit_pattern.findall(full_text)

    print(f"🧩 Found {len(units)} units")

    with open(output_path, "w", encoding="utf-8") as out:
        for idx, (unit_text, _) in enumerate(units):
            print(f"  🧠 Formatting Unit {idx + 1}")
            cleaned = ai_format_markdown(unit_text, True)
            out.write(f"# Unit {idx + 1}\n{cleaned}\n\n")

    print(f"✅ Saved structured grammar book: {output_path}")

def convert_to_dutch_prompt() -> str:
    return """
        ⚠️ Additional rule (for grammar lessons only):
                If the content is in English and it is clearly a grammar lesson intended to teach English, then:
                Do NOT translate it
                Instead, convert it into a grammar lesson for Dutch learners, teaching Dutch grammar, keeping the same format and scope
                Replace English grammar rules and examples with equivalent Dutch grammar rules and examples
                Keep the lesson structure (explanations, examples, exercises)
                respects line breaks from the original
                keeps everything aligned with your grammar-learning format
                Units should be split in two main section. General and Exercises. If no exercises in unit, just General.
                Ignore picture based exercises and remove them() 
                Output should be in Dutch, not English(including descriptions, examples, and exercises)
                Use natural Dutch, but don’t be overly strict or robotic
                Do not keep literal translations like "I’m doing" → "Ik ben bezig". Instead, use grammar-correct structures like "Ik ben aan het doen"
            Only apply this if the source material is clearly a grammar explanation written in English for teaching English. If it’s a general English text, keep it as is.
    """

def ai_format_markdown(plain_text: str, translateToDutch: bool = False) -> str:
    prompt = f"""
    You are a formatting engine.

    Do NOT add, rewrite, or rephrase anything.

    Your job is:

        Keep only the lines that make sense (remove OCR noise, unmeaningful text, broken characters, unreadable fragments, empty lines)
        Preserve the order and wording of real sentences or content
        Format it into Markdown using # or ## or ### headers, lists, and spacing
        Formatting rules:
            Use # only for unit or section titles (e.g. “Unit 1: Present Continuous”)
            Use ## for main sections within a unit (e.g. grammar rules, explanation, exercises)
            Use ### and #### for subsections if needed (e.g. examples, compare blocks, sub-sections of main sections)
        Do NOT invent or add any new content
        Do NOT guess missing words or rewrite anything
        If it looks like garbage or non-content, remove the line
        {convert_to_dutch_prompt() if translateToDutch else ''}

        Raw OCR Text:
        \"\"\"
        {plain_text.strip()}
        \"\"\"
    """

    return chat_with_openai(prompt) if translateToDutch else chat_with_command_r_plus(prompt)