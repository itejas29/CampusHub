"""Create a registrar (super admin) account for real use.

    python -m app.seed.create_registrar --email registrar@pdpu.ac.in --name "Registrar Office"

With demo accounts switched off the demo registrar cannot sign in, so the
first real one is made here, on the server. It prints a one-time password once;
the registrar must replace it at their first sign-in. Run it again for an
existing account to issue a fresh one-time password (e.g. if it was lost).
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import func, select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.enums import AuditAction, Role
from app.models.identity import User, UserRole
from app.services import accounts, audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    email = args.email.strip().lower()
    if email.endswith(accounts.DEMO_DOMAIN):
        print("Use a real address — the demo domain is for demo accounts.")
        return 1

    password = accounts.temporary_password()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if user is None:
            user = User(email=email, full_name=args.name.strip(), is_active=True,
                        hashed_password=hash_password(password))
            db.add(user)
            db.flush()
            db.add(UserRole(user_id=user.id, role=Role.SUPER_ADMIN))
            what = "Created registrar account"
        elif not user.has_role(Role.SUPER_ADMIN):
            print("That address belongs to an account that is not a registrar; nothing changed.")
            return 1
        else:
            user.hashed_password = hash_password(password)
            what = "Issued a new one-time password to registrar"
        user.must_change_password = True
        user.sessions_valid_after = accounts.utcnow()
        audit.record(db, action=AuditAction.CREATE, entity_type="user", entity_id=user.id,
                     actor=None, description=f"{what} {email} from the server console")
        db.commit()
    print(f"{what}: {email}")
    print(f"One-time password (shown once, must be changed at first sign-in): {password}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
