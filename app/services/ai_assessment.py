"""
Calls Anthropic's API to score how well a candidate's CV matches a job's
description, per the prompt template in cv-screening-SKILL.md.

Every failure path here - a network error, a timeout, a rate limit, an
API-level error, or a response that isn't the JSON shape we asked for - is
collapsed into one exception (AssessmentFailed), with no provider-specific
detail attached. app/routers/candidates.py translates that straight to a
generic 502: never leak Anthropic's internal error messages to a client,
and no need to distinguish "Anthropic is down" from "Anthropic sent us
garbage" at the API boundary - both mean the assessment couldn't be
produced this time.
"""

import json
import re
from functools import lru_cache

import anthropic
from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings

# Matches a response wrapped in a markdown code fence, with or without a
# language tag (e.g. ```json ... ``` or ``` ... ```). Haiku sometimes wraps
# its JSON answer in one despite the system prompt saying not to - observed
# in production, not just a hypothetical.
_CODE_FENCE_RE = re.compile(r"^```[^\n]*\n?(.*?)\n?```$", re.DOTALL)


def _strip_code_fence(text: str) -> str:
    """Strip a leading/trailing markdown code fence around `text`, if
    present. Text without one is returned unchanged (just whitespace-
    trimmed), so this is safe to call unconditionally before json.loads."""
    stripped = text.strip()
    match = _CODE_FENCE_RE.match(stripped)
    return match.group(1) if match else stripped

MODEL = "claude-haiku-4-5-20251001"
# Keeps POST /candidates/{id}/assess from hanging on a slow/stuck upstream
# call - within the 15-30s range decided for this step.
REQUEST_TIMEOUT_SECONDS = 20.0

SYSTEM_PROMPT = (
    "Du är en objektiv rekryteringsassistent. Bedöm hur väl en kandidats "
    "CV matchar en jobbeskrivning. Svara ENDAST med JSON enligt schema: "
    "{score: number (1-10), strengths: string[3], gaps: string[2], "
    "summary: string (max 2 meningar)}. Var koncis och konkret, undvik "
    "generiska omdömen."
)


class AssessmentFailed(Exception):
    """Raised for any failure producing an assessment. The router catches
    this and returns a generic 502; the original cause is chained (`from`)
    for our own logs, never surfaced to the client."""


class AssessmentResult(BaseModel):
    """Validates the shape we asked Claude for.

    strengths/gaps length isn't pinned to exactly 3/2 (what the prompt
    asks for) - enforcing that exactly would fail the whole assessment on
    harmless model formatting variance; at least one item each is what
    actually matters for the feature to be useful.
    """

    score: int = Field(ge=1, le=10)
    strengths: list[str] = Field(min_length=1)
    gaps: list[str] = Field(min_length=1)
    summary: str


@lru_cache
def get_anthropic_client() -> anthropic.Anthropic:
    """FastAPI dependency: a process-wide cached Anthropic client.

    A plain dependency (like get_supabase) rather than a bare module-level
    client, so tests can swap it out via app.dependency_overrides instead
    of calling the real API.
    """
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def assess_candidate(
    client: anthropic.Anthropic, job_description: str, cv_text: str
) -> AssessmentResult:
    """Ask Claude to assess `cv_text` against `job_description`.

    Raises AssessmentFailed on any network/API failure, or if the
    response isn't valid JSON matching AssessmentResult's schema.
    """
    user_message = f"JOBBESKRIVNING:\n{job_description}\n\nCV:\n{cv_text}"

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except anthropic.AnthropicError as exc:
        # Covers timeouts, rate limits, connection errors, and API-level
        # errors alike - anthropic.AnthropicError is the common base for
        # all of them (verified against the installed SDK's exception
        # hierarchy).
        raise AssessmentFailed("Anthropic API call failed") from exc

    text = "".join(block.text for block in response.content if block.type == "text")

    try:
        payload = json.loads(_strip_code_fence(text))
        return AssessmentResult.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise AssessmentFailed(
            "Anthropic response was not the expected JSON shape"
        ) from exc
