import os
from PIL import Image
from PyPDF2 import PdfReader
import pytesseract
import pdfplumber
from pdf2image import convert_from_path
import openai

# Config
BOOKS_DIR = "books"
OUTPUT_DIR = "data"
LANGS = "eng+deu+nl"

openai.api_key = os.getenv("OPENAI_API_KEY")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def clean_ocr_text(raw_text: str) -> str:
    lines = raw_text.splitlines()
    return "\n".join([
        line for line in lines
        if len(line.strip()) > 5 and not line.strip().isupper()
    ])

# 🧠 Use OpenAI to convert raw OCR to structured markdown
def ai_format_markdown(plain_text: str) -> str:
    prompt = f"""
You are a formatting engine.

Do NOT add, rewrite, or rephrase anything.

Your job is:
- Keep **only the lines that make sense** (remove OCR noise, unmeaningfull text, broken characters, unreadable fragments, empty lines)
- Preserve the order and wording of real sentences or content
- Format it into **Markdown** using ## or ### headers, lists, and spacing
- Do NOT invent or add any new content
- Do NOT guess missing words or rewrite anything
- If it looks like garbage or non-content, remove the line

Raw OCR Text:
\"\"\"
{plain_text.strip()}
\"\"\"
"""

    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
    )
    return response.choices[0].message.content.strip()

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
    
# 📘 Loop over files in books folder
for book_name in os.listdir(BOOKS_DIR):
    book_path = os.path.join(BOOKS_DIR, book_name)

    # Handle PDF files
    if book_name.lower().endswith(".pdf"):
        output_path = os.path.join(OUTPUT_DIR, f"{os.path.splitext(book_name)[0]}.md")
        print(f"📘 Processing PDF: {book_name}")

        with open(output_path, "w", encoding="utf-8") as out:
            if is_text_based_pdf(book_path):
                print("  ✅ Detected text-based PDF. Using text extraction...")
                with pdfplumber.open(book_path) as pdf:
                    for i, page in enumerate(pdf.pages):
                        raw_text = page.extract_text()
                        if raw_text and raw_text.strip():
                            print(f"  📄 Formatting page {i + 1}...")
                            md_text = ai_format_markdown(raw_text)
                            out.write(md_text + "\n\n")
            else:
                print("  🔍 Detected scanned PDF. Using OCR...")
                pages = convert_from_path(book_path, dpi=300)
                for i, page in enumerate(pages):
                    print(f"  🖼️ OCR'ing scanned page {i + 1}/{len(pages)}...")
                    raw_text = pytesseract.image_to_string(page, lang=LANGS)
                    if raw_text.strip():
                        raw_text = clean_ocr_text(raw_text)
                        md_text = ai_format_markdown(raw_text)
                        out.write(md_text + "\n\n")

        print(f"✅ Saved: {output_path}")
        continue

    # Handle image folders (existing logic)
    if not os.path.isdir(book_path):
        continue

    output_path = os.path.join(OUTPUT_DIR, f"{book_name}.md")
    print(f"📘 Processing image folder: {book_name}")

    with open(output_path, "w", encoding="utf-8") as out:
        for image_file in sorted(os.listdir(book_path)):
            if not image_file.lower().endswith((".png", ".jpg", ".jpeg")):
                continue

            image_path = os.path.join(book_path, image_file)
            print(f"  🖼️ OCR'ing image: {image_file}")
            raw_text = pytesseract.image_to_string(Image.open(image_path), lang=LANGS)

            if raw_text.strip():
                raw_text = clean_ocr_text(raw_text)
                md_text = ai_format_markdown(raw_text)
                out.write(md_text + "\n\n")

    print(f"✅ Saved formatted markdown: {output_path}")
