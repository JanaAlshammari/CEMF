"""Point the app at your PostgreSQL database. Handles special characters in the password.

    python -m scripts.set_db
"""
import getpass
import sys
from urllib.parse import quote

from scripts.make_env import ROOT, build


def build_url(user: str, password: str, host: str, port: str, database: str) -> str:
    # quote(): an '@' in the password becomes %40, '#' becomes %23, and so on
    return (f"postgresql+psycopg://{quote(user, safe='')}:{quote(password, safe='')}"
            f"@{host}:{port}/{database}")


def set_database_url(env_text: str, url: str) -> str:
    lines, done = [], False
    for line in env_text.splitlines():
        if line.lstrip().startswith("DATABASE_URL="):
            line, done = f"DATABASE_URL={url}", True
        lines.append(line)
    if not done:
        lines.append(f"DATABASE_URL={url}")
    return "\n".join(lines) + "\n"


def ask(label: str, default: str) -> str:
    return input(f"{label} [{default}]: ").strip() or default


if __name__ == "__main__":
    print("Enter your PostgreSQL details (press Enter to accept the value in brackets).")
    host, port = ask("Host", "localhost"), ask("Port", "5432")
    database, user = ask("Database name", "cemf"), ask("User", "postgres")
    password = getpass.getpass("Password (typing is hidden): ")
    if not password:
        sys.exit("No password entered. Nothing was changed.")

    env_path = ROOT / ".env"
    if not env_path.exists():
        env_path.write_text(build((ROOT / ".env.example").read_text(encoding="utf-8")), encoding="utf-8")
        print("Created .env with new random secrets.")
    env_path.write_text(set_database_url(env_path.read_text(encoding="utf-8"),
                                         build_url(user, password, host, port, database)),
                        encoding="utf-8")
    print(f"Saved DATABASE_URL for database '{database}'. Check it with: python -m scripts.doctor")
