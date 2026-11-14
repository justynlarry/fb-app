"""Login helpers: password hashing, sessions, and failed-login limits."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

SESSION_DAYS = 30
MIN_PASSWORD_LENGTH = 12
MAX_FAILS_PER_USER = 5
MAX_FAILS_PER_IP = 20
FAIL_WINDOW = timedelta(minutes=15)

hasher = PasswordHasher()


def hash_password(password):
    """Turn a password into an argon2 hash to store in users.password_hash."""
    return hasher.hash(password)


def check_password(stored_hash, password):
    """True if the password matches the stored hash, False otherwise."""
    try:
        return hasher.verify(stored_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def hash_token(token):
    """The sha256 of a session token.  Only this is stored in the database."""
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(conn, user_id):
    """Start a login session.  Returns the token to put in the browser cookie."""
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
        (hash_token(token), user_id, expires),
    )
    conn.execute("UPDATE users SET last_login_at = now() WHERE id = %s", (user_id,))
    return token


def session_user(conn, token):
    """The logged-in user for a cookie token, or None if missing/expired/disabled."""
    if not token:
        return None
    row = conn.execute(
        """
        SELECT u.id, u.username, u.is_admin, u.must_change_password
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = %s
          AND s.expires_at > now()
          AND u.active
        """,
        (hash_token(token),),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "username": row[1],
        "is_admin": row[2],
        "must_change_password": row[3],
    }


def end_session(conn, token):
    """Log out: delete this session from the database."""
    if token:
        conn.execute("DELETE FROM sessions WHERE token_hash = %s", (hash_token(token),))


def too_many_failures(conn, username, ip):
    """True if this username or IP address has failed too often recently."""
    since = datetime.now(timezone.utc) - FAIL_WINDOW
    user_fails, ip_fails = conn.execute(
        """
        SELECT count(*) FILTER (WHERE lower(username) = lower(%s)),
               count(*) FILTER (WHERE ip = %s)
        FROM login_attempts
        WHERE NOT success
          AND at > %s
        """,
        (username, ip, since),
    ).fetchone()
    return user_fails >= MAX_FAILS_PER_USER or ip_fails >= MAX_FAILS_PER_IP


def record_attempt(conn, username, ip, success):
    """Save one login attempt (for the rate limit and as a login history)."""
    conn.execute(
        "INSERT INTO login_attempts (username, ip, success) VALUES (%s, %s, %s)",
        (username, ip, success),
    )


# Checked when the username doesn't exist, so a wrong username takes
# as long as a wrong password (no hint about which usernames are real).
DUMMY_HASH = hasher.hash("not-a-real-password")


def authenticate(conn, username, password, ip):
    """Check a login.  Returns (user_id, None) on success, or (None, error message)."""
    username = username.strip()[:100]
    if too_many_failures(conn, username, ip):
        return None, "Too many failed attempts.  Try again in 15 minutes."

    row = conn.execute(
        "SELECT id, password_hash FROM users WHERE lower(username) = lower(%s) AND active",
        (username,),
    ).fetchone()
    if row is None:
        check_password(DUMMY_HASH, password)
        record_attempt(conn, username, ip, False)
        return None, "Wrong username or password."

    user_id, stored_hash = row
    if not check_password(stored_hash, password):
        record_attempt(conn, username, ip, False)
        return None, "Wrong username or password."

    record_attempt(conn, username, ip, True)
    return user_id, None


def change_password(conn, user_id, current_password, new_password, keep_token):
    """Set a new password. Returns None on success, or an error message."""
    if len(new_password) < MIN_PASSWORD_LENGTH:
        return f"Use at least {MIN_PASSWORD_LENGTH} characters."
    if new_password == current_password:
        return "Choose a new password, not the current one."
    stored_hash = conn.execute(
        "SELECT password_hash FROM users WHERE id = %s", (user_id,)
    ).fetchone()[0]
    if not check_password(stored_hash, current_password):
        return "Your current password is wrong."
    conn.execute(
        "UPDATE users SET password_hash = %s, must_change_password = false WHERE id = %s",
        (hash_password(new_password), user_id),
    )
    # Log out every other device, but keep this browser logged in
    conn.execute(
        "DELETE FROM sessions WHERE user_id = %s AND token_hash <> %s",
        (user_id, hash_token(keep_token)),
    )
    return None
