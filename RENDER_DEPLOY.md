# Deploying to Render

1. Push your code to GitHub.
2. Go to https://render.com and create a new Web Service.
3. Connect your GitHub repo and select your branch.
4. Set the build command to `pip install -r requirements.txt`.
5. Set the start command to `gunicorn app:app`.
6. Add environment variables:
   - `FLASK_SECRET_KEY` (your secret key)
   - `MAIL_USERNAME`, `MAIL_PASSWORD`, etc.
7. SQLite is ephemeral on Render. For production, use PostgreSQL or another managed DB. For demo/testing, SQLite works but data will reset on redeploy.
8. Click 'Create' and wait for deployment.

## Notes
- If you use SQLite, your database will be wiped on every redeploy. For persistent data, use PostgreSQL.
- Update your app to read secrets from environment variables instead of hardcoding them.
