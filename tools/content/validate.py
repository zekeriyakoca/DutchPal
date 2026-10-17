"""Validate extracted book chapters in content/<book>/chXX.json.

Usage: python tools/content/validate.py content/nl-in-gang/ch01.json [...]
Exits non-zero if any chapter has errors.
"""

import json
import os
import sys
from collections import Counter
from pathlib import Path, PurePosixPath

EXERCISE_TYPES = {
    "speaking_pair", "speaking_roleplay", "fill_gap", "choose_option",
    "personal_questions", "teacher_material", "classroom_activity",
    "form_fill", "listening_stress", "matching", "ordering", "reading",
    "listening", "writing", "comprehension_questions", "puzzle",
    "pronunciation", "rewrite", "word_stress", "dialogue_completion",
    "speaking",
}
QA_TYPES = {"comprehension_questions", "puzzle", "reading"}
ARTICLES = {"de", "het"}
# Media paths in exercises are relative to the media root served at /media (see routes/media.py).
MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "media"))


def media_errors(ex: dict, warnings: list[str]) -> list[str]:
    """Check audio/video/images/option_images paths: relative, no '..', and (warning) present locally."""
    paths = [ex[k] for k in ("audio", "video") if k in ex]
    paths += ex.get("images", []) + ex.get("option_images", [])
    errors = []
    for p in paths:
        pure = PurePosixPath(p) if isinstance(p, str) else None
        if not pure or not p or pure.is_absolute() or ".." in pure.parts or "\\" in p:
            errors.append(f"{ex['id']}: bad media path {p!r}")
        elif not (MEDIA_DIR / p).is_file():
            warnings.append(f"{ex['id']}: media file not found under {MEDIA_DIR}: {p}")
    return errors


def mc_errors(ex: dict) -> list[str]:
    """Multiple-choice items [{n, q, options, a}] with `a` one of the options."""
    errors = []
    for item in ex.get("items", []):
        if not item.get("q") or not item.get("options") or item.get("a") not in item["options"]:
            errors.append(f"{ex['id']} #{item.get('n')}: needs q, options and an answer from the options")
    if "option_images" in ex and any(len(ex["option_images"]) != len(i["options"]) for i in ex.get("items", [])):
        errors.append(f"{ex['id']}: option_images and options differ in length")
    return errors


