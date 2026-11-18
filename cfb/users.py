"""Manage login accounts from the command line (the admin page uses the same functions).

    docker compose exec app python -m cfb.users add justyn --admin
    docker compose exec app python -m cfb.users reset justyn
    docker compose exec app python -m cfb.users list
    docker compose exec app python -m cfb.users disable alex
    docker compose exec app python -m cfb.users enable alex
    docker compose exec app python -m cfb.users make-admin alex
    docker compose exec app python -m cfb.users remove-admin alex
"""

import argparse
import re
import secrets

from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row

from cfb.auth import hash_password
from cfb.db import connect


class UserError(Exception):
    """An account change we refuse (bad name, unknown user, last admin...).  The message is safe to show."""


def temporary_password():
    """A random 16-character password the user must change at first login."""
    return secrets.token_urlsafe(12)


def find_user(conn, username):
    """(id, is_admin, active) for a username.  Raises UserError if there's no such user."""
    row = conn.execute(
        "SELECT id, is_admin, active FROM users WHERE lower(username) = lower(%s)",
        (username,),
    ).fetchone()
    if row is None:
        raise UserError(f"No user named {username!r}.")
    return row


def other_admins(conn, user_id):
    """How many active admins there are besides this user."""
    return conn.execute(
        "SELECT count(*) FROM users WHERE is_admin AND active AND id <> %s",
        (user_id,),
    ).fetchone()[0]


def add_user(username, is_admin):
    """Create an account.  Returns its temporary password."""
    username = username.strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{2,40}", username):
        raise UserError("Usernames are 2-40 characters: letters, digits, dot, dash, underscore.")

    password = temporary_password()
    try:
        with connect() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, is_admin) VALUES (%s, %s, %s)",
                (username, hash_password(password), is_admin),
            )
    except UniqueViolation:
        raise UserError(f"A user named {username!r} already exists.") from None
    return password


def reset_password(username):
    """Give a user a new temporary password and log them out everywhere.  Returns the password."""
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
            raise UserError(f"No user named {username!r}.")
        conn.execute("DELETE FROM sessions WHERE user_id = %s", (row[0],))
    return password


def all_users():
    """Every account as a list of dicts, for the admin page and the list command."""
    with connect() as conn:
        conn.row_factory = dict_row
        return conn.execute(
            """
            SELECT id, username, is_admin, active, must_change_password, created_at, last_login_at
            FROM users
            ORDER BY lower(username)
            """
        ).fetchall()


def set_active(username, active):
    """Disable (lock out and log out) or re-enable an account."""
    with connect() as conn:
        user_id, is_admin, _ = find_user(conn, username)
        if not active and is_admin and other_admins(conn, user_id) == 0:
            raise UserError("That's the last active admin. Make someone else an admin first.")
        conn.execute("UPDATE users SET active = %s WHERE id = %s", (active, user_id))
        if not active:
            conn.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))


def set_admin(username, make_admin):
    """Give or take away admin rights."""
    with connect() as conn:
        user_id, is_admin, _ = find_user(conn, username)
        if not make_admin and is_admin and other_admins(conn, user_id) == 0:
            raise UserError("That's the last active admin. Make someone else an admin first.")
        conn.execute("UPDATE users SET is_admin = %s WHERE id = %s", (make_admin, user_id))


def print_users():
    """The list command: one line per account."""
    users = all_users()
    if not users:
        print("No users yet.")
        return
    for user in users:
        role = "admin" if user["is_admin"] else "viewer"
        status = "active" if user["active"] else "DISABLED"
        last = user["last_login_at"]
        seen = last.strftime("%Y-%m-%d %H:%M %Z") if last else "never"
        flag = "  (temporary password)" if user["must_change_password"] else ""
        print(f"{user['username']:<20} {role:<7} {status:<9} last login: {seen}{flag}")


def main():
    parser = argparse.ArgumentParser(description="Manage login accounts.")
    commands = parser.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add", help="create an account with a temporary password")
    add.add_argument("username")
    add.add_argument("--admin", action="store_true", help="may change overrides and settings")

    reset = commands.add_parser("reset", help="give a user a new temporary password")
    reset.add_argument("username")

    commands.add_parser("list", help="show all accounts")

    disable = commands.add_parser("disable", help="lock an account")
    disable.add_argument("username")

    enable = commands.add_parser("enable", help="unlock an account")
    enable.add_argument("username")

    make_admin = commands.add_parser("make-admin", help="give a user admin rights")
    make_admin.add_argument("username")

    remove_admin = commands.add_parser("remove-admin", help="take away admin rights")
    remove_admin.add_argument("username")

    args = parser.parse_args()
    try:
        if args.command == "add":
            password = add_user(args.username, args.admin)
            role = "admin" if args.admin else "viewer"
            print(f"Created {role} {args.username.strip()!r}.  Temporary password: {password}")
            print("They'll be asked to choose their own password at first login.")
        elif args.command == "reset":
            password = reset_password(args.username)
            print(f"New temporary password for {args.username!r}: {password}")
        elif args.command == "list":
            print_users()
        elif args.command == "disable":
            set_active(args.username, False)
            print(f"{args.username!r} is now disabled.")
        elif args.command == "enable":
            set_active(args.username, True)
            print(f"{args.username!r} is now enabled.")
        elif args.command == "make-admin":
            set_admin(args.username, True)
            print(f"{args.username!r} is now an admin.")
        elif args.command == "remove-admin":
            set_admin(args.username, False)
            print(f"{args.username!r} is no longer an admin.")
    except UserError as err:
        print(err)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
