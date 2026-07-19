"""Platform process manager.

Starts and supervises all registered app backends as subprocesses.
Automatically restarts a backend if it crashes (up to MAX_RESTARTS times).
Shuts everything down cleanly when the platform backend exits.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_log = logging.getLogger("process_manager")

# Maximum consecutive restarts before giving up on an app
MAX_RESTARTS = 5
# Seconds to wait between restart attempts
RESTART_DELAY = 3


class FrontendProcess:
    """Manages a Vite dev-server frontend subprocess."""

    def __init__(self, app_id: str, frontend_dir: Path, port: int, extra_env: dict):
        self.app_id = app_id
        self.frontend_dir = frontend_dir
        self.port = port
        self.extra_env = extra_env
        self.process: subprocess.Popen | None = None
        self.stopped = False
        self.started_at: float | None = None

    def _npm(self) -> str:
        """Return npm executable path."""
        # On Windows npm is npm.cmd
        if sys.platform == "win32":
            # Try to find npm.cmd on PATH
            import shutil
            npm = shutil.which("npm")
            return npm or "npm"
        return "npm"

    def start(self) -> bool:
        if not self.frontend_dir.exists():
            _log.error("%s: frontend_dir %s does not exist — skipping",
                       self.app_id, self.frontend_dir)
            return False
        # Check node_modules exists
        if not (self.frontend_dir / "node_modules").exists():
            _log.warning("%s: node_modules missing in %s — run npm install first",
                         self.app_id, self.frontend_dir)

        env = os.environ.copy()
        env.update(self.extra_env)

        # On Windows, npm is a .cmd batch file and must be run via shell=True
        # as a string command, not a list.
        if sys.platform == "win32":
            cmd_str = f'npm run dev -- --port {self.port}'
            use_shell = True
            cmd: list | str = cmd_str
        else:
            cmd = ["npm", "run", "dev", "--", "--port", str(self.port)]
            use_shell = False

        _log.info("Starting frontend %s on port %d", self.app_id, self.port)
        try:
            self.process = subprocess.Popen(
                cmd,
                cwd=str(self.frontend_dir),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=use_shell,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            )
            self.started_at = time.time()
            self.stopped = False
            _log.info("%s frontend started (pid=%d)", self.app_id, self.process.pid)
            return True
        except Exception as e:
            _log.error("Failed to start frontend %s: %s", self.app_id, e)
            return False

    def stop(self) -> None:
        self.stopped = True
        if self.process and self.process.poll() is None:
            _log.info("Stopping frontend %s (pid=%d)", self.app_id, self.process.pid)
            try:
                if sys.platform == "win32":
                    # Kill the entire process tree (cmd.exe → node → vite)
                    subprocess.call(
                        ["taskkill", "/F", "/T", "/PID", str(self.process.pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    self.process.terminate()
                try:
                    self.process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    self.process.kill()
            except Exception as e:
                _log.warning("Error stopping frontend %s: %s", self.app_id, e)

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None


class AppProcess:
    """Manages the lifecycle of a single app backend subprocess."""

    def __init__(self, app_id: str, backend_dir: Path, module: str, port: int):
        self.app_id = app_id
        self.backend_dir = backend_dir
        self.module = module
        self.port = port
        self.process: subprocess.Popen | None = None
        self.restarts = 0
        self.started_at: float | None = None
        self.stopped = False  # True once intentionally stopped
        self._monitor_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Python / uvicorn resolution
    # ------------------------------------------------------------------

    def _python_executable(self) -> str:
        """Return the venv python if present, else the platform's own python."""
        candidates = [
            self.backend_dir / "venv" / "Scripts" / "python.exe",  # Windows
            self.backend_dir / "venv" / "bin" / "python",           # Unix
            self.backend_dir / ".venv" / "Scripts" / "python.exe",
            self.backend_dir / ".venv" / "bin" / "python",
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        return sys.executable  # fall back to platform's python

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Launch uvicorn for this app. Returns True if launched successfully."""
        if not self.backend_dir.exists():
            _log.error("%s: backend_dir %s does not exist — skipping",
                       self.app_id, self.backend_dir)
            return False

        python = self._python_executable()
        cmd = [
            python, "-m", "uvicorn",
            self.module,
            "--host", "0.0.0.0",
            "--port", str(self.port),
        ]

        _log.info("Starting %s on port %d: %s", self.app_id, self.port, " ".join(cmd))

        try:
            # Inherit env so PATH / PYTHONPATH are available
            env = os.environ.copy()

            self.process = subprocess.Popen(
                cmd,
                cwd=str(self.backend_dir),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                # On Windows, create a new process group so we can kill the
                # whole tree without killing the platform process.
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            )
            self.started_at = time.time()
            self.stopped = False
            _log.info("%s started (pid=%d)", self.app_id, self.process.pid)
            return True
        except Exception as e:
            _log.error("Failed to start %s: %s", self.app_id, e)
            return False

    def stop(self) -> None:
        """Terminate the subprocess gracefully."""
        self.stopped = True
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
        if self.process and self.process.poll() is None:
            _log.info("Stopping %s (pid=%d)", self.app_id, self.process.pid)
            try:
                if sys.platform == "win32":
                    # Kill entire process tree (uvicorn spawns child workers)
                    subprocess.call(
                        ["taskkill", "/F", "/T", "/PID", str(self.process.pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    self.process.terminate()
                try:
                    self.process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    _log.warning("%s did not exit in time — killing", self.app_id)
                    self.process.kill()
            except Exception as e:
                _log.warning("Error stopping %s: %s", self.app_id, e)

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    @property
    def status(self) -> str:
        if self.stopped:
            return "stopped"
        if self.process is None:
            return "not_started"
        rc = self.process.poll()
        if rc is None:
            return "running"
        return f"exited({rc})"

    def info(self) -> dict[str, Any]:
        return {
            "id": self.app_id,
            "port": self.port,
            "status": self.status,
            "pid": self.process.pid if self.process else None,
            "restarts": self.restarts,
            "uptime_s": round(time.time() - self.started_at, 1) if self.started_at and self.is_running else None,
        }


# ---------------------------------------------------------------------------
# Global registry
# ---------------------------------------------------------------------------

_processes: dict[str, AppProcess] = {}
_frontends: dict[str, FrontendProcess] = {}


def _repo_root() -> Path:
    """Return the monorepo root (three levels above platform/backend/app/)."""
    return Path(__file__).resolve().parents[3]


def _build_processes() -> tuple[dict[str, AppProcess], dict[str, FrontendProcess]]:
    """Build AppProcess and FrontendProcess instances from the app registry."""
    from .registry import APP_PROCESS_CONFIG
    root = _repo_root()
    procs: dict[str, AppProcess] = {}
    fronts: dict[str, FrontendProcess] = {}
    for cfg in APP_PROCESS_CONFIG:
        backend_dir = root / cfg["backend_dir"]
        procs[cfg["id"]] = AppProcess(
            app_id=cfg["id"],
            backend_dir=backend_dir,
            module=cfg["module"],
            port=cfg["port"],
        )
        frontend_dir = root / cfg["frontend_dir"]
        fronts[cfg["id"]] = FrontendProcess(
            app_id=cfg["id"],
            frontend_dir=frontend_dir,
            port=cfg["frontend_port"],
            extra_env=cfg.get("frontend_env", {}),
        )
    return procs, fronts


# ---------------------------------------------------------------------------
# Monitor task — restarts crashed processes
# ---------------------------------------------------------------------------

async def _monitor(proc: AppProcess) -> None:
    """Async task: watches a process and restarts it if it dies unexpectedly."""
    while not proc.stopped:
        await asyncio.sleep(2)
        if proc.stopped:
            break
        if proc.process and proc.process.poll() is not None:
            rc = proc.process.poll()
            if proc.stopped:
                break
            if proc.restarts >= MAX_RESTARTS:
                _log.error("%s crashed (rc=%d) and exceeded max restarts (%d) — giving up",
                           proc.app_id, rc, MAX_RESTARTS)
                break
            proc.restarts += 1
            _log.warning("%s crashed (rc=%d) — restarting in %ds (attempt %d/%d)",
                         proc.app_id, rc, RESTART_DELAY, proc.restarts, MAX_RESTARTS)
            await asyncio.sleep(RESTART_DELAY)
            proc.start()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def start_all() -> None:
    """Start all app backend and frontend subprocesses."""
    global _processes, _frontends
    _processes, _frontends = _build_processes()

    # Start backends first
    for proc in _processes.values():
        ok = proc.start()
        if ok:
            proc._monitor_task = asyncio.create_task(_monitor(proc))

    # Wait briefly for backends to bind their ports before starting frontends
    await asyncio.sleep(3)

    # Start frontends
    for front in _frontends.values():
        front.start()


def stop_all() -> None:
    """Stop all running app backend and frontend subprocesses."""
    for front in _frontends.values():
        front.stop()
    for proc in _processes.values():
        proc.stop()
    _log.info("All app processes stopped.")


def get_status() -> list[dict]:
    """Return status info for all managed backend processes."""
    result = []
    for p in _processes.values():
        info = p.info()
        # Attach frontend status
        front = _frontends.get(p.app_id)
        if front:
            info["frontend_status"] = "running" if front.is_running else "stopped"
            info["frontend_port"] = front.port
        result.append(info)
    return result


def get_process(app_id: str) -> AppProcess | None:
    return _processes.get(app_id)


def get_frontend(app_id: str) -> FrontendProcess | None:
    return _frontends.get(app_id)
