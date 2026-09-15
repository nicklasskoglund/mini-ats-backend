"""
Translates known Postgres constraint violations into controlled 422
responses, instead of letting them bubble up as unhandled 500s.

The concrete case this exists for: an admin creating a job supplies
`customer_id` explicitly (see app/routers/jobs.py), and nothing validates
that id belongs to a real profile before the insert - if it doesn't, the
foreign key constraint on jobs.customer_id raises a Postgres error. This
wrapper catches that (and other constraint violation classes, as cheap
defense-in-depth) and turns it into a normal, documented client error.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException, status
from postgrest.exceptions import APIError

# Postgres SQLSTATE class 23 = integrity constraint violation.
# https://www.postgresql.org/docs/current/errcodes-appendix.html
_CONSTRAINT_VIOLATION_CODES = {
    "23503",  # foreign_key_violation
    "23505",  # unique_violation
    "23514",  # check_violation
}


@contextmanager
def translate_constraint_violations() -> Iterator[None]:
    """Wrap a Supabase write call; re-raise known constraint violations as
    HTTP 422 instead of letting them propagate as a 500."""
    try:
        yield
    except APIError as exc:
        if exc.code in _CONSTRAINT_VIOLATION_CODES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=exc.message,
            ) from exc
        raise
