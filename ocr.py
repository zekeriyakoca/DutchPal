import os
from PIL import Image
import pytesseract
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


# 📘 Loop over books
for book_name in os.listdir(BOOKS_DIR):
    book_path = os.path.join(BOOKS_DIR, book_name)
    if not os.path.isdir(book_path):
        continue

    output_path = os.path.join(OUTPUT_DIR, f"{book_name}.md")
    print(f"📘 Processing book: {book_name}")

    with open(output_path, "w", encoding="utf-8") as out:
        for image_file in sorted(os.listdir(book_path)):
            if not image_file.lower().endswith((".png", ".jpg", ".jpeg")):
                continue

            image_path = os.path.join(book_path, image_file)
            print(f"  🖼️ OCR'ing page: {image_file}")
            raw_text = pytesseract.image_to_string(Image.open(image_path), lang=LANGS)

            if raw_text.strip():
                print(f"    ✨ Sending to OpenAI for markdown formatting...")
                raw_text = clean_ocr_text(raw_text)
                md_text = ai_format_markdown(raw_text)
                out.write(md_text + "\n\n")

    print(f"✅ Saved formatted markdown: {output_path}")
