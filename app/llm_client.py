import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


def get_api_config() -> dict[str, str]:
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env", override=False)

    api_key = (
        os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or ""
    )

    base_url = (
        os.getenv("DEEPSEEK_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or "https://api.deepseek.com/v1"
    ).rstrip("/")

    model = (
        os.getenv("DEEPSEEK_MODEL")
        or os.getenv("OPENAI_MODEL")
        or "deepseek-chat"
    )

    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
    }


async def call_llm(
    prompt: str,
    max_tokens: int = 2000,
    temperature: float = 0.3,
) -> str:
    config = get_api_config()

    if not config["api_key"]:
        raise RuntimeError(
            "Missing API key. Set DEEPSEEK_API_KEY in the project .env file."
        )

    url = f"{config['base_url']}/chat/completions"

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {config['api_key']}",
                "Content-Type": "application/json",
            },
            json={
                "model": config["model"],
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )

        response.raise_for_status()
        data: dict[str, Any] = response.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            "The model API returned an unexpected response format."
        ) from exc

    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("The model API returned an empty response.")

    return content.strip()