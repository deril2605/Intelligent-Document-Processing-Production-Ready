#!/usr/bin/env python3
"""
One-command startup script for your Document Processing system.

Starts:
- Docker infra: postgres + redis
- Celery worker (optional but recommended)
- FastAPI API (run_api.py)

Assumptions:
- docker compose services are named: postgres, redis
- API exposes: GET /api/v1/health
- run_api.py exists in repo root
"""

from __future__ import annotations

import sys
import time
import subprocess
import platform
import signal
import logging
from pathlib import Path
from typing import List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class DocumentPipelineStarter:
    def __init__(self) -> None:
        self.project_root = Path(__file__).parent.resolve()
        self.is_windows = platform.system().lower().startswith("win")
        self.docker_compose_cmd = self._get_docker_compose_cmd()
        self.processes: List[subprocess.Popen] = []
        self.api_already_running = False

    def _get_docker_compose_cmd(self) -> List[str]:
        """
        Prefer: docker compose
        Fallback: docker-compose
        Returns a list command prefix, e.g. ["docker", "compose"] or ["docker-compose"].
        """
        try:
            subprocess.run(["docker", "compose", "version"], capture_output=True, check=True)
            return ["docker", "compose"]
        except Exception:
            pass

        try:
            subprocess.run(["docker-compose", "version"], capture_output=True, check=True)
            return ["docker-compose"]
        except Exception:
            raise RuntimeError("Neither 'docker compose' nor 'docker-compose' found. Install Docker Desktop.")

    def check_prerequisites(self) -> bool:
        try:
            subprocess.run(["docker", "--version"], capture_output=True, check=True)
            logger.info("Docker is available")

            if sys.version_info < (3, 10):
                logger.warning("Recommended Python 3.10+. You are on %s", sys.version.split()[0])
            else:
                logger.info("Python %s is available", sys.version.split()[0])

            if not (self.project_root / "run_api.py").exists():
                logger.error("run_api.py not found in %s", self.project_root)
                return False

            return True
        except Exception as e:
            logger.error("Prerequisite check failed: %s", e)
            return False

    def start_infrastructure(self) -> bool:
        """
        Start postgres + redis only.
        """
        logger.info("Starting infrastructure services (postgres, redis)...")
        try:
            cmd = self.docker_compose_cmd + ["up", "-d", "postgres", "redis"]
            result = subprocess.run(cmd, cwd=self.project_root, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error("Failed to start infra:\n%s", result.stderr)
                return False

            logger.info("Infrastructure started ✅")
            return True
        except Exception as e:
            logger.error("Failed to start infrastructure: %s", e)
            return False

    def wait_for_services(self, max_wait: int = 120) -> bool:
        """
        Minimal readiness: containers are running.
        (We don't do deep DB/Redis probes here; API healthcheck will catch issues later.)
        """
        logger.info("Waiting for docker services to be running...")
        services = ["postgres", "redis"]
        start = time.time()

        while time.time() - start < max_wait:
            ok = False

            # Preferred path: ask compose for currently running services.
            out = subprocess.run(
                self.docker_compose_cmd + ["ps", "--services", "--status", "running"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
            )
            if out.returncode == 0:
                running_services = {line.strip() for line in out.stdout.splitlines() if line.strip()}
                ok = all(svc in running_services for svc in services)
            else:
                # Fallback for compose variants that do not support --status.
                ok = True
                for svc in services:
                    svc_out = subprocess.run(
                        self.docker_compose_cmd + ["ps", svc],
                        cwd=self.project_root,
                        capture_output=True,
                        text=True,
                    )
                    if svc_out.returncode != 0 or "up" not in svc_out.stdout.lower():
                        ok = False
                        break

            if ok:
                logger.info("Core services are running")
                return True

            time.sleep(3)
            elapsed = int(time.time() - start)
            logger.info("Waiting... (%ss)", elapsed)

        logger.warning("Services may still be initializing; continuing anyway.")
        return True

    def start_celery_worker(self, concurrency: int = 2) -> bool:
        """
        Start Celery worker:
          python -m celery -A src.celery_app worker --loglevel=info --concurrency=2
        """
        logger.info("Starting Celery worker...")
        try:
            # Windows + prefork is unstable for Celery/billiard in local dev.
            pool = "solo" if self.is_windows else "prefork"
            effective_concurrency = 1 if pool == "solo" else concurrency

            cmd = [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "src.celery_app",
                "worker",
                "--loglevel=info",
                f"--concurrency={effective_concurrency}",
                f"--pool={pool}",
            ]

            # Show logs in terminal (helpful for debugging).
            process = subprocess.Popen(cmd, cwd=self.project_root)
            self.processes.append(process)

            time.sleep(2)
            if process.poll() is None:
                logger.info("Celery worker started (PID: %s, pool=%s)", process.pid, pool)
                return True

            logger.error("Celery worker exited immediately (code=%s)", process.returncode)
            return False

        except Exception as e:
            logger.error("Failed to start Celery worker: %s", e)
            return False

    def start_api(self, base_url: str) -> bool:
        """
        Start FastAPI service using your run_api.py
        """
        logger.info("Starting API via run_api.py ...")
        try:
            # If API is already reachable, reuse it instead of starting a second process.
            try:
                import requests
                r = requests.get(f"{base_url}/api/v1/health", timeout=2)
                if r.status_code == 200:
                    logger.info("API already running at %s; reusing existing process", base_url)
                    self.api_already_running = True
                    return True
            except Exception:
                pass

            cmd = [sys.executable, "run_api.py"]

            process = subprocess.Popen(cmd, cwd=self.project_root)
            self.processes.append(process)

            time.sleep(2)
            if process.poll() is None:
                logger.info("API process started ✅ (PID: %s)", process.pid)
                return True

            logger.error("API exited immediately (code=%s)", process.returncode)
            return False

        except Exception as e:
            logger.error("Failed to start API: %s", e)
            return False

    def wait_for_api_health(self, base_url: str, max_wait: int = 120) -> bool:
        """
        Wait until GET {base_url}/api/v1/health returns 200.
        """
        logger.info("Waiting for API healthcheck at %s/api/v1/health ...", base_url)
        start = time.time()

        try:
            import requests  # local dependency
        except Exception:
            logger.error("requests not installed. Add it to deps: pip install requests")
            return False

        while time.time() - start < max_wait:
            try:
                r = requests.get(f"{base_url}/api/v1/health", timeout=3)
                if r.status_code == 200:
                    logger.info("API healthcheck OK ✅")
                    return True
            except Exception:
                pass

            time.sleep(2)
            elapsed = int(time.time() - start)
            logger.info("Waiting for API... (%ss)", elapsed)

        logger.error("API did not become healthy in time ❌")
        return False

    def cleanup(self) -> None:
        logger.info("Stopping started processes...")
        for p in reversed(self.processes):
            try:
                if p.poll() is None:
                    p.terminate()
                    p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                p.kill()
            except Exception:
                pass
        self.processes.clear()

    def run(self) -> bool:
        from src.config import AppConfig  # uses your file-based config (no env vars)

        cfg = AppConfig()
        base_url = f"http://{cfg.api.host}:{cfg.api.port}"

        logger.info("Starting Document Pipeline System...")
        logger.info("Project root: %s", self.project_root)

        if not self.check_prerequisites():
            return False

        if not self.start_infrastructure():
            return False

        self.wait_for_services()

        # Celery may be optional early on; keep it on by default.
        celery_ok = self.start_celery_worker(concurrency=2)
        if not celery_ok:
            logger.warning("Celery failed to start. Continuing (API can still run).")

        if not self.start_api(base_url=base_url):
            return False

        if not self.wait_for_api_health(base_url=base_url):
            return False

        logger.info("✅ System is ready!")
        logger.info("Web UI: %s/", base_url)
        logger.info("API Docs: %s/docs", base_url)
        logger.info("Health: %s/api/v1/health", base_url)
        logger.info("Press Ctrl+C to stop.")

        try:
            while True:
                time.sleep(1)
                # If API dies, fail fast
                for p in self.processes:
                    if p.poll() is not None:
                        logger.error("A process stopped unexpectedly (PID=%s, code=%s)", p.pid, p.returncode)
                        return False
        except KeyboardInterrupt:
            logger.info("Stopping...")
            return True
        finally:
            self.cleanup()


def main() -> None:
    starter = DocumentPipelineStarter()

    def handle_signal(signum, frame):
        logger.info("Signal received (%s). Shutting down...", signum)
        starter.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_signal)

    ok = starter.run()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
