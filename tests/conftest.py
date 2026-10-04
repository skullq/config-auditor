import os
import sys
import time
import subprocess
import pytest
import httpx

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")

@pytest.fixture(scope="session", autouse=True)
def ensure_server_running():
    """테스트 실행 전 FastAPI 서버가 실행 중인지 확인하고, 안 떠 있다면 백그라운드로 실행."""
    server_process = None
    try:
        r = httpx.get(f"{BASE_URL}/api/golden/pending-changes", timeout=1.0)
        if r.status_code in (200, 404):
            # 서버가 이미 실행 중
            yield
            return
    except Exception:
        pass

    # 서버가 안 떠 있으므로 subprocess로 실행
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(os.path.dirname(__file__), "..", "webapp")
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "webapp.main:app", "--port", "8000", "--host", "127.0.0.1"],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    # 헬스체크 폴링
    started = False
    for _ in range(30):
        try:
            r = httpx.get(f"{BASE_URL}/api/golden/pending-changes", timeout=0.5)
            if r.status_code in (200, 404):
                started = True
                break
        except Exception:
            time.sleep(0.3)

    if not started:
        if server_process:
            server_process.terminate()
        raise RuntimeError("FastAPI server failed to start within timeout.")

    try:
        yield
    finally:
        if server_process:
            server_process.terminate()
            server_process.wait(timeout=5)
