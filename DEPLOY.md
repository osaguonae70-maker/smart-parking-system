# Deploy Guide

This project is ready to run on `Render` with a managed `PostgreSQL` database.

## 1. Install Git

If `git` is not available in PowerShell, install Git for Windows:

- Download: https://git-scm.com/download/win
- After installation, close and reopen your terminal

Check that Git works:

```powershell
git --version
where.exe git
```

## 2. Push Project to GitHub

Open PowerShell in `c:\parking system` and run:

```powershell
git init
git remote remove origin
git remote add origin https://github.com/osaguonae70-maker/smart-parking-system.git
git add .
git commit -m "Prepare app for Render and PostgreSQL"
git branch -M main
git push -u origin main
```

If `origin` does not exist yet, skip this line:

```powershell
git remote remove origin
```

If the GitHub repository already contains files, run:

```powershell
git pull origin main --allow-unrelated-histories
```

Then push again:

```powershell
git push -u origin main
```

## 3. Deploy on Render

1. Sign in to https://render.com/
2. Click `New +`
3. Choose `Blueprint`
4. Select the GitHub repository:
   `osaguonae70-maker/smart-parking-system`
5. Render will read `render.yaml`
6. Confirm creation of:
   - one web service
   - one PostgreSQL database
7. Click `Apply`

## 4. Render Settings Used

This project already includes:

- `render.yaml`
- `wsgi.py`
- `requirements.txt`
- PostgreSQL-ready database config in `app.py`

Render will set:

- `DATABASE_URL`
- `SECRET_KEY`
- `FLASK_DEBUG=0`
- `ADMIN_LOCAL_ONLY=0`

## 5. Local Development

For local development, the project uses:

- `.env`
- local `SQLite`

Run locally with:

```powershell
python app.py
```

## 6. After Deployment

- Open the Render app URL
- Visit `/portal` for the user portal
- Visit `/admin` for the admin dashboard
- Confirm the database is connected and the parking slots initialize correctly
