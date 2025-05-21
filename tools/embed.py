from sqlalchemy.dialects.postgresql import ARRAY
import os
import re
import spacy
import string
import openai
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.dialects.postgresql import TSVECTOR
from pgvector.sqlalchemy import Vector
from typing import List

import json
from tqdm import tqdm
from dotenv import load_dotenv

env_file = ".env.production" if os.getenv("ENV") == "production" else ".env"
load_dotenv(env_file)

Base = declarative_base()


class Book(Base):
    __tablename__ = "books"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    language = Column(String, nullable=False)
    cefr_level = Column(String)
    sections = relationship("Section", back_populates="book")
    sentences = relationship("Sentence", back_populates="book")


class Section(Base):
    __tablename__ = "sections"
    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1536), nullable=False)
    book = relationship("Book", back_populates="sections")
    sentences = relationship("Sentence", back_populates="section")


class Sentence(Base):
    __tablename__ = "sentences"
    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=False)
    text = Column(Text, nullable=False)
    translation = Column(String, nullable=True)
    cefr_level = Column(String, nullable=True)
    embedding = Column(Vector(1536), nullable=True)
    text_search_vector = Column(TSVECTOR)
    book = relationship("Book", back_populates="sentences")
    section = relationship("Section", back_populates="sentences")


class Vocabulary(Base):
    __tablename__ = "vocabulary"
    id = Column(Integer, primary_key=True)
    lemma = Column(String, nullable=False)
    pos = Column(String, nullable=False)
    cefr_level = Column(String, nullable=True)
    encounter_count = Column(Integer, default=1)
    embedding = Column(Vector(1536), nullable=False)
    infinitive = Column(String, nullable=True)
    present_form = Column(String, nullable=True)
    v2_form = Column(String, nullable=True)
    v3_form = Column(String, nullable=True)
    frequency = Column(Integer, nullable=True)
    __table_args__ = (UniqueConstraint("lemma", "pos", name="_lemma_pos_uc"),)


class QuestionGroup(Base):
    __tablename__ = "question_groups"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=True)  # Optional title for grouped questions
    question_type = Column(
        String, nullable=False
    )  # e.g., 'paragraph', 'vocabulary', 'grammar'
    text = Column(Text, nullable=True)  # Paragraph or instruction text
    explanation = Column(Text, nullable=True)
    cefr_level = Column(String, nullable=True)
    question_count = Column(Integer, nullable=True)

    # Relationships
    questions = relationship(
        "QuestionItem", back_populates="group", cascade="all, delete-orphan"
    )


class QuestionItem(Base):
    __tablename__ = "question_items"
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("question_groups.id"), nullable=False)
    question_text = Column(Text, nullable=False)
    gap_index = Column(
        Integer, nullable=True
    )  # Useful for vocab-type fill-in-the-blanks
    choices = Column(
        ARRAY(String), nullable=True
    )  # Multiple-choice options if applicable
    answer = Column(String, nullable=False)
    explanation = Column(Text, nullable=True)
    order_index = Column(Integer, nullable=True)

    # Relationships
    group = relationship("QuestionGroup", back_populates="questions")


