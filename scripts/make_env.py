"""Create .env from .env.example with fresh random secrets.

    python -m scripts.make_env           # creates .env (refuses to overwrite)
    python -m scripts.make_env --force   # overwrite an existing .env
"""
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build(template: str) -> str:
    out = []
    for line in template.splitlines():
        if line.startswith("SECRET_KEY="):
            line = f"SECRET_KEY={secrets.token_urlsafe(48)}"
        elif line.startswith("TICKET_SIGNING_KEY="):
            line = f"TICKET_SIGNING_KEY={secrets.token_urlsafe(48)}"
        out.append(line)
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    target = ROOT / ".env"
    if target.exists() and "--force" not in sys.argv:
        sys.exit(".env already exists. Use --force to overwrite it.")
    target.write_text(build((ROOT / ".env.example").read_text(encoding="utf-8")), encoding="utf-8")
    print("Created .env with new random secrets.")
    print("Next: using Docker? The default DATABASE_URL already matches. Using your own PostgreSQL? Run: python -m scripts.set_db")
