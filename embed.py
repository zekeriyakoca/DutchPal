import os
import re
import spacy
import openai
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Float,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from pgvector.sqlalchemy import Vector
from typing import List

import json
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

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
    embedding = Column(Vector(1536), nullable=False)
    book = relationship("Book", back_populates="sentences")
    section = relationship("Section", back_populates="sentences")

class Vocabulary(Base):
    __tablename__ = "vocabulary"
    id = Column(Integer, primary_key=True)
    lemma = Column(String, nullable=False)
    pos = Column(String, nullable=False)
    cefr_level = Column(String)
    encounter_count = Column(Integer, default=1)
    embedding = Column(Vector(1536), nullable=False)
    __table_args__ = (UniqueConstraint("lemma", "pos", name="_lemma_pos_uc"),)

class LanguageProcessor:
    def __init__(self, language_model='nl_core_news_sm'):
        self.nlp = spacy.load(language_model)
        openai.api_key = os.getenv("OPENAI_API_KEY")

    def generate_embedding(self, text: str) -> List[float]:
        response = openai.embeddings.create(
            model="text-embedding-ada-002",
            input=text
        )
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
        return [sent.text.strip() for sent in self.nlp(text).sents if self.is_valid_sentence(sent.text)]

    def extract_vocab(self, text: str):
        doc = self.nlp(text)
        for token in doc:
            if token.is_alpha and not token.is_stop:
                yield token.lemma_, token.pos_

    def estimate_cefr(self, word: str) -> str:
        return None  # Placeholder — replace with real level logic

def upsert_vocab(processor: LanguageProcessor, session, text: str):
    for lemma, pos in processor.extract_vocab(text):
        if pos == "PROPN":
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
                embedding=embedding
            )
            session.add(vocab)

def process_book(processor: LanguageProcessor, session, file_path: str, book_title: str, language: str):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    sections = re.findall(r"## (.*?)\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
    book = Book(title=book_title, language=language, cefr_level="A1")
    session.add(book)
    session.flush()

    for section_title, section_content in sections:
        section_embedding = processor.generate_embedding(section_content)
        section = Section(
            book_id=book.id,
            title=section_title,
            content=section_content,
            embedding=section_embedding
        )
        session.add(section)
        session.flush()

        for sentence_text in processor.extract_sentences(section_content):
            sentence_embedding = processor.generate_embedding(sentence_text)
            sentence = Sentence(
                book_id=book.id,
                section_id=section.id,
                text=sentence_text,
                embedding=sentence_embedding
            )
            session.add(sentence)
            upsert_vocab(processor, session, sentence_text)

    session.commit()
    print(f"✅ {book_title}")

def update_cefr_levels_batched(session, batch_size=100):
    vocab_entries = session.query(Vocabulary).filter(Vocabulary.cefr_level == None).all()
    print(f"🔍 Found {len(vocab_entries)} vocabulary entries to update.")

    for i in tqdm(range(0, len(vocab_entries), batch_size)):
        batch = vocab_entries[i:i + batch_size]
        
        prompt_lines = [
            "You are a Dutch language teacher.",
            "What are the CEFR levels (A1 to C2) for the following 100 Dutch words with their part of speech?",
            "Respond in JSON format like: {\"huis\": \"A1\", \"lopen\": \"A2\", ...}"
        ]
        for entry in batch:
            prompt_lines.append(f"{entry.lemma} ({entry.pos})")
        
        prompt = "\n".join(prompt_lines)

        try:
            response = openai.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a Dutch language teacher."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                max_tokens=1000  # You can increase if needed
            )
            content = response.choices[0].message.content.strip()

            # Clean up and parse JSON
            cefr_levels = json.loads(content)

            for entry in batch:
                level = cefr_levels.get(entry.lemma)
                if level in ["A1", "A2", "B1", "B2", "C1", "C2"]:
                    entry.cefr_level = level
                else:
                    print(f"⚠️ No CEFR level found for {entry.lemma} or invalid: {level}")

        except Exception as e:
            print(f"❌ Error in batch starting at index {i}: {e}")

    session.commit()
    print("🎉 All CEFR levels updated.")



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
    
    update_cefr_levels_batched(session)

if __name__ == "__main__":
    main()