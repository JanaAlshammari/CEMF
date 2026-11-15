# Campus Event Management Framework (CEMF)

A service-oriented web application for university student clubs. Clubs publish events, students register and receive **QR tickets**, organisers **scan attendance** at the door, attendees earn **verifiable certificates**, and everyone gives feedback that turns into **performance reports**.

Built with **FastAPI**, **PostgreSQL**, **SQLAlchemy**, **JWT** authentication, **Tailwind CSS** and the Python **qrcode** library.

<!-- Add screenshots to a docs/ folder and show them here, for example:
![Events page](docs/events.png) -->

## Features

| Service | What it does |
|---|---|
| **Club & Membership** | Club profiles, club-scoped roles (member, committee leader, president), system administrators |
| **Event Management** | Draft, publish, cancel and complete events with sessions, categories and seat limits |
| **Resource & Equipment** | Venues and equipment with admin approval and **conflict-free booking** (enforced by the database) |
| **Registration & Ticketing** | Seat registration, automatic **waitlist**, signed QR tickets, "My tickets" |
| **Attendance & Certification** | Camera or manual check-in per session, attendance reports, **PDF certificates** with public verification |
| **Feedback & Evaluation** | Post-event ratings and comments, anonymous option, statistics, CSV export |

Role-based access control (RBAC) protects every action. See [Roles](#roles-and-permissions).

## Team

Developed as a university project by:

| Name | Role / contribution | GitHub |
|---|---|---|
| Full Name | Team lead | [@username](https://github.com/username) |
| Full Name |  | [@username](https://github.com/username) |
| Full Name |  | [@username](https://github.com/username) |
| Full Name |  | [@username](https://github.com/username) |
| Full Name |  | [@username](https://github.com/username) |

**Course:** ARTI 303, University name
**Supervisor:** Dr. Name
**Year:** 2026

## Tech stack

Python 3.10+, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, PyJWT + Argon2, Jinja2, Tailwind CSS (CDN), `qrcode`, ReportLab, jsQR (in-browser QR scanning).

## Quick start

You need **Python 3.10 or newer** and **PostgreSQL 14 or newer**. The easiest way to get PostgreSQL is Docker (Option A). Without Docker, use Option B.

### 1. Get the code and install

**Windows (PowerShell)**
```powershell
git clone https://github.com/YOUR-USERNAME/cemf.git
cd cemf
python -m venv venv
.\venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
python -m scripts.make_env
```

**macOS / Linux**
```bash
git clone https://github.com/YOUR-USERNAME/cemf.git
cd cemf
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m scripts.make_env
```

`make_env` creates your `.env` file with fresh random secrets.

### 2. Start a database

**Option A: Docker** (matches the default `.env`, nothing to configure)
```bash
docker compose up -d db
```

**Option B: PostgreSQL installed on your computer** (download it from postgresql.org if you don't have it)

1. Create an empty database called `cemf`. The easiest way is **pgAdmin** (installed with PostgreSQL): connect to your server, right-click **Databases**, choose **Create** then **Database...**, name it `cemf` and save.
   Prefer the terminal? `psql -U postgres -c "CREATE DATABASE cemf;"` works if `psql` is on your PATH. On Windows it usually isn't, so use pgAdmin instead.
2. Tell the app how to connect:
```bash
python -m scripts.set_db
```
It asks for the host, database name, user and password, and writes `DATABASE_URL` into `.env`. Special characters in the password (such as `@`) are handled for you.

### 3. Create the tables
```bash
alembic upgrade head
```

### 4. Add some data

Pick one:
```bash
python -m scripts.seed_demo                       # demo accounts, a club, venues and 2 events (development only)
python -m scripts.create_admin you@uni.edu "Your Name"   # just one real admin account
```

### 5. Run it
```bash
uvicorn app.main:app --reload
```

| Address | What |
|---|---|
| http://127.0.0.1:8000 | The website |
| http://127.0.0.1:8000/docs | Interactive API documentation (Swagger) |
| http://127.0.0.1:8000/health | Health check |

Something wrong? Run `python -m scripts.doctor`. It checks your setup and tells you what to fix.

## Demo accounts

After `python -m scripts.seed_demo`, every account uses the password `Demo12345`. These are for local development only. Never run the seed script on a real deployment.

| Email | Role |
|---|---|
| `admin@cemf.test` | System administrator |
| `leader@cemf.test` | President of the Chess Club |
| `student1@cemf.test`, `student2@cemf.test` | Students |

**A quick tour**
1. Log in as `student1` and register for *Chess Strategy Workshop* (2 seats). Register `student2` too, then a third student: they join the waitlist.
2. Open **My tickets** to see the QR ticket.
3. Log in as `leader` and open **Manage**. Use **Check-in** to scan a ticket (the paste box works if you have no camera), then **Attendees** and **Report**.
4. As `admin`, open **Manage** to approve venue booking requests.

## Roles and permissions

| Role | Scope | Can do |
|---|---|---|
| **Student** | Platform | Browse, register, get tickets, rate events, claim certificates |
| **Member** | Per club | Same as a student |
| **Committee leader** | Per club | Create, edit, publish, cancel and complete the club's events; request venues and equipment; check people in; view attendees and reports |
| **Club president** | Per club | Everything a committee leader can do, plus change member roles |
| **System administrator** | Platform | Everything, plus create clubs and resources, approve bookings, assign platform roles |

A person can hold different roles in different clubs. Platform-wide permissions are checked on every request, so changing a role takes effect immediately.

## Configuration

Settings live in `.env` (see `.env.example`):

| Variable | Meaning |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `SECRET_KEY` | Signs login tokens. Keep it secret |
| `TICKET_SIGNING_KEY` | Signs ticket QR codes. Keep it secret |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | How long a login lasts (default 60) |
| `CORS_ORIGINS` | Allowed browser origins, as a JSON list |
| `TIMEZONE_NAME` | Time zone for dates on certificates (default `Asia/Riyadh`) |

**Never commit `.env`.** It is already in `.gitignore`.

## Project structure

```
cemf/
├── app/
│   ├── main.py                 # FastAPI app: mounts the API and the website
│   ├── core/                   # config, database session, JWT security, RBAC dependencies
│   ├── common/                 # base model, enums (roles, statuses), shared types
│   ├── modules/                # one package per service
│   │   ├── identity/           #   users, login, registration
│   │   ├── clubs/              #   clubs, memberships
│   │   ├── events/             #   events, sessions
│   │   ├── resources/          #   venues, equipment, bookings
│   │   ├── registrations/      #   seats, waitlist, QR tickets
│   │   ├── attendance/         #   check-in, certificates, PDFs
│   │   └── feedback/           #   ratings, reports
│   │       └── (each: models.py, schemas.py, service.py, router.py)
│   └── web/                    # Jinja2 pages, Tailwind styling, browser JavaScript
├── alembic/                    # database migrations
├── scripts/                    # make_env, set_db, create_admin, seed_demo, doctor
├── docker-compose.yml          # PostgreSQL for development
└── requirements.txt
```

Each service keeps the same layers: **router** (HTTP) → **service** (business rules) → **models** (database). Services call each other only through service functions, so any of them can later be split into its own deployable service.

## API overview

All endpoints are under `/api/v1`. Full details and a try-it-out interface are at `/docs`.

| Area | Examples |
|---|---|
| Auth | `POST /auth/register`, `POST /auth/login`, `GET /users/me` |
| Clubs | `GET /clubs`, `GET /clubs/mine`, `POST /clubs` (admin) |
| Events | `GET /events`, `POST /events`, `POST /events/{id}/publish` |
| Resources | `GET /resources`, `POST /resources/{id}/bookings`, `PATCH /bookings/{id}/status` |
| Registration | `POST /events/{id}/register`, `GET /registrations/me`, `GET /registrations/{id}/ticket` |
| Attendance | `POST /events/{id}/attendance/scan`, `GET /events/{id}/attendance` |
| Certificates | `POST /events/{id}/certificate`, `GET /certificates/{id}/pdf`, `GET /certificates/verify/{code}` |
| Feedback | `POST /events/{id}/feedback`, `GET /events/{id}/feedback/report` |

Authenticate by sending `Authorization: Bearer <token>`, using the token from `/auth/login`.

## Working on the database

After changing a model, create and apply a migration:
```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```
Review the generated file before committing it. Migration files in `alembic/versions/` **are committed**, so everyone gets the same schema.

The first migration enables the PostgreSQL `btree_gist` extension. It powers the rule that stops two bookings of the same venue from overlapping.

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'app'` | Run commands from the project root folder (the one containing `app/`), with the venv active |
| `password authentication failed` | Wrong user or password in `DATABASE_URL`. With Docker the default is `cemf` / `cemf` |
| `Could not parse SQLAlchemy URL` | A special character in the password broke the URL. Run `python -m scripts.set_db`, which encodes it for you |
| `psql` is not recognized | Windows doesn't add PostgreSQL to your PATH. Use pgAdmin to create the database (see Option B), or add `C:\\Program Files\\PostgreSQL\\<version>\\bin` to your PATH |
| `connection refused` on port 5432 | The database isn't running. Start Docker (`docker compose up -d db`) or the PostgreSQL service |
| `docker` is not recognized | Docker isn't installed. Use Option B (local PostgreSQL) instead |
| `relation "users" does not exist` | Tables are missing. Run `alembic upgrade head` |
| `btree_gist` error during migration | The database user needs permission to create extensions. Use a superuser such as `postgres` locally |
| Camera won't start on a phone | Browsers only allow the camera on `https://` or `localhost`. Use the paste box, or deploy with HTTPS |
| Page has no styling | Tailwind and fonts load from the internet. Check your connection |
| Arabic names show as `?` in the PDF certificate | Use **Print** then **Save as PDF** on the certificate page. The on-screen version supports all scripts |

## Known limitations

- Membership **applications** (apply, review, accept, reject) have database tables but no pages yet.
- Clubs, venues and equipment are created through the API (`/docs`); there is no admin screen yet.
- Equipment bookings are available through the API but not on a web page.
- No email or push notifications. Waitlisted students see their ticket when they open **My tickets**.
- The PDF certificate supports Latin characters only (the on-screen certificate supports all scripts).
- Tailwind CSS loads from a CDN; a compiled build is recommended for deployment.
- No automated test suite yet.

## Deploying

Before going live: use a managed PostgreSQL database, set strong random `SECRET_KEY` and `TICKET_SIGNING_KEY` values, serve over **HTTPS** (needed for phone camera scanning), set `CORS_ORIGINS` to your real domain, and do not run `seed_demo`.
