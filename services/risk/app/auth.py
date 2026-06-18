"""Authentication for the web app (plan §A): register / login + role guards.

Real auth, kept simple + low-dep: passwords hashed with stdlib PBKDF2-HMAC-SHA256 (per-user
salt); bearer tokens are JWTs (PyJWT). Two roles: `user` and `admin`. Local-only.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from typing import Optional

import jwt
import re
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from services.risk.app import db

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_JWT_SECRET = os.environ.get("TRUSTSHIELD_JWT_SECRET", "dev-insecure-secret-change-in-prod")
_JWT_ALGO = "HS256"
_TOKEN_TTL = 60 * 60 * 12  # 12 hours
_PBKDF2_ROUNDS = 200_000
_ROLES = {"user", "admin"}


def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ROUNDS)
    return h.hex(), salt


def verify_password(password: str, pw_hash: str, salt: str) -> bool:
    calc, _ = hash_password(password, salt)
    return hmac.compare_digest(calc, pw_hash)


def make_token(user: dict) -> str:
    payload = {
        "uid": user["id"], "email": user["email"], "role": user["role"],
        "iat": int(time.time()), "exp": int(time.time()) + _TOKEN_TTL,
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGO)


# --------------------------------------------------------------------------
# Dependencies
# --------------------------------------------------------------------------

def current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGO])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from exc
    return {"uid": claims["uid"], "email": claims["email"], "role": claims["role"]}


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="admin role required")
    return user


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

router = APIRouter(tags=["auth"])


class RegisterReq(BaseModel):
    email: str
    password: str
    role: str = "user"


class LoginReq(BaseModel):
    email: str
    password: str


@router.post("/auth/register")
def register(req: RegisterReq) -> dict:
    if not _EMAIL_RE.match(req.email.strip()):
        raise HTTPException(status_code=400, detail="invalid email address")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="password must be at least 6 characters")
    role = req.role if req.role in _ROLES else "user"
    if db.get_user_by_email(req.email):
        raise HTTPException(status_code=409, detail="email already registered")
    pw_hash, salt = hash_password(req.password)
    user = db.create_user(req.email, pw_hash, salt, role)
    return {"token": make_token(user), "email": user["email"], "role": user["role"]}


@router.post("/auth/login")
def login(req: LoginReq) -> dict:
    user = db.get_user_by_email(req.email)
    if not user or not verify_password(req.password, user["pw_hash"], user["pw_salt"]):
        raise HTTPException(status_code=401, detail="invalid email or password")
    return {"token": make_token(user), "email": user["email"], "role": user["role"]}


@router.get("/auth/me")
def me(user: dict = Depends(current_user)) -> dict:
    return user
