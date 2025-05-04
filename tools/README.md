# 🛠️ DutchPal Tools

This folder contains various tools and utilities used in the **DutchPal** project to process, analyze, and enhance Dutch language learning materials. These tools handle tasks such as OCR, embedding generation, grammar processing, and interaction with AI models.

---

## 📂 Tools Overview

### 1. **`embed.py`**
   - **Purpose**: Handles embedding generation, sentence extraction, vocabulary processing, and CEFR level estimation.
   - **Key Features**:
     - Extracts sentences and vocabulary from text.
     - Generates embeddings using OpenAI's `text-embedding-ada-002`.
     - Updates CEFR levels for vocabulary and sentences in batches.
   - **Usage**:
     - Processes `.md` files in the `data` folder.
     - Updates vocabulary and sentence CEFR levels in the database.

### 2. **`ocr.py`**
   - **Purpose**: Processes PDFs and images to extract text using OCR and formats it into Markdown.
   - **Key Features**:
     - Detects text-based or scanned PDFs.
     - Uses Tesseract OCR for scanned PDFs.
     - Formats extracted text into Markdown.
   - **Usage**:
     - Processes files in the `books` and `reading-books` directories.
     - Outputs formatted Markdown files to the `data` folder.

### 3. **`chat_with_ai.py`**
   - **Purpose**: Provides utility functions to interact with OpenAI and Cohere APIs.
   - **Key Features**:
     - Supports multiple OpenAI models (e.g., GPT-4, GPT-3.5).
     - Includes functions for specific tasks like formatting, embedding, and translation.
   - **Usage**:
     - Used as a backend utility for AI-based tasks in other tools.

### 4. **`agent.py`**
   - **Purpose**: Implements a Dutch language learning assistant using OpenAI's GPT models.
   - **Key Features**:
     - Provides tools for finding lessons, sentences, and vocabulary.
     - Supports random sentence generation and CEFR-level filtering.
     - Includes a grammar explanation tool.
   - **Usage**:
     - Integrated with FastAPI routes for user interaction.

### 5. **`book_specific_tools/grammar_in_use_processor.py`**
   - **Purpose**: Processes grammar books (e.g., "Grammar in Use") and converts them into structured Markdown.
   - **Key Features**:
     - Extracts and formats grammar lessons into Markdown.
     - Converts English grammar lessons into Dutch grammar lessons for learners.
   - **Usage**:
     - Processes grammar books in the `books` directory.

### 6. **`to_markdown.py`**
   - **Purpose**: Converts various content (e.g., PDFs, YouTube videos) into Markdown using AI. This is a playground to test some libraries and frequently changes

---

## 📦 Dependencies

The tools rely on the following libraries and APIs:
- **OpenAI API**: For embedding generation, text formatting, and language processing.
- **Tesseract OCR**: For text extraction from scanned PDFs and images.
- **SQLAlchemy**: For database interactions.
- **pgvector**: For vector similarity search in PostgreSQL.
- **pdfplumber**: For extracting text from text-based PDFs.
- **PyPDF2**: For basic PDF handling.
- **spaCy**: For natural language processing.
- **dotenv**: For managing environment variables.

---

## 🚀 How to Use

1. **Set Up Environment**:
   - Activate the virtual environment:
     ```bash
     source .venv/bin/activate
     ```
   - Install dependencies:
     ```bash
     pip install -r requirements.txt
     ```

2. **Run Specific Tools**:
   - **Embedding Processing**:
     ```bash
     python tools/embed.py
     ```
   - **OCR Processing**:
     ```bash
     python tools/ocr.py
     ```
   - **Grammar Book Processing**:
     ```bash
     python tools/book_specific_tools/grammar_in_use_processor.py
     ```

3. **Environment Variables**:
   Ensure the following variables are set in the [.env](http://_vscodecontentref_/2) file:
   - [OPENAI_API_KEY](http://_vscodecontentref_/3): API key for OpenAI.
   - [DATABASE_URL](http://_vscodecontentref_/4): Connection string for the PostgreSQL database.
   - `LOGFIRE_TOKEN`: Token for logging (if used).

---

## 📖 Example Workflow

1. Place your PDF or text files in the [books](http://_vscodecontentref_/5) or [reading-books](http://_vscodecontentref_/6) directory.
2. Run the appropriate tool (e.g., [ocr.py](http://_vscodecontentref_/7) for PDFs).
3. Process the extracted content using [embed.py](http://_vscodecontentref_/8) to generate embeddings and update the database.
4. Use the FastAPI backend to interact with the processed data via routes (e.g., `/vocabulary`, `/sentences`).

---

## 🛠️ Future Improvements

- Optimize batch sizes for CEFR level updates to reduce API costs.
- Add support for additional languages and grammar formats.
- Improve error handling for OCR and embedding generation.

---

## 📧 Support

For any issues or questions, feel free to reach out to the project maintainers.