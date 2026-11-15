"""Bootstrap the first System Administrator:  python -m scripts.create_admin you@uni.edu 'Full Name'"""
import getpass
import sys

import app.models  # noqa: F401  (loads every model so relationships resolve)
from app.common.enums import GlobalRole
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.modules.identity.models import User

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: python -m scripts.create_admin <email> <full name>")
    email, name = sys.argv[1].lower(), sys.argv[2]
    password = getpass.getpass("Password (min 8 chars): ")
    if len(password) < 8:
        sys.exit("password too short")
    with SessionLocal() as db:
        db.add(User(email=email, full_name=name, hashed_password=hash_password(password),
                    global_role=GlobalRole.SYSTEM_ADMIN))
        db.commit()
    print(f"Created system admin {email}")
