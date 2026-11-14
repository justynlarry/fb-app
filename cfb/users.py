"""Manage login accounts from the command line.

    docker compose exec app python -m cfb.users add justyn --admin
    docker compose exec app python -m cfb.users reset justyn
    docker compose exec app python -m cfb.users list
    docker compose exec app python -m cfb.users disable alex
    docker compose exec app python -m cfb.users enable alex
"""

import argparse
import re
import secrets

from psycopg.errors import UniqueViolation

from cfb.auth import hash_password
from cfb.db import connect


def temporary_password():
    """A random 16-character password the user must change at first login."""
    return secrets.token_urlsafe(12)


def add_user(username, is_admin):
    """Create an account and print its temporary password."""
    username = username.strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{2,40}", username):
        print("Usernames are 2-40 characters: letters, digits, dot, dash, underscore.")
        return

    password = temporary_password()
    try:
        with connect() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, is_admin) VALUES (%s, %s, %s)",
                (username, hash_password(password), is_admin),
            )
    except UniqueViolation:
        print(f"A user named {username!r} already exists.")
        return

    role = "admin" if is_admin else "viewer"
    print(f"Created {role} {username!r}.  Temporary password: {password}")
    print("They'll be asked to choose their own password at first login.")


def reset_password(username):
    """Give a user a new temporary password and log them out everywhere."""
    password = temporary_password()
    with connect() as conn:
        row = conn.execute(
            """
            UPDATE users
            SET password_hash = %s, must_change_password = true
            WHERE lower(username) = lower(%s)
            RETURNING id
            """,
            (hash_password(password), username),
        ).fetchone()
        if row is None:
            print(f"No user named {username!r}.")
            return
        conn.execute("DELETE FROM sessions WHERE user_id = %s", (row[0],))
    print(f"New temporary password for {username!r}: {password}")


def list_users():
    """Print every account."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT username, is_admin, active, must_change_password, last_login_at
            FROM users
            ORDER BY lower(username)
            """
        ).fetchall()
    if not rows:
        print("No users yet.")
        return
    for username, is_admin, active, must_change, last_login in rows:
        role = "admin" if is_admin else "viewer"
        status = "active" if active else "DISABLED"
        seen = last_login.strftime("%Y-%m-%d %H:%M %Z") if last_login else "never"
        flag = "  (temporary password)" if must_change else ""
        print(f"{username:<20} {role:<7} {status:<9} last login: {seen}{flag}")


def set_active(username, active):
    """Disable (lock out and log out) or re-enable an account."""
    with connect() as conn:
        row = conn.execute(
            "UPDATE users SET active = %s WHERE lower(username) = lower(%s) RETURNING id",
            (active, username),
        ).fetchone()
        if row is None:
            print(f"No user named {username!r}.")
            return
        if not active:
            conn.execute("DELETE FROM sessions WHERE user_id = %s", (row[0],))
    state = "enabled" if active else "disabled"
    print(f"{username!r} is now {state}.")


def main():
    parser = argparse.ArgumentParser(description="Manage login accounts.")
    commands = parser.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add", help="create an account with a temporary password")
    add.add_argument("username")
    add.add_argument("--admin", action="store_true", help="may change overrides")

    reset = commands.add_parser("reset", help="give a user a new temporary password")
    reset.add_argument("username")

    commands.add_parser("list", help="show all accounts")

    disable = commands.add_parser("disable", help="lock an account")
    disable.add_argument("username")

    enable = commands.add_parser("enable", help="unlock an account")
    enable.add_argument("username")

    args = parser.parse_args()
    if args.command == "add":
        add_user(args.username, args.admin)
    elif args.command == "reset":
        reset_password(args.username)
    elif args.command == "list":
        list_users()
    elif args.command == "disable":
        set_active(args.username, False)
    elif args.command == "enable":
        set_active(args.username, True)


if __name__ == "__main__":
    main()
