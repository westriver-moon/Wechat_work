import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from flask import jsonify, redirect, request, session, url_for

from db import get_auth_identity, upsert_auth_identity

try:
    import bit_login
except Exception:
    bit_login = None


PERM_USE_APP = 1 << 0
PERM_ANSWER = 1 << 1
PERM_ADMIN = 1 << 2

PERMISSION_NAME_MAP = {
    "use_app": PERM_USE_APP,
    "answer": PERM_ANSWER,
    "admin": PERM_ADMIN,
}

SESSION_KEY = "auth_user"
ALLOWLIST_PATH = Path(__file__).resolve().parent / "auth_identities.json"
OWNER_SALT = os.getenv("AUTH_OWNER_SALT", os.getenv("SECRET_KEY", "dev-secret-key"))
SESSION_HOURS = max(1, int(os.getenv("AUTH_SESSION_HOURS", "8")))


class AuthError(Exception):
    pass


def _permissions_from_value(raw_value) -> int:
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, list):
        bits = 0
        for item in raw_value:
            bits |= PERMISSION_NAME_MAP.get(str(item).strip().lower(), 0)
        return bits
    return 0


def permission_labels(bits: int) -> List[str]:
    labels = []
    for name, mask in PERMISSION_NAME_MAP.items():
        if bits & mask:
            labels.append(name)
    return labels


def build_owner_identity(student_code: str) -> str:
    digest = hashlib.sha256(f"{OWNER_SALT}:{student_code}".encode("utf-8")).hexdigest()
    return f"user:{digest}"


def build_external_identity(channel: str, external_id: str) -> str:
    digest = hashlib.sha256(f"{OWNER_SALT}:{channel}:{external_id}".encode("utf-8")).hexdigest()
    return f"{channel}:{digest}"


def authenticate_bit_user(username: str, password: str) -> Dict[str, str]:
    if bit_login is None:
        raise AuthError("bit-login dependency is not installed")
    if not username or not password:
        raise AuthError("username and password are required")

    try:
        login_result = bit_login.jxzxehall_login().login(username=username, password=password)
        profile = bit_login.jxzxehall.credit(login_result.get_session()).get_student_data()
    except Exception as exc:
        raise AuthError(str(exc)) from exc

    student_code = str(profile.get("student_code") or "").strip()
    name = str(profile.get("name") or "").strip()
    if not student_code or not name:
        raise AuthError("failed to resolve student profile from bit-login")

    return {
        "student_code": student_code,
        "name": name,
        "major": str(profile.get("major") or "").strip(),
        "college": str(profile.get("college") or "").strip(),
        "grade": str(profile.get("grade") or "").strip(),
        "class_name": str(profile.get("class") or "").strip(),
    }


def build_session_user(profile: Dict[str, str]) -> Dict[str, object]:
    student_code = str(profile.get("student_code") or "").strip()
    auth_identity = get_auth_identity(student_code)
    extra_permissions = 0
    is_privileged = False
    if auth_identity and int(auth_identity.get("enabled") or 0) == 1:
        extra_permissions = int(auth_identity.get("permissions") or 0)
        is_privileged = True

    permissions = PERM_USE_APP | extra_permissions
    display_name = str(profile.get("name") or "").strip()
    if auth_identity and str(auth_identity.get("display_name") or "").strip():
        display_name = str(auth_identity.get("display_name") or "").strip()

    return {
        "student_code": student_code,
        "name": display_name,
        "major": str(profile.get("major") or "").strip(),
        "college": str(profile.get("college") or "").strip(),
        "grade": str(profile.get("grade") or "").strip(),
        "class_name": str(profile.get("class_name") or "").strip(),
        "permissions": permissions,
        "permission_labels": permission_labels(permissions),
        "owner_identity": build_owner_identity(student_code),
        "is_privileged": is_privileged,
    }


def login_user(profile: Dict[str, str]) -> Dict[str, object]:
    auth_user = build_session_user(profile)
    session.permanent = True
    session[SESSION_KEY] = auth_user
    return auth_user


def logout_user() -> None:
    session.pop(SESSION_KEY, None)


def current_user() -> Optional[Dict[str, object]]:
    user = session.get(SESSION_KEY)
    return user if isinstance(user, dict) else None


def is_authenticated() -> bool:
    return current_user() is not None


def has_permission(mask: int) -> bool:
    user = current_user()
    if not user:
        return False
    return bool(int(user.get("permissions") or 0) & mask)


def login_required_response():
    if request.path.startswith("/api/"):
        return jsonify({"error": "authentication required", "login_url": "/login"}), 401
    next_url = request.full_path if request.query_string else request.path
    return redirect(url_for("login_page", next=next_url))


def permission_denied_response():
    if request.path.startswith("/api/"):
        return jsonify({"error": "forbidden"}), 403
    return redirect(url_for("index"))


def require_permission(mask: int):
    if not is_authenticated():
        return login_required_response()
    if not has_permission(mask):
        return permission_denied_response()
    return None


def sync_auth_identities_from_file() -> int:
    if not ALLOWLIST_PATH.exists():
        return 0

    try:
        raw = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AuthError(f"failed to parse auth_identities.json: {exc}") from exc

    if not isinstance(raw, list):
        raise AuthError("auth_identities.json must contain a list")

    count = 0
    for item in raw:
        if not isinstance(item, dict):
            continue
        student_code = str(item.get("student_code") or "").strip()
        if not student_code:
            continue
        upsert_auth_identity(
            student_code=student_code,
            display_name=str(item.get("display_name") or "").strip(),
            permissions=_permissions_from_value(item.get("permissions")),
            enabled=bool(item.get("enabled", True)),
            note=str(item.get("note") or "").strip(),
        )
        count += 1
    return count
