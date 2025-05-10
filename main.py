from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import sentences, vocabulary, quiz, ask, chat, grammar, translate, bootstrap

app = FastAPI(root_path="/dutchpal-api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "https://dutchpal.netlify.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
def health_check():
    """
    Health check endpoint to verify the application is running.
    """
    return {"status": "ok"}


app.include_router(bootstrap.router)
app.include_router(chat.router)
app.include_router(ask.router)
app.include_router(sentences.router)
app.include_router(vocabulary.router)
app.include_router(quiz.router)
app.include_router(grammar.router)
app.include_router(translate.router)
