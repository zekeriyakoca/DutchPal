from tools.agent import SessionLocal


# Dependency to get the database session; closed when the request is done
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
