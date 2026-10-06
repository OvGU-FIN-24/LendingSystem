"""
Operator commands. Run inside the backend container, for example:

    docker compose exec backend python manage.py set-password <email>
    docker compose exec backend python manage.py reset-link <email>
    python manage.py seed-demo [--force-dev]   # development only

Does not start the mail scheduler.
"""
import argparse
import getpass
import sys

import password_reset
from authz import AuthzError
from config import public_base_url, testing_on


def _user_or_exit(email):
    user = password_reset.find_user(email)
    if user is None:
        sys.exit(f"No user with email {email}")
    return user


def set_password(email):
    user = _user_or_exit(email)
    new_password = getpass.getpass("New password: ")
    if new_password != getpass.getpass("Repeat new password: "):
        sys.exit("Passwords do not match")
    try:
        password_reset.set_password(user, new_password)
    except AuthzError as e:
        sys.exit(e.message)
    print("Password changed; the user's other sessions are signed out.")


def reset_link(email):
    if not public_base_url:
        sys.exit("public_base_url is not set; set it in backend.env or use set-password")
    user = _user_or_exit(email)
    print(password_reset.issue_link(user))
    print("Valid for 1 hour, single use. Send it to the user over a trusted channel.", file=sys.stderr)


def seed_demo(force_dev):
    if not (testing_on or force_dev):
        sys.exit("seed-demo loads demo users with a published password. It only runs with "
                 "testing_on=1 or --force-dev, never on a production database.")
    import seed_demo as demo
    created = demo.seed()
    summary = ", ".join(f"{count} {kind}" for kind, count in sorted(created.items())) or "nothing new"
    print(f"Demo data loaded ({summary}). Password of all demo users: {demo.DEMO_PASSWORD}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="LendingSystem operator commands")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("set-password", help="set a user's password interactively").add_argument("email")
    commands.add_parser("reset-link", help="print a one-hour password reset link").add_argument("email")
    seed = commands.add_parser("seed-demo", help="load Harry Potter demo data (development only)")
    seed.add_argument("--force-dev", action="store_true",
                      help="allow seeding without testing_on (development databases only)")
    args = parser.parse_args(argv)

    if args.command == "set-password":
        set_password(args.email)
    elif args.command == "reset-link":
        reset_link(args.email)
    else:
        seed_demo(args.force_dev)


if __name__ == "__main__":
    main()
