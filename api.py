"""
API entry point.
Launched via: uvicorn api:app --host 0.0.0.0 --port 8000
"""
from src.routes import app  # noqa: F401
