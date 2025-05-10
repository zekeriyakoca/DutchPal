from markitdown import MarkItDown
from openai import OpenAI
import os

from dotenv import load_dotenv

env_file = ".env.production" if os.getenv("ENV") == "production" else ".env"
load_dotenv(env_file)

# Playground for MarkItDown

client = OpenAI()
md = MarkItDown(llm_client=client, llm_model="gpt-4o", enable_plugins=True)

# md = MarkItDown(enable_plugins=True)  # Set to True if you want OCR, audio, etc.
# result = md.convert("books/partial-grammar-in-use.pdf")
result = md.convert("https://www.youtube.com/watch?v=GzMx4S7KbZw")

# print(result.text_content)

with open("book1.md", "w", encoding="utf-8") as f:
    f.write(result.text_content)
