import os
import time
from groq import AsyncGroq

ISSUE_TYPES = [
    "late_delivery",
    "missing_items",
    "order_not_arrived",
    "wrong_items",
    "restaurant_cancelled",
    "food_quality",
    "still_preparing",
    "no_issue",
]

_SYSTEM_PROMPT = (
    "You are a classifier for a food delivery support system. "
    "Given a customer message, respond with exactly one of these categories and nothing else:\n"
    + ", ".join(ISSUE_TYPES)
)

_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=os.environ["GROQ_API_KEY"])
    return _client


async def classify_issue(text: str) -> str:
    start = time.monotonic()
    try:
        response = await _get_client().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            max_tokens=10,
            temperature=0,
        )
        result = response.choices[0].message.content.strip().lower()
        if result not in ISSUE_TYPES:
            result = "no_issue"
    except Exception as e:
        print(f"[classifier] error: {e}")
        result = "no_issue"

    latency_ms = (time.monotonic() - start) * 1000
    print(f"[classifier] {result!r:25s} {latency_ms:.0f}ms  input={text[:60]!r}")
    return result
