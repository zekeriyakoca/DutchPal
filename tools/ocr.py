import os
from PIL import Image
from PyPDF2 import PdfReader
import pytesseract
import pdfplumber
from pdf2image import convert_from_path
from chat_with_ai import (
    chat_with_openai,
    chat_with_command_r_plus,
    chat_with_openai_3_5,
    chat_with_openai_4o,
    chat_with_openai_4o_mini,
    chat_with_openai_41_nano,
    chat_with_openai_o1,
)
from datetime import datetime
import openai
from book_specific_tools.grammar_in_use_processor import process_grammar_in_use_book
from dotenv import load_dotenv

# Config
BOOKS_DIR = "books"
READING_BOOKS_DIR = "reading-books"
OUTPUT_DIR = "data"
LANGS = "eng+deu+nl"

env_file = ".env.production" if os.getenv("ENV") == "production" else ".env"
load_dotenv(env_file)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # for GPT-4 / DeepSeek
openai.api_key = OPENAI_API_KEY

os.makedirs(OUTPUT_DIR, exist_ok=True)


def clean_ocr_text(raw_text: str) -> str:
    lines = raw_text.splitlines()
    return "\n".join(
        [line for line in lines if len(line.strip()) > 5 and not line.strip().isupper()]
    )


def is_text_based_pdf(path: str) -> bool:
    try:
        reader = PdfReader(path)
        for page in reader.pages:
            text = page.extract_text()
            if text and any(c.isalpha() for c in text):
                return True
        return False
    except Exception:
        return False


def simple_markdown_format(text: str) -> str:
    lines = text.splitlines()
    cleaned_lines = [
        line.strip()
        for line in lines
        if len(line.strip()) > 0 and not line.strip().isupper()
    ]
    # Join lines into paragraphs, double newlines between paragraphs
    return "\n\n".join(cleaned_lines)


