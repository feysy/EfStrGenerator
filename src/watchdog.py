# watchdog.py
# Spawned as a detached process by gui.main() on Windows.
# Watches the main app PID and runs "docker compose down" when it exits.
import sys
import os
import subprocess
import ctypes
import time
import logging

logging.basicConfig(
    filename=os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchdog.log"),
    level=logging.DEBUG,
    format="%(asctime)s %(message)s",
)

SYNCHRONIZE = 0x00100000
INFINITE = 0xFFFFFFFF
CREATE_NO_WINDOW = 0x08000000

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000


def get_pythonw() -> str:
    """Returns pythonw.exe path if available (suppresses console window), else python.exe."""
    exe_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(exe_dir, "pythonw.exe")
    return pythonw if os.path.exists(pythonw) else sys.executable


def spawn_watchdog() -> None:
    """Spawns a detached watchdog process that tears down Docker when the app exits."""
    print("spawning watchdog with pid:", os.getpid())
    subprocess.Popen(
        [get_pythonw(), "src/watchdog.py", str(os.getpid()), "./"],
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


def _wait_for_pid_exit(pid: int) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        return  # Process already gone — clean up immediately
    logging.info(f"watchdog started, watching PID {pid}")
    kernel32.WaitForSingleObject(handle, INFINITE)
    kernel32.CloseHandle(handle)


if __name__ == "__main__":
    main_pid = int(sys.argv[1])
    compose_dir = sys.argv[2]

    _wait_for_pid_exit(main_pid)
    print(f"[watchdog] PID {main_pid} exited, running docker compose down")
    try:
        subprocess.run(
            ["docker", "compose", "down"],
            cwd=compose_dir,
            timeout=30,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception as e:
        print(e)

    time.sleep(3)
