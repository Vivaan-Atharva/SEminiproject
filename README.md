# Change Management Software (CMS)

Software Engineering mini-project, Team 4.

An issue management application: create change requests, assign them to engineers, get them resolved, and track them to closure.

## Team

| SRN | Name | Role in project |
|---|---|---|
| PES1UG24AM071 | Vivaan Atharva | Team lead: Jira, repository, CI, integration |
| PES1UG24AM082 | Dhanush S S | Change requests: create, list, search, edit, due dates |
| PES1UG24AM105 | Gayathri Priya V | Status-flow engine: review, approve/reject, resolve |
| PES1UG24AM106 | Gonu Guntla Hema Kowshik | Assignment, close/reopen, comments, notifications |

Everyone writes tests for their own stories and reviews at least one other member's pull request.

## Documents

| Document | PDF | Word |
|---|---|---|
| Software Requirements Specification (SRS) | [PDF](docs/CMS_SRS.pdf) | [DOCX](docs/CMS_SRS.docx) |
| Software Architecture and Design Specification (SAD) | [PDF](docs/CMS_SAD.pdf) | [DOCX](docs/CMS_SAD.docx) |
| Software Test Plan (STP) | [PDF](docs/CMS_Test_Plan.pdf) | [DOCX](docs/CMS_Test_Plan.docx) |
| UML diagrams | [docs/UML.md](docs/UML.md) | |

## Technology stack

| Part | Choice |
|---|---|
| Language | Python 3.12 (3.10 or newer works) |
| Web framework | Flask, with Jinja templates and Bootstrap 5 |
| Database | SQLite through Flask-SQLAlchemy |
| Login | Flask-Login (added in CMS-2) |
| Tests | pytest |
| CI | GitHub Actions on Ubuntu, Windows and macOS |
| Project tracking | Jira, project key `CMS` |

## Setup

You need **Git** and **Python 3.10 or newer**.

### macOS

```bash
# 1. Install tools (skip any you already have)
xcode-select --install          # installs Git
brew install python@3.12        # or download Python from python.org

# 2. Clone the repository
git clone https://github.com/Vivaan-Atharva/SEminiproject.git
cd SEminiproject

# 3. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Load demo data and run the app
flask --app cms seed
flask --app cms run --debug
```

Open http://127.0.0.1:5000 in your browser. On macOS, if port 5000 is busy (AirPlay Receiver), use `flask --app cms run --debug --port 5001`.

### Windows (PowerShell)

```powershell
# 1. Install tools (skip any you already have)
#    Git:    https://git-scm.com/download/win  (keep the default options)
#    Python: https://www.python.org/downloads/  (tick "Add python.exe to PATH")

# 2. Clone the repository
git clone https://github.com/Vivaan-Atharva/SEminiproject.git
cd SEminiproject

# 3. Create and activate a virtual environment
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
#    If PowerShell says scripts are disabled, run this once and try again:
#    Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#    (In Command Prompt instead of PowerShell, use: .venv\Scripts\activate.bat)

# 4. Install dependencies
pip install -r requirements.txt

# 5. Load demo data and run the app
flask --app cms seed
flask --app cms run --debug
```

Open http://127.0.0.1:5000 in your browser.

### Every time you start work

Activate the virtual environment first (`source .venv/bin/activate` on macOS, `.venv\Scripts\Activate.ps1` on Windows).

## Useful commands

| Command | What it does |
|---|---|
| `flask --app cms run --debug` | Start the app with auto-reload |
| `flask --app cms seed` | Add demo users and change requests (safe to run again) |
| `flask --app cms reset-db` | Delete all local data and recreate the tables |
| `python -m pytest` | Run all tests |

### Demo accounts

All demo accounts use the password `demo1234`. They exist for local development only.

| Email | Role |
|---|---|
| admin@cms.local | Admin |
| reviewer@cms.local | Reviewer |
| engineer1@cms.local, engineer2@cms.local | Engineer |
| engineer3@cms.local | Engineer (inactive, for testing) |
| requester@cms.local, requester2@cms.local | Requester |

