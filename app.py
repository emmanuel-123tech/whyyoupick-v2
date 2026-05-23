"""Vercel FastAPI entrypoint.

Vercel's Python runtime auto-detects FastAPI apps from app.py/index.py/server.py.
The actual application lives in main.py so local Render/uvicorn usage keeps working.
"""

from main import app
