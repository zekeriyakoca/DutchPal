from fastapi import HTTPException
from httpx import HTTPStatusError
import openai


def raise_openai_unavailable_if_provider_error(exc: Exception) -> None:
    if _is_openai_provider_error(exc):
        raise HTTPException(
            status_code=503,
            detail="OpenAI provider unavailable. Check OPENAI_API_KEY billing, quota, or model access.",
        ) from exc
    raise exc


def _is_openai_provider_error(exc: Exception) -> bool:
    current: BaseException | None = exc
    while current is not None:
        if isinstance(
            current,
            (
                openai.APIConnectionError,
                openai.APIStatusError,
                openai.AuthenticationError,
                openai.PermissionDeniedError,
                openai.RateLimitError,
            ),
        ):
            return True

        if isinstance(current, HTTPStatusError):
            request_url = str(current.request.url)
            if "api.openai.com" in request_url:
                return True

        message = str(current)
        if "insufficient_quota" in message or "api.openai.com" in message:
            return True

        current = current.__cause__ or current.__context__

    return False
