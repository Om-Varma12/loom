import os
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from db.database import database


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: str
    clerk_user_id: str
    email: str
    name: str
    claims: dict[str, Any]


def _clerk_public_key() -> str:
    public_key = os.environ.get("CLERK_JWT_PUBLIC_KEY", "").strip()
    if not public_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CLERK_JWT_PUBLIC_KEY is not configured",
        )
    return public_key.replace("\\n", "\n")


def verify_clerk_token(token: str) -> dict[str, Any]:
    decode_kwargs: dict[str, Any] = {
        "key": _clerk_public_key(),
        "algorithms": ["RS256"],
        "options": {
            "require": ["exp", "iat", "sub"],
            "verify_aud": bool(os.environ.get("CLERK_JWT_AUDIENCE")),
            "verify_iss": bool(os.environ.get("CLERK_ISSUER")),
        },
    }

    issuer = os.environ.get("CLERK_ISSUER")
    if issuer:
        decode_kwargs["issuer"] = issuer

    audience = os.environ.get("CLERK_JWT_AUDIENCE")
    if audience:
        decode_kwargs["audience"] = audience

    try:
        return jwt.decode(token, **decode_kwargs)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def _profile_from_claims(claims: dict[str, Any]) -> tuple[str, str, str]:
    clerk_user_id = str(claims["sub"])
    email = (
        claims.get("email")
        or claims.get("primary_email_address")
        or f"{clerk_user_id}@clerk.local"
    )
    name = (
        claims.get("name")
        or " ".join(
            part
            for part in [claims.get("given_name"), claims.get("family_name")]
            if part
        ).strip()
        or claims.get("username")
        or str(email).split("@", maxsplit=1)[0]
        or "Clerk User"
    )
    return clerk_user_id, str(email), str(name)


async def _upsert_user(conn, claims: dict[str, Any]) -> CurrentUser:
    clerk_user_id, email, name = _profile_from_claims(claims)
    row = await upsert_user_record(conn, clerk_user_id, email, name)

    return CurrentUser(
        id=str(row["id"]),
        clerk_user_id=row["clerk_user_id"],
        email=row["email"],
        name=row["name"],
        claims=claims,
    )


async def upsert_user_record(
    conn,
    clerk_user_id: str,
    email: str,
    name: str,
):
    existing = await conn.fetchrow(
        """
        SELECT id, clerk_user_id, email, name
        FROM users
        WHERE clerk_user_id = $1
        """,
        clerk_user_id,
    )

    if existing:
        row = await conn.fetchrow(
            """
            UPDATE users
            SET email = $2,
                name = $3
            WHERE clerk_user_id = $1
            RETURNING id, clerk_user_id, email, name
            """,
            clerk_user_id,
            email,
            name,
        )
    else:
        email_owner = await conn.fetchrow(
            """
            SELECT id, clerk_user_id, email, name
            FROM users
            WHERE email = $1
            """,
            email,
        )

        if email_owner:
            row = await conn.fetchrow(
                """
                UPDATE users
                SET clerk_user_id = $2,
                    name = $3
                WHERE email = $1
                  AND (clerk_user_id IS NULL OR clerk_user_id = $2)
                RETURNING id, clerk_user_id, email, name
                """,
                email,
                clerk_user_id,
                name,
            )
            if row is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email is already linked to another user",
                )
        else:
            row = await conn.fetchrow(
                """
                INSERT INTO users (clerk_user_id, email, name)
                VALUES ($1, $2, $3)
                RETURNING id, clerk_user_id, email, name
                """,
                clerk_user_id,
                email,
                name,
            )

    return row


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = verify_clerk_token(credentials.credentials)
    conn = await database.get_conn()
    try:
        return await _upsert_user(conn, claims)
    finally:
        await database.release_conn(conn)
