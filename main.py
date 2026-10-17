from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from routes import (
    vocabulary,
    quiz,
    chat,
    grammar,
    translate,
    bootstrap,
    translate_word,
    content,
    word,
)
from utils.llm_json import LlmJsonError

app = FastAPI(root_path="/dutchpal-api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "https://dutchpal.netlify.app",
        "https://dutchpal.lontray.art",
    ],
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


@app.exception_handler(LlmJsonError)
def llm_json_error(request: Request, exc: LlmJsonError):
    # The model answered, but not with the JSON we asked for (even after a retry).
    return JSONResponse(status_code=502, content={"detail": str(exc)})


app.include_router(bootstrap.router)
app.include_router(chat.router)
app.include_router(vocabulary.router)
app.include_router(quiz.router)
app.include_router(grammar.router)
app.include_router(translate.router)
app.include_router(translate_word.router)
app.include_router(content.router)
app.include_router(word.router)
