import os
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class WordList(Base):
    __tablename__ = "wordlist"
    id = Column(Integer, primary_key=True)
    word = Column(String, unique=True, nullable=False)


def insert_words_from_file(session, file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        words = [line.strip() for line in f if line.strip()]

    print(f"📄 Found {len(words)} words in file.")

    for word in words:
        session.add(WordList(word=word))

    try:
        session.commit()
        print("✅ Words inserted into 'wordlist'.")
    except Exception as e:
        session.rollback()
        print(f"❌ DB insert failed: {e}")


def main():
    DATABASE_URL = os.getenv("DATABASE_URL")
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    insert_words_from_file(session, "data/wordlist.txt")


if __name__ == "__main__":
    main()