class LanguageProcessor:
    def __init__(self, language_model="nl_core_news_sm"):
        self.nlp = spacy.load(language_model)
        openai.api_key = os.getenv("OPENAI_API_KEY")

    def generate_embedding(self, text: str) -> List[float]:
        response = openai.embeddings.create(model="text-embedding-ada-002", input=text)
        return response.data[0].embedding

    def is_valid_sentence(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return False
        if stripped.isnumeric():
            return False
        if len(stripped.split()) <= 1:
            return False
        return True

    def extract_sentences(self, text: str) -> List[str]:
        sentences = []

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            doc = self.nlp(line)
            for sent in doc.sents:
                stripped = sent.text.strip()
                if stripped and self.is_valid_sentence(stripped):
                    sentences.append(stripped)

        return sentences

    def extract_vocab(self, text: str):
        doc = self.nlp(text)
        for token in doc:
            if token.is_alpha and not token.is_stop:
                yield token.lemma_, token.pos_

    def estimate_cefr(self, word: str) -> str:
        return None

    def extract_tokens(self, text: str):
        return self.nlp(text)  # Placeholder — replace with real level logic


def upsert_vocab(processor: LanguageProcessor, session, text: str):
    SKIP_POS = {
        "PROPN",
        "DET",
        "PRON",
        "CCONJ",
        "SCONJ",
        "PART",
        "INTJ",
        "PUNCT",
        "SYM",
        "NUM",
        "X",
    }

    for lemma, pos in processor.extract_vocab(text):
        if pos in SKIP_POS:
            continue

        existing = session.query(Vocabulary).filter_by(lemma=lemma, pos=pos).first()
        if existing:
            existing.encounter_count += 1
        else:
            embedding = processor.generate_embedding(lemma)
            vocab = Vocabulary(
                lemma=lemma,
                pos=pos,
                cefr_level=processor.estimate_cefr(lemma),
                encounter_count=1,
                embedding=embedding,
            )
            session.add(vocab)


def process_book(
    processor: LanguageProcessor,
    session,
    file_path: str,
    book_title: str,
    language: str,
):

    print(f"📖 Processing book: {book_title}")
    if session.query(Book).filter_by(title=book_title).first():
        print(f"⚠️ Book '{book_title}' already exists in the database.")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    sections = re.findall(r"# {1,2}(.*?)\n(.*?)(?=\n# {1,2}|\Z)", content, re.DOTALL)
    print(f"🔍 Found {len(sections)} sections in {book_title}.")

    book = Book(title=book_title, language=language, cefr_level="A1")
    session.add(book)
    session.flush()
    print("Book record added to db.")

    for section_title, section_content in sections:
        print(f"🔍 Processing section: {section_title}")
        section_embedding = processor.generate_embedding(section_content)
        section = Section(
            book_id=book.id,
            title=section_title,
            content=section_content,
            embedding=section_embedding,
        )
        session.add(section)
        session.flush()

        for sentence_text in processor.extract_sentences(section_content):
            if not is_sentence_valuable(sentence_text, processor):
                continue

            sentence_embedding = processor.generate_embedding(sentence_text)
            sentence = Sentence(
                book_id=book.id,
                section_id=section.id,
                text=sentence_text,
                embedding=sentence_embedding,
            )
            session.add(sentence)
            upsert_vocab(processor, session, sentence_text)

    session.commit()
    print(f"✅ {book_title}")


def update_vocabulary_forms_batched(session, batch_size=100):
    vocab_entries = (
        session.query(Vocabulary)
        .filter((Vocabulary.pos == "VERB") & (Vocabulary.present_form.is_(None)))
        .all()
    )
    print(f"🔍 Found {len(vocab_entries)} vocabulary entries to update.")

    for i in tqdm(range(0, len(vocab_entries), batch_size)):
        batch = vocab_entries[i : i + batch_size]

        prompt_lines = [
            "You are a Dutch language teacher.",
            f"Provide the Present, V2 (Past), and V3 (Past Participle) forms for the following {len(batch)} Dutch words along with their part of speech.",
            'Respond in JSON format like: {"lopen": {"infinitive": "lopen", "present": "loop/loopt/lopen", "V2": "liep/liepen", "V3": "gelopen"}, ...}',
            "do not use blocks like ```json",
        ]
        for entry in batch:
            prompt_lines.append(f"{entry.lemma} ({entry.pos})")

        prompt = "\n".join(prompt_lines)

        try:
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a Dutch language teacher."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=6500,  # Adjust if needed
            )
            content = response.choices[0].message.content.strip()
            print(f"🔁 Raw response:\n{content}\n")
            # Parse JSON response
            conjugations = json.loads(content)

            for entry in batch:
                forms = conjugations.get(entry.lemma)
                if forms:
                    entry.infinitive = forms.get("infinitive", "")
                    entry.present_form = forms.get("present", "")
                    entry.v2_form = forms.get("V2", "")
                    entry.v3_form = forms.get("V3", "")
                else:
                    print(f"⚠️ No forms found for {entry.lemma}")

            session.commit()

        except Exception as e:
            print(f"❌ Error in batch starting at index {i}: {e}")

    print("🎉 All vocabulary forms updated.")


def update_vocabulary_cefr_levels_batched(session, batch_size=50):
    vocab_entries = (
        session.query(Vocabulary).filter(Vocabulary.cefr_level == None).all()
    )
    print(f"🔍 Found {len(vocab_entries)} vocabulary entries to update.")

    for i in tqdm(range(0, len(vocab_entries), batch_size)):
        batch = vocab_entries[i : i + batch_size]

        prompt_lines = [
            "You are a Dutch language teacher.",
            "Determine the CEFR level (A1 to C2) for each of the following 100 Dutch words, based on their part of speech.",
            'Respond **only** in **valid JSON** format like: {"huis": "A1", "lopen": "A2", "xyz": "N/A"}.',
            "Do **not** translate or modify the words. Example: 'gaan (NOUN)' must remain 'gaan', not 'ga'.",
            "Mark any word that is not a valid Dutch word (including any English word) as 'N/A'.",
            "Do not include any explanation or extra text—**only return the JSON object**.",
            "do not use blocks like ```json",
        ]
        for entry in batch:
            prompt_lines.append(f"{entry.lemma} ({entry.pos})")

        prompt = "\n".join(prompt_lines)

        try:
            response = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a Dutch language teacher."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=2000,  # You can increase if needed
            )
            content = response.choices[0].message.content.strip()
            print(f"🔁 Raw response:\n{content}\n")
            print(f"total tokens: {response.usage.total_tokens}")
            # Clean up and parse JSON
            cefr_levels = json.loads(content)

            for entry in batch:
                level = cefr_levels.get(entry.lemma)
                if level in ["A1", "A2", "B1", "B2", "C1", "C2"]:
                    entry.cefr_level = level
                else:
                    print(
                        f"⚠️ No CEFR level found for {entry.lemma} or invalid: {level}"
                    )
                    entry.cefr_level = "N/A"

        except Exception as e:
            print(f"❌ Error in batch starting at index {i}: {e}")

    session.commit()
    print("🎉 All CEFR levels updated.")


