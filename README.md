# TaskManager Web App

A task management web application built with Python `http.server`, PostgreSQL/SQLite, and vanilla JavaScript.

## Features

- User authentication with signup and login
- Role-based access for Admin and Member accounts
- Project management
- Task creation and assignment
- Task status tracking: Todo, In Progress, Done
- Team collaboration with project members
- Responsive UI for desktop and mobile
- Railway deployment support

## Tech Stack

- Backend: Python
- Database: PostgreSQL on Railway, SQLite fallback locally
- Frontend: HTML, CSS, JavaScript
- Deployment: Railway
- Version Control: Git and GitHub

## Project Structure

```text
TaskManager/
  backend/
    config.py
    db.py
    handlers.py
    security.py
    validation.py
  static/
    index.html
    styles.css
    app.js
  app.py
  requirements.txt
  Procfile
  README.md
```

## Local Setup

```bash
cd TaskManager
python app.py
```

Open:

```text
http://localhost:8000
```

## Railway

Railway can deploy this app directly from GitHub. The `Procfile` start command is:

```bash
web: python app.py
```

## Database

The app uses PostgreSQL automatically when `DATABASE_URL` is set. On Railway, add a PostgreSQL database service to the same project, then attach its `DATABASE_URL` variable to the web service.

Without `DATABASE_URL`, the app falls back to SQLite for local development.