The demo data includes change requests in every main status, including several **Approved** ones that can be assigned to engineers.

## Project structure

```text
SEminiproject/
├── cms/                      # The application
│   ├── __init__.py           # create_app(): builds and configures the app
│   ├── config.py             # Settings (override with environment variables)
│   ├── constants.py          # Roles, statuses, priorities, types, components
│   ├── extensions.py         # Shared database object
│   ├── cli.py                # flask --app cms seed / reset-db / init-db
│   ├── seed.py               # Demo users and change requests
│   ├── models/               # Database tables (User, ChangeRequest, ...)
│   ├── services/             # Business rules (workflow, assignment, ...)
│   ├── routes/               # URLs and page handlers (Flask blueprints)
│   ├── templates/            # HTML pages (Jinja + Bootstrap)
│   └── static/               # CSS and other static files
├── tests/                    # pytest tests
├── docs/                     # SRS, SAD, Test Plan, UML diagrams
├── .github/workflows/ci.yml  # Runs the tests on every push and pull request
├── requirements.txt
└── README.md
```

Keep the layers separate: **routes** handle the web request, **services** hold the rules, **models** hold the data. Put each rule in a service so it can be unit-tested without a browser.

## Login, roles and forms (from CMS-2)

**Protect a page by role** with `roles_required`. Signed-out users are sent to the login page, a wrong role gets the 403 page, and Admin passes every role check:

```python
from flask_login import current_user, login_required
from cms.constants import Role
from cms.decorators import roles_required

@bp.route("/change-requests/<int:cr_id>/approve", methods=["POST"])
@roles_required(Role.REVIEWER)
def approve(cr_id):
    ...

@bp.route("/change-requests")
@login_required              # any signed-in user
def list_change_requests():
    ...
```

The decorator only checks the **role**. Checks such as "only the assignee may resolve" or "only the requester may close" go in your service, using `current_user`.

**Every `method="post"` form needs the CSRF field**, or the request is rejected with 400:

```html
<form method="post" action="...">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  ...
</form>
```

**In tests**, sign in with the `login` fixture (CSRF is switched off in tests):

```python
def test_reviewer_can_approve(seeded, client, login):
    login("reviewer@cms.local")
    response = client.post("/change-requests/1/approve")
    ...
```

## Team workflow

1. **Pick your Jira story** on the CMS board and move it to **In Progress**.
2. **Create a branch from the latest `main`**, named after the Jira key:
   ```bash
   git switch main
   git pull origin main
   git switch -c feature/CMS-3-create-change-request
   ```
3. **Work only on your story.** Commit small, meaningful steps with the Jira key:
   ```text
   feat(CMS-3): add change request form and validation
   test(CMS-3): cover missing title and invalid priority
   fix(CMS-3): show error when component is not selected
   ```
4. **Run the tests** before pushing: `python -m pytest`
5. **Push your branch** and open a **pull request** into `main`:
   ```bash
   git push -u origin feature/CMS-3-create-change-request
   ```
   In the pull request, write what you changed, how you tested it, and the Jira key.
6. **Get one review** from another team member and make sure CI is green, then merge.
7. **Move the Jira story to Done** only when its acceptance criteria are met and the code is merged.

Never commit directly to `main`, and never commit passwords, `.env` files or your local `instance/` database.

### If your branch is behind `main`

```bash
git switch main
git pull origin main
git switch feature/CMS-3-create-change-request
git merge main
# fix any conflicts, run the tests, then commit and push
```

## Sprints

| Sprint | Dates | Goal |
|---|---|---|
| Sprint 1 | 31 Oct – 1 Nov 2026 | Skeleton and CI, login with roles, create/list/view change requests, status-flow engine, assign an engineer |
| Sprint 2 | 2 – 7 Nov 2026 | Approve/reject, resolve, close/reopen, comments, editing, dashboard, overdue flags, notifications, integration tests, final documents |
| Presentation | 9 Nov 2026 | Feature freeze on 7 Nov |