def book_pages_found(chapter: dict) -> set[int]:
    pages = set()

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("book_page"), int):
                pages.add(node["book_page"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(chapter)
    return pages


def validate(path: Path) -> tuple[list[str], list[str], dict]:
    errors, warnings = [], []
    data = json.loads(path.read_text(encoding="utf-8"))
    ch = data["chapter"]

    if ch.get("book_pages"):
        first, last = ch["book_pages"]
        missing = sorted(set(range(first, last + 1)) - book_pages_found(data))
        if missing:
            warnings.append(f"book pages without content: {missing}")
    elif ch.get("authored"):
        if not ch.get("note"):
            errors.append("authored chapter has no note saying so")
        for ex in data.get("exercises", []):
            if ex.get("answers_source") != "generated_needs_review":
                errors.append(f"{ex['id']}: authored exercise must have answers_source generated_needs_review")
    elif not ch.get("source_images") and not ch.get("source_files"):
        errors.append("chapter has neither book_pages, source_images, source_files nor authored")
    if not ch.get("goals") and ch.get("goals_printed", True):
        errors.append("chapter has no goals")

    for d in data.get("dialogues", []):
        for i, line in enumerate(d["lines"]):
            if line.get("stage") or line.get("narration"):
                if not line.get("text", "").strip():
                    errors.append(f"{d['id']} line {i}: empty text")
                continue
            if not line.get("speaker") or not line.get("text", "").strip():
                errors.append(f"{d['id']} line {i}: missing speaker or text")

    words = []
    for vlist in data.get("vocabulary", []):
        if "generated" in vlist and not isinstance(vlist["generated"], bool):
            errors.append(f"vocab list '{vlist.get('list')}': generated must be true or false")
        if ch.get("authored") and vlist.get("generated") is not True:
            errors.append(f"vocab list '{vlist.get('list')}': authored chapter needs generated: true")
        if vlist.get("generated") and vlist.get("book_page"):
            errors.append(f"vocab list '{vlist.get('list')}': generated list cannot have a book_page")
        for item in vlist["items"]:
            words.append(item["nl"])
            if not item.get("en"):
                errors.append(f"vocab '{item['nl']}': missing translation")
            if not item.get("lemma"):
                errors.append(f"vocab '{item['nl']}': missing lemma")
            if item.get("article") and item["article"] not in ARTICLES:
                errors.append(f"vocab '{item['nl']}': bad article {item['article']}")
    dupes = [w for w, n in Counter(words).items() if n > 1]
    if dupes:
        warnings.append(f"vocab repeated across lists (ok if intended): {dupes}")

    for ex in data.get("exercises", []):
        if ex["type"] not in EXERCISE_TYPES:
            errors.append(f"{ex['id']}: unknown type {ex['type']}")
        if ex["type"] == "fill_gap":
            for item in ex["items"]:
                gaps = item["text"].count("___")
                if gaps != len(item.get("answers", [])):
                    errors.append(f"{ex['id']} #{item['n']}: {gaps} gaps but {len(item.get('answers', []))} answers")
        if ex["type"] in QA_TYPES:
            for item in ex.get("items", []):
                if not item.get("q") or not item.get("a"):
                    errors.append(f"{ex['id']} #{item['n']}: missing q or a")
                if item.get("options") and item.get("a") not in item["options"]:
                    errors.append(f"{ex['id']} #{item['n']}: answer not in options")
        if ex["type"] == "rewrite":
            for item in ex["items"]:
                if not item.get("a"):
                    errors.append(f"{ex['id']} #{item['n']}: missing a")
        if ex["type"] == "word_stress":
            for item in ex["items"]:
                if item.get("stressed", "").lower() not in item["word"].lower():
                    errors.append(f"{ex['id']} #{item['n']}: stressed part not in word")
        if ex["type"] == "dialogue_completion":
            for i, line in enumerate(ex["lines"]):
                if "___" in line["text"] and not line.get("model"):
                    errors.append(f"{ex['id']} line {i}: gap without model answer")
        if ex["type"] == "choose_option":
            for item in ex["items"]:
                if item.get("answer") not in item.get("options", []):
                    errors.append(f"{ex['id']} #{item['n']}: answer not in options")
        # Exam-style shapes (staatsexamen-b1): audio-backed listening, writing with criteria, speaking.
        if ex["type"] == "listening" and "audio" in ex:
            if not isinstance(ex.get("items"), list):
                errors.append(f"{ex['id']}: listening with audio needs items (may be empty for an intro)")
            errors += mc_errors(ex)
        if ex["type"] == "writing" and "criteria" in ex:
            if not ex.get("prompt") or not ex["criteria"] or not all(isinstance(c, str) and c for c in ex["criteria"]):
                errors.append(f"{ex['id']}: writing needs a prompt and non-empty criteria strings")
            for item in ex.get("items", []):
                if not item.get("q"):
                    errors.append(f"{ex['id']} #{item.get('n')}: missing q")
        if ex["type"] == "speaking":
            if not ex.get("audio") or not ex.get("prompt") or not isinstance(ex.get("criteria"), list):
                errors.append(f"{ex['id']}: speaking needs audio, prompt and a criteria list")
        if ex["type"] == "reading" and "title" in ex and not ex.get("text"):
            errors.append(f"{ex['id']}: reading with a title needs text")
        errors += media_errors(ex, warnings)

    stats = {
        "goals": len(ch.get("goals", [])),
        "dialogue_lines": sum(len(d["lines"]) for d in data.get("dialogues", [])),
        "new_words": sum(len(d.get("new_words", [])) for d in data.get("dialogues", [])),
        "vocab_items": len(words),
        "generated_vocab": sum(len(v["items"]) for v in data.get("vocabulary", []) if v.get("generated")),
        "unique_lemmas": len({i["lemma"].lower() for v in data.get("vocabulary", []) for i in v["items"]}),
        "grammar_topics": len(data.get("grammar", [])),
        "exercises": len(data.get("exercises", [])),
        "interactive_items": sum(len(e.get("items", [])) for e in data.get("exercises", []) if e["type"] in {"fill_gap", "choose_option"}),
        "can_do": len(data.get("reflection", {}).get("can_do", [])),
    }
    return errors, warnings, stats


def main() -> int:
    failed = False
    for arg in sys.argv[1:]:
        errors, warnings, stats = validate(Path(arg))
        print(f"{arg}: {'OK' if not errors else 'FAILED'}  {stats}")
        for w in warnings:
            print(f"  warning: {w}")
        for e in errors:
            print(f"  error: {e}")
        failed |= bool(errors)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
