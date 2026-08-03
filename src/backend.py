import os
import subprocess
import time
import traceback
from typing import Callable

from src.api_client import ping_api


def initialize_docker_backend(status_callback: Callable[[str], None]) -> None:
    """
    Checks if the FastAPI backend is reachable. If not, attempts to start it
    via Docker Compose. Calls status_callback with user-facing status strings.
    """
    status_callback("Checking backend API server status...")

    if ping_api():
        status_callback("Backend API connected and ready (Windows Mode).")
        return

    status_callback("Backend API offline. Starting/building Docker containers...")
    try:
        subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )

        for cmd in [["docker", "compose", "up", "-d"], ["docker-compose", "up", "-d"]]:
            try:
                creationflags = 0
                stdout_target = subprocess.DEVNULL
                stderr_target = subprocess.DEVNULL
                if os.name == "nt":
                    # Open a new console so the user can see build/pull logs
                    creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)
                    stdout_target = None
                    stderr_target = None

                subprocess.run(
                    cmd,
                    check=True,
                    stdout=stdout_target,
                    stderr=stderr_target,
                    creationflags=creationflags,
                )

                # Wait up to 10 s for the API to become reachable
                for _ in range(10):
                    if ping_api():
                        status_callback("Backend API connected and ready (Windows Mode).")
                        return
                    time.sleep(1.0)

            except Exception:
                traceback.print_exc()
                continue

    except Exception:
        traceback.print_exc()

    status_callback(
        "⚠️ Backend API offline. Please ensure Docker is running and run 'docker compose up -d'."
    )