def update_sentences_cefr_levels_batched(session, batch_size=50):
    sentences = session.query(Sentence).filter(Sentence.cefr_level == None).all()
    print(f"🔍 Found {len(sentences)} sentences to update.")

    for i in tqdm(range(0, len(sentences), batch_size)):
        batch = sentences[i : i + batch_size]

        prompt_lines = [
            "You are a Dutch language teacher.",
            "Determine the CEFR level (A1 to C2) for each of the following Dutch sentences.",
            'Respond ONLY in valid JSON format like this: {"Levels": ["A1", "B1", "A2"]}.',
            "Do not include any explanation or extra text—**only return the JSON object**.",
            "Mark any sentences that is obvious wrong sentence (or an English sentence) as 'N/A'.",
            "**do not use blocks** in response like ```json .... ```",
            "Here are the sentences:",
        ]

        for idx, entry in enumerate(batch, start=1):
            prompt_lines.append(f"{idx}. {entry.text.strip()}")

        prompt = "\n".join(prompt_lines)
        print(f"Prompt:\n{prompt}\n")

        try:
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a Dutch language teacher."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=3000,
            )
            content = response.choices[0].message.content.strip()

            print(f"🔁 Raw response:\n{content}\n")
            print(f"total tokens: {response.usage.total_tokens}")

            # Parse the JSON response
            cefr_levels = json.loads(content).get("Levels", [])

            if len(cefr_levels) != len(batch):
                print(
                    f"⚠️ Mismatch in levels count at batch starting index {i}: expected {len(batch)}, got {len(cefr_levels)}"
                )
                continue

            for sentence, level in zip(batch, cefr_levels):
                if level in ["A1", "A2", "B1", "B2", "C1", "C2"]:
                    sentence.cefr_level = level
                else:
                    print(
                        f"⚠️ Invalid CEFR level for sentence '{sentence.text}': {level}"
                    )
                    sentence.cefr_level = "N/A"

        except Exception as e:
            print(f"❌ Error in batch starting at index {i}: {e}")

    session.commit()
    print("🎉 All CEFR sentence levels updated.")


def is_sentence_valuable(sentence: str, processor: LanguageProcessor) -> bool:
    sentence = sentence.strip().lower()
    print(f"Validating sentence: {sentence}")

    # Early rejection for empty or punctuation-only sentences
    if not sentence or all(char in string.punctuation for char in sentence):
        return False

    words = sentence.split(" ")
    if len(words) < 3:
        return False

    # Remove trivial expressions
    skip_phrases = {
        "hey",
        "yay",
        "oké",
        "hoi",
        "dag",
        "ik ben",
        "het is goed",
        "dat klopt",
        "geen idee",
        "niet echt",
    }
    if sentence in skip_phrases:
        return False

    # Skip if contains digits and is short
    if any(char.isdigit() for char in sentence) and len(words) <= 2:
        return False

    # Skip if it's just one capitalized word (likely a name/place)
    if len(words) == 1 and words[0][0].isupper():
        return False

    # Tokenization & POS tagging
    tokens = processor.extract_tokens(sentence)

    # POS integer values based on Universal POS
    VALID_SUBJECT_POS = {92, 95, 96}  # NOUN, PRON, PROPN
    VALID_VERB_POS = {87, 100}  # AUX, VERB
    REQUIRED_CONTENT_POS = {
        92,
        96,
    }  # NOUN, PROPN (to avoid floating verbs like "Ben daar")

    has_subject = any(t.pos in VALID_SUBJECT_POS for t in tokens)
    has_action = any(t.pos in VALID_VERB_POS for t in tokens)
    has_real_content = any(t.pos in REQUIRED_CONTENT_POS for t in tokens)

    # Sentence must have all 3: subject, verb, and meaningful noun/proper noun
    return has_subject and has_action and has_real_content