def process_pdf(pdf_path: str, output_path: str, bookType: str = "study_book"):
    print(f"Processing PDF: {pdf_path} at {datetime.now().strftime('%M:%S')}")
    with open(output_path, "w", encoding="utf-8") as out:
        if is_text_based_pdf(pdf_path):
            print("  ✅ Text-based PDF detected")
            with pdfplumber.open(pdf_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    raw_text = page.extract_text()
                    if raw_text and raw_text.strip():
                        print(f"  📄 Formatting page {i + 1}...")
                        md = (
                            ai_format_study_book_to_markdown(raw_text)
                            if bookType == "study_book"
                            else ai_format_readingbook_to_markdown(raw_text)
                        )
                        out.write(md + "\n\n")
        else:
            print(
                f"  🔍 Scanned PDF detected — using OCR at {datetime.now().strftime('%M:%S')}"
            )
            pages = convert_from_path(pdf_path, dpi=300)
            for i, page in enumerate(pages):
                print(
                    f"  🖼️ OCR'ing page {i + 1}/{len(pages)}... at {datetime.now().strftime('%M:%S')}"
                )
                raw_text = pytesseract.image_to_string(page, lang=LANGS)
                if raw_text.strip():
                    raw_text = clean_ocr_text(raw_text)
                    md = (
                        ai_format_study_book_to_markdown(raw_text)
                        if bookType == "study_book"
                        else ai_format_readingbook_to_markdown(raw_text)
                    )
                    out.write(md + "\n\n")


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


def ai_format_study_book_to_markdown(
    plain_text: str, translateToDutch: bool = False
) -> str:
    print(f"Formatting text... at {datetime.now().strftime('%M:%S')}")
    prompt = f"""
    You are a formatting engine.

    Do NOT add, rewrite, or rephrase anything.

    Your job is:

        Keep only the lines that make sense (remove OCR noise, unmeaningful text, broken characters, unreadable fragments, empty lines)
        Preserve the order and wording of real sentences or content
        Format it into Markdown using # or ## or ### headers, lists, and spacing but don't add any extra titles or headers.
        Formatting rules:
            Use # only for unit or section titles (e.g. “Unit 1, Les 2 ..., etc)
        Do NOT invent or add any new content
        Do NOT guess missing words or rewrite anything
        If there is English translation of Dutch text, remove them. I only want to collect Dutch text.
        If it looks like garbage or non-content, remove the line
        {convert_to_dutch_prompt() if translateToDutch else ''}

        Raw OCR Text:
        \"\"\"
        {plain_text.strip()}
        \"\"\"
    """
    response = chat_with_openai_4o_mini(prompt)
    print(f"formatting completed at {datetime.now().strftime('%M:%S')}")

    return response


def ai_format_readingbook_to_markdown(plain_text: str) -> str:
    print(f"Formatting text... at {datetime.now().strftime('%M:%S')}")
    prompt = f"""
    You are a formatting engine.

    Do NOT add, rewrite, or rephrase anything.

    Your job is:
        You'll receive a text from a book. It is a reading book.
        Keep only the lines that make sense (remove OCR noise, unmeaningful text, broken characters, unreadable fragments, empty lines)
        Preserve the order and wording of real sentences or content
        Format it into Markdown using # or ## or ### chapter or section titles, etc but don't add any extra titles or headers.
        Formatting rules:
            Use #... only for chapter titles (e.g. Episode 1, Section 2, Part 1, Monster in the Lake ..., etc) If no chapter title, use #Chapter
            Every book should have at least one chapter title.
        Do NOT invent or add any new content
        Do NOT guess missing words or rewrite anything
        If there is English translation of Dutch text, remove them. I only want to collect Dutch text.
        If it looks like garbage, page info, additional info or non-content, remove the line

        Raw OCR Text:
        \"\"\"
        {plain_text.strip()}
        \"\"\"
    """
    response = chat_with_openai_41_nano(prompt)
    print(f"formatting completed at {datetime.now().strftime('%M:%S')}")

    return response
    # return chat_with_openai(prompt) if translateToDutch else chat_with_command_r_plus(prompt)


def process_image_folder(
    folder_path: str, output_path: str, bookType: str = "study_book"
):
    with open(output_path, "w", encoding="utf-8") as out:
        for file in sorted(os.listdir(folder_path)):
            if not file.lower().endswith((".png", ".jpg", ".jpeg")):
                continue
            print(f"  🖼️ OCR'ing image: {file} at {datetime.now().strftime('%M:%S')}")
            image_path = os.path.join(folder_path, file)
            raw_text = pytesseract.image_to_string(Image.open(image_path), lang=LANGS)
            if raw_text.strip():
                raw_text = clean_ocr_text(raw_text)
                md = ai_format_study_book_to_markdown(raw_text)
                out.write(md + "\n\n")


# 🔁 Main processing loop
def process_language_books():
    for name in os.listdir(BOOKS_DIR):
        path = os.path.join(BOOKS_DIR, name)

        if os.path.isfile(path) and path.lower().endswith(".pdf"):
            output_md = os.path.join(OUTPUT_DIR, f"{os.path.splitext(name)[0]}.md")
            if "grammar_in_use" in name.lower():
                process_grammar_in_use_book(path, output_md)
            else:
                process_pdf(path, output_md)
            print(f"✅ Saved: {output_md}")
            continue

        if os.path.isdir(path):
            pdfs = sorted([f for f in os.listdir(path) if f.lower().endswith(".pdf")])
            if pdfs:
                first_pdf = os.path.join(path, pdfs[0])
                output_md = os.path.join(
                    OUTPUT_DIR, f"{os.path.splitext(pdfs[0])[0]}.md"
                )
                if "grammar_in_use" in name.lower():
                    process_pdf(first_pdf, output_md)
                else:
                    process_pdf(first_pdf, output_md)
                print(f"✅ Saved: {output_md}")
            else:
                output_md = os.path.join(OUTPUT_DIR, f"{name}.md")
                process_image_folder(path, output_md, False)
                print(f"✅ Saved: {output_md}")


def process_story_books():
    for name in os.listdir(READING_BOOKS_DIR):
        path = os.path.join(READING_BOOKS_DIR, name)

        if os.path.isfile(path) and path.lower().endswith(".pdf"):
            output_md = os.path.join(OUTPUT_DIR, f"{os.path.splitext(name)[0]}.md")
            process_pdf(path, output_md, "story_book")
            print(f"✅ Saved: {output_md}")
            continue

        if os.path.isdir(path):
            pdfs = sorted([f for f in os.listdir(path) if f.lower().endswith(".pdf")])
            if pdfs:
                first_pdf = os.path.join(path, pdfs[0])
                output_md = os.path.join(
                    OUTPUT_DIR, f"{os.path.splitext(pdfs[0])[0]}.md"
                )
                process_pdf(first_pdf, output_md, "story_book")
                print(f"✅ Saved: {output_md}")


# process_language_books()
process_story_books()
