# inkfall

inkfall is a small Flask-based Lorcana card search and browse app.

Live site: https://inkfall.de

GitHub repository: https://github.com/SuppenNudel/inkfall

## Deploy and auto-update

A simple remote deployment workflow is included in the `deploy/` folder.

- Use `deploy/setup.sh` for a clean server setup.
- Use `deploy/update.sh` for a manual restart/update.
- Use the GitHub webhook receiver in `deploy/github-webhook.py` for push-based auto-updates without polling.

For the full production setup and webhook instructions, see `deploy/DEPLOY.md`.

### Recommended production flow

- run the server behind Nginx + Gunicorn
- register a GitHub webhook on the repository
- let the webhook call `deploy/update.sh` on every push
- keep the app on the same remote host and use the repo as the source of truth

## Features

- Search and browse Lorcana cards
- Advanced filtering and syntax helpers
- Support for multiple languages
- Sitemap generation for better indexing

## Future Ideas

- Precon Decks
- Product list
- pull chance

## Run locally

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

## Notes

This project is an independent fan project and is not affiliated with Ravensburger or Lorcana.
