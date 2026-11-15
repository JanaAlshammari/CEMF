"""Checks your setup and says what to fix:   python -m scripts.doctor"""
import sys

OK, BAD = "[ok]  ", "[FIX] "


def main() -> int:
    problems = 0

    def report(ok: bool, message: str, hint: str = "") -> None:
        nonlocal problems
        print((OK if ok else BAD) + message)
        if not ok:
            problems += 1
            if hint:
                print("       " + hint)

    try:
        from app.core.config import settings
        report(True, ".env loaded")
    except Exception:
        report(False, "Could not read settings from .env",
               "Run `python -m scripts.make_env`, then check DATABASE_URL.")
        return 1
    report(settings.secret_key not in ("", "change-me") and settings.ticket_signing_key not in ("", "change-me-too"),
           "Secret keys are set", "Run `python -m scripts.make_env --force` to generate new ones.")

    from sqlalchemy import create_engine, inspect, text
    try:
        engine = create_engine(settings.database_url)
        with engine.connect() as conn:
            report(True, "Connected to the database")
            ext = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'btree_gist'")).first()
            report(bool(ext), "btree_gist extension is installed (prevents venue double-booking)",
                   "Run `alembic upgrade head`; the first migration must contain "
                   "CREATE EXTENSION IF NOT EXISTS btree_gist.")
            tables = set(inspect(conn).get_table_names())
            needed = {"users", "clubs", "events", "registrations", "tickets", "resource_bookings",
                      "attendance_records", "certificates", "feedback"}
            report(needed <= tables, "Database tables exist",
                   "Missing: " + ", ".join(sorted(needed - tables)) + ". Run `alembic upgrade head`.")
            if "users" in tables:
                admins = conn.execute(text("SELECT count(*) FROM users WHERE global_role = 'system_admin'")).scalar()
                report(admins > 0, f"{admins} admin account(s)",
                       "Run `python -m scripts.create_admin you@uni.edu \"Your Name\"` or `python -m scripts.seed_demo`.")
    except Exception as exc:
        first_line = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        report(False, f"Could not connect to the database: {first_line}",
               "Is PostgreSQL running? Do the user, password and database name in DATABASE_URL exist? "
               "Run `python -m scripts.set_db` to enter your details; it encodes special characters for you.")
    print("\nAll good." if not problems else f"\n{problems} thing(s) to fix.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
