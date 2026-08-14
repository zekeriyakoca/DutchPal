import os
import sys

from sqlalchemy import (
    create_engine,
)
from sqlalchemy.orm import sessionmaker
from langdetect import detect, DetectorFactory


sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


from tools.embed import LanguageProcessor, Vocabulary


def update_vocabulary_infinitives(session, processor, batch_size=100):
    """
    Update Vocabulary.infinitive for verbs using SpaCy lemma.
    Only update if infinitive differs from current value or is None.
    """

    vocab_query = (
        session.query(Vocabulary).filter(Vocabulary.pos == "VERB").yield_per(batch_size)
    )

    # Process in batches
    batch = []
    for entry in vocab_query:
        if not is_dutch(entry.lemma):
            print(f"Skipping non-Dutch word: {entry.lemma}")
            continue

        word = processor.nlp(entry.lemma)[0]
        lemma_infinitive = word.lemma_

        if (entry.infinitive or "").strip() != lemma_infinitive.strip():
            print(
                f"Updated infinitive for {entry.lemma} from {entry.infinitive} to {lemma_infinitive} [isVerb: {word.pos_}, language: {word.lang_}]"
            )
            # entry.infinitive = lemma_infinitive
            batch.append(entry)

        if len(batch) >= batch_size:
            # session.commit()
            batch.clear()

    # Commit remaining
    # if batch:
    #     session.commit()


DetectorFactory.seed = 0  # For consistent results


def is_dutch(text):
    try:
        return detect(text) == "nl"
    except Exception:
        return False


def main():
    DATABASE_URL = os.getenv("DATABASE_URL")
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    processor = LanguageProcessor()

    update_vocabulary_infinitives(session, processor)


if __name__ == "__main__":
    main()
