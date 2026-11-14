# The Roll

A Django directory for lawyers and clients, with profiles, consultation bookings, wallet transactions, post-consultation reviews and complaints, and community experiences.

## Project layout

```text
main/                    Django project settings and root URLs
directory/               Main app: data models, forms, admin, and app URLs
directory/views/
  accounts.py             Sign-up, client profile, and wallet actions
  bookings.py             Availability, booking, cancellation, payment, review, and complaint actions
  directory.py            Lawyer directory, profiles, and shared availability helpers
  experiences.py          Experience posts, comments, and likes
directory/migrations/     Database schema history; keep these files
templates/
  base.html               Shared page layout
  registration/           Django login templates
  directory/              App pages
static/
  css/style.css           Site styles
  js/lawyer-calendar.js   Lawyer availability calendar and booking confirmation
media/                    Uploaded profile photos
manage.py                 Django management commands
requirements.txt          Python dependencies
db.sqlite3                Local development database
```

## Run locally

Activate the project virtual environment, then run:

```powershell
python manage.py migrate
python manage.py runserver
```

Open `http://127.0.0.1:8000/`. To administer the local database, create an admin account with `python manage.py createsuperuser`.

The wallet and escrow behavior is currently handled inside this Django app; it does not connect to an external payment provider.