def import_frequency_wordlist(
    processor: LanguageProcessor, session, file_path="words.txt"
):
    """
    Imports a Dutch word frequency list into the Vocabulary table.
    Always updates frequency if the word exists. Adds embedding if it's new.
    """
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return

    SKIP_POS = {
        "PROPN",
        "DET",
        "PRON",
        "CCONJ",
        "SCONJ",
        "PART",
        "INTJ",
        "PUNCT",
        "SYM",
        "NUM",
        "X",
    }

    added, updated, skipped = 0, 0, 0

    with open(file_path, "r", encoding="utf-8") as file:
        for line in tqdm(file, desc="📥 Importing words"):
            try:
                word, freq_str = line.strip().split()
                frequency = int(freq_str)
            except ValueError:
                print(f"⚠️ Skipping malformed line: {line.strip()}")
                continue

            doc = processor.nlp(word)
            if not doc:
                print(f"⚠️ Skipping invalid token: {word}")
                skipped += 1
                continue

            token = doc[0]
            lemma, pos = token.lemma_, token.pos_

            if pos in SKIP_POS:
                print(f"⚠️ Skipping word '{word}' with POS '{pos}'")
                skipped += 1
                continue

            existing = session.query(Vocabulary).filter_by(lemma=lemma, pos=pos).first()

            if existing:
                existing.frequency = frequency
                updated += 1
            else:
                embedding = processor.generate_embedding(lemma)
                vocab = Vocabulary(
                    lemma=lemma,
                    pos=pos,
                    frequency=frequency,
                    cefr_level=processor.estimate_cefr(lemma),
                    encounter_count=1,
                    embedding=embedding,
                )
                session.add(vocab)
                added += 1

    session.commit()
    print(f"✅ Done. {added} added, {updated} updated, {skipped} skipped.")


def import_question_groups_from_file(session, file_path: str):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Match each CEFR block with title and body independently
    record_pattern = re.compile(
        r"CEFR-niveau:\s*(A1|A2|B1|B2|C1|C2)\s*### (.*?)\n(.*?)(?=CEFR-niveau:|\Z)",
        re.DOTALL,
    )
    records = record_pattern.findall(content)

    print(f"🧠 Found {len(records)} question groups to import.")

    for cefr_level, title, entry_text in records:
        title = title.strip()

        # Extract paragraph from start up to first '# ' (question header)
        paragraph_match = re.search(r"^(.*?)(?=\n# )", entry_text, re.DOTALL)
        paragraph = paragraph_match.group(1).strip() if paragraph_match else ""

        # Extract question section header and block
        question_block_match = re.search(
            r"# (.*?)\n(.*?)(?=\n## Antwoorden)", entry_text, re.DOTALL
        )
        question_header = (
            question_block_match.group(1).strip() if question_block_match else "Vragen"
        )
        question_block = (
            question_block_match.group(2).strip() if question_block_match else ""
        )

        # Extract answers
        answers = []
        answers_match = re.search(r"## Antwoorden\n(.*)", entry_text, re.DOTALL)
        if answers_match:
            raw_answers = answers_match.group(1)
            answer_matches = re.findall(
                r"\d+:\s*(.*?)(?=(\d+:|\Z))", raw_answers, re.DOTALL
            )
            answers = [a[0].strip().rstrip(",") for a in answer_matches]

        # Extract questions
        questions = re.findall(r"\d+-\s*(.*?)(?=\d+-|\Z)", question_block, re.DOTALL)
        questions = [q.strip() for q in questions]

        print(
            f"➡️ {title} [{cefr_level}] — {len(questions)} Q / {len(answers)} A — type: {question_header}"
        )

        if len(questions) != len(answers):
            print(
                f"⚠️ Skipping '{title}' due to mismatch: {len(questions)} questions vs {len(answers)} answers"
            )
            continue

        group = QuestionGroup(
            title=title,
            question_type=(
                "statement"
                if "Waar" in question_header and "Onwaar" in question_header
                else "paragraph"
            ),
            text=paragraph,
            cefr_level=cefr_level,
            question_count=len(questions),
        )
        session.add(group)
        session.flush()

        for i, (q, a) in enumerate(zip(questions, answers), start=1):
            session.add(
                QuestionItem(
                    group_id=group.id, question_text=q, answer=a, order_index=i
                )
            )

    session.commit()
    print("✅ All question groups imported.")


def main():
    DATABASE_URL = os.getenv("DATABASE_URL")
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    processor = LanguageProcessor()

    for filename in os.listdir("data"):
        if filename.endswith(".md"):
            title = filename.replace(".md", "")
            file_path = os.path.join("data", filename)
            process_book(processor, session, file_path, title, language="Dutch")

    # update_vocabulary_cefr_levels_batched(session)
    # update_vocabulary_forms_batched(session)
    # update_sentences_cefr_levels_batched(session)
    # import_frequency_wordlist(
    #     processor, session, file_path="data/vocabulary/nl_50k.txt"
    # )
    import_question_groups_from_file(session, "data/questions/test.md")


if __name__ == "__main__":
    main()
