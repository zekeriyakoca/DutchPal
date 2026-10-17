"""Tables for extracted book chapters (schema v1, see docs/06-content-extraction.md).

These use their own declarative Base so `create_all` only ever touches these tables;
the old tables (books, sections, sentences, vocabulary, question_*) stay as they are.

Each child row keeps its natural key from the JSON (`source_id`, e.g. `ch01-o2`, or the
list/item position for vocabulary) so the importer can upsert instead of duplicating.
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Chapter(Base):
    __tablename__ = "chapters"
    id = Column(Integer, primary_key=True)
    book_id = Column(String, nullable=False)  # slug, e.g. "nl-in-gang"
    book_title = Column(String, nullable=False)
    book_cefr = Column(String, nullable=True)
    number = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    schema_version = Column(Integer, nullable=False)
    pdf_page_first = Column(Integer, nullable=True)
    pdf_page_last = Column(Integer, nullable=True)
    book_page_first = Column(Integer, nullable=True)
    book_page_last = Column(Integer, nullable=True)
    goals = Column(JSONB, nullable=False, default=list)
    culture = Column(JSONB, nullable=False, default=list)
    reflection = Column(JSONB, nullable=True)
    source_images = Column(JSONB, nullable=False, default=list)  # books delivered as screenshots
    note = Column(Text, nullable=True)
    imported_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    dialogues = relationship("Dialogue", back_populates="chapter", cascade="all, delete-orphan")
    vocab_entries = relationship("VocabEntry", back_populates="chapter", cascade="all, delete-orphan")
    grammar_topics = relationship("GrammarTopic", back_populates="chapter", cascade="all, delete-orphan")
    exercises = relationship("Exercise", back_populates="chapter", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("book_id", "number", name="uq_chapters_book_number"),)


class Dialogue(Base):
    __tablename__ = "dialogues"
    id = Column(Integer, primary_key=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id = Column(String, nullable=False)  # e.g. "ch01-d1"
    position = Column(Integer, nullable=False)
    title = Column(String, nullable=True)
    book_page = Column(Integer, nullable=True)
    audio_tracks = Column(JSONB, nullable=False, default=list)
    lines = Column(JSONB, nullable=False)  # [{speaker, text, stage? | narration?}]
    new_words = Column(JSONB, nullable=False, default=list)  # words printed in italics (no translation)

    chapter = relationship("Chapter", back_populates="dialogues")

    __table_args__ = (UniqueConstraint("chapter_id", "source_id", name="uq_dialogues_chapter_source"),)


class VocabEntry(Base):
    __tablename__ = "vocab_entries"
    id = Column(Integer, primary_key=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    list_position = Column(Integer, nullable=False)  # index of the printed list in the chapter
    item_position = Column(Integer, nullable=False)  # index of the word in that list
    list_name = Column(String, nullable=True)
    book_page = Column(Integer, nullable=True)
    nl = Column(String, nullable=False)  # as printed
    lemma = Column(String, nullable=False, index=True)
    article = Column(String, nullable=True)  # de / het
    form = Column(String, nullable=True)
    en = Column(String, nullable=False)
    generated = Column(Boolean, nullable=True)  # list not printed in the book; translations generated

    chapter = relationship("Chapter", back_populates="vocab_entries")

    __table_args__ = (
        UniqueConstraint("chapter_id", "list_position", "item_position", name="uq_vocab_entries_position"),
    )


class GrammarTopic(Base):
    __tablename__ = "grammar_topics"
    id = Column(Integer, primary_key=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id = Column(String, nullable=False)  # e.g. "ch01-g1"
    position = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    book_page = Column(Integer, nullable=True)
    content = Column(JSONB, nullable=False)  # pairs / table / examples / conjugation / ...

    chapter = relationship("Chapter", back_populates="grammar_topics")

    __table_args__ = (UniqueConstraint("chapter_id", "source_id", name="uq_grammar_topics_chapter_source"),)


class Exercise(Base):
    __tablename__ = "exercises"
    id = Column(Integer, primary_key=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id = Column(String, nullable=False)  # e.g. "ch01-o2"
    position = Column(Integer, nullable=False)
    label = Column(String, nullable=True)  # e.g. "Opdracht 2"
    book_page = Column(Integer, nullable=True)
    type = Column(String, nullable=False, index=True)
    instruction = Column(Text, nullable=True)
    # Where the answers come from; "generated_needs_review" = written by Claude, not printed in the book.
    answers_source = Column(String, nullable=True, index=True)
    payload = Column(JSONB, nullable=False)  # items / options / answers / prompts / parts / ...

    chapter = relationship("Chapter", back_populates="exercises")

    __table_args__ = (UniqueConstraint("chapter_id", "source_id", name="uq_exercises_chapter_source"),)
