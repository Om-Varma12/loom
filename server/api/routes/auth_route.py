from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from db.database import database
from dependencies.auth_dep import CurrentUser, get_current_user, upsert_user_record

router = APIRouter(tags=["Auth"])


def _primary_email(data: dict[str, Any]) -> str:
    primary_id = data.get("primary_email_address_id")
    for email in data.get("email_addresses", []):
        if email.get("id") == primary_id and email.get("email_address"):
            return str(email["email_address"])

    email_addresses = data.get("email_addresses", [])
    if email_addresses and email_addresses[0].get("email_address"):
        return str(email_addresses[0]["email_address"])

    return f"{data['id']}@clerk.local"


def _display_name(data: dict[str, Any], email: str) -> str:
    name = " ".join(
        part
        for part in [data.get("first_name"), data.get("last_name")]
        if part
    ).strip()
    return name or data.get("username") or email.split("@", maxsplit=1)[0]


def _decode_svix_secret(secret: str) -> bytes:
    encoded = secret.removeprefix("whsec_")
    try:
        return base64.b64decode(encoded)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid CLERK_WEBHOOK_SIGNING_SECRET",
        ) from exc


def _verify_clerk_webhook(
    body: bytes,
    svix_id: str | None,
    svix_timestamp: str | None,
    svix_signature: str | None,
) -> dict[str, Any]:
    secret = os.environ.get("CLERK_WEBHOOK_SIGNING_SECRET", "").strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CLERK_WEBHOOK_SIGNING_SECRET is not configured",
        )

    if not svix_id or not svix_timestamp or not svix_signature:
        raise HTTPException(status_code=400, detail="Missing Svix headers")

    try:
        timestamp = int(svix_timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid Svix timestamp") from exc

    if abs(time.time() - timestamp) > 300:
        raise HTTPException(status_code=400, detail="Stale webhook timestamp")

    signed_content = f"{svix_id}.{svix_timestamp}.".encode() + body
    digest = hmac.new(
        _decode_svix_secret(secret),
        signed_content,
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(digest).decode()

    signatures = [
        part.split(",", maxsplit=1)[1]
        for part in svix_signature.split(" ")
        if part.startswith("v1,")
    ]
    if not any(hmac.compare_digest(expected, signature) for signature in signatures):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    return json.loads(body)


@router.get("/auth/me")
async def read_current_user(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, str]:
    return {
        "id": current_user.id,
        "clerk_user_id": current_user.clerk_user_id,
        "email": current_user.email,
        "name": current_user.name,
    }


@router.post("/webhooks/clerk")
async def clerk_webhook(
    request: Request,
    svix_id: str | None = Header(default=None, alias="svix-id"),
    svix_timestamp: str | None = Header(default=None, alias="svix-timestamp"),
    svix_signature: str | None = Header(default=None, alias="svix-signature"),
):
    body = await request.body()
    payload = _verify_clerk_webhook(
        body,
        svix_id,
        svix_timestamp,
        svix_signature,
    )

    event_type = payload.get("type")
    data = payload.get("data") or {}
    clerk_user_id = data.get("id")

    if not clerk_user_id:
        raise HTTPException(status_code=400, detail="Missing Clerk user id")

    conn = await database.get_conn()
    try:
        if event_type in {"user.created", "user.updated"}:
            email = _primary_email(data)
            name = _display_name(data, email)
            await upsert_user_record(conn, str(clerk_user_id), email, name)
        elif event_type == "user.deleted":
            await conn.execute(
                "DELETE FROM users WHERE clerk_user_id = $1",
                str(clerk_user_id),
            )

        return {"status": "ok"}
    finally:
        await database.release_conn(conn)
