from __future__ import annotations

import hashlib
import hmac
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from uuid import UUID
from email_validator import validate_email
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import DecodeError, ExpiredSignatureError, encode, decode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models import User

oauth_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/verify-code", auto_error=False)


def normalize_email(raw: str) -> str:
    try:
        return validate_email(raw.strip(), check_deliverability=False).normalized.lower()
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Enter a valid email address.") from exc


def hash_code(email: str, code: str) -> str:
    return hmac.new(settings.jwt_secret.encode(), f"{email}:{code}".encode(), hashlib.sha256).hexdigest()


def create_access_token(user_id: str) -> str:
    return encode(
        {"sub": user_id, "exp": datetime.now(UTC) + timedelta(days=settings.jwt_days)},
        settings.jwt_secret,
        algorithm="HS256",
    )


async def current_user(
    token: str | None = Depends(oauth_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in again.")
    try:
        payload = decode(token, settings.jwt_secret, algorithms=["HS256"])
        raw_user_id = payload.get("sub")
        user_id = UUID(raw_user_id) if isinstance(raw_user_id, str) else None
    except (DecodeError, ExpiredSignatureError):
        user_id = None
    except (TypeError, ValueError):
        user_id = None
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in again.")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in again.")
    return user


def smtp_is_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_from)


def _deliver_code(email: str, code: str) -> None:
    message = EmailMessage()
    message["Subject"] = "Your Saarthi sign-in code"
    message["From"] = settings.smtp_from
    message["To"] = email
    message.set_content(
        f"Your sign-in code is {code}. It expires in 10 minutes.\n\n"
        "If you did not request this code, you can ignore this email."
    )
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)


async def send_code(email: str, code: str) -> None:
    import anyio

    await anyio.to_thread.run_sync(_deliver_code, email, code)
