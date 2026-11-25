# Platforms that want a start command instead of a Dockerfile (Railway via
# Nixpacks, Render's native Python runtime, Heroku-style hosts). The image path
# in Dockerfile.api / render.yaml / railway.json is the recommended one; this is
# the no-Docker equivalent and serves the same single origin.
web: cd apps/api && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
