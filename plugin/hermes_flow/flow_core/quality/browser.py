"""真实浏览器验证：启动 Vite preview，用系统 Chrome + CDP 探针逐路由检查。"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

PROBE = Path(__file__).with_name("browser_probe.mjs")


def find_chrome() -> Optional[str]:
    env = os.environ.get("HERMES_CHROME_PATH")
    candidates = [env] if env else []
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                 os.environ.get("LOCALAPPDATA")):
        if not base:
            continue
        candidates.extend([
            os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
        ])
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def detect_routes(project_root: str | Path) -> List[str]:
    root = Path(project_root)
    routes = ["/"]
    for rel in ("src/router/index.js", "src/router/index.ts", "src/router.js", "router/index.js"):
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        found = re.findall(r"path\s*:\s*['\"]([^'\"]+)['\"]", text)
        for item in found:
            if item.startswith("/") and ":" not in item and item not in routes:
                routes.append(item)
        break
    return routes


def _wait_http(url: str, timeout: float) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                return 200 <= resp.status < 500
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    return False


def probe(project_root: str | Path, *, routes: Optional[List[str]] = None,
          out_dir: Optional[str | Path] = None, timeout: int = 180) -> Dict[str, Any]:
    root = Path(project_root).resolve()
    out = Path(out_dir) if out_dir else root / ".quality-browser"
    out.mkdir(parents=True, exist_ok=True)
    chrome = find_chrome()
    node = shutil.which("node")
    if not chrome:
        return {"ran": False, "ok": False, "skipped": True,
                "error": "未找到 Chrome/Edge；设置 HERMES_CHROME_PATH"}
    if not node:
        return {"ran": False, "ok": False, "skipped": True, "error": "node not found"}
    routes = routes or detect_routes(root)
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    pkg_path = root / "package.json"
    pkg = {}
    try:
        pkg = json.loads(pkg_path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        pass
    scripts = pkg.get("scripts") or {}
    if "preview" in scripts:
        cmd = ["npm", "run", "preview", "--", "--host", "127.0.0.1", "--port", str(port)]
    elif "vite" in {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}:
        cmd = ["npx", "vite", "preview", "--host", "127.0.0.1", "--port", str(port)]
    else:
        return {"ran": False, "ok": False, "skipped": True,
                "error": "no preview/vite script; build a preview server first"}
    tmp = out / ".tmp"
    tmp.mkdir(exist_ok=True)
    env = {**os.environ, "TMP": str(tmp), "TEMP": str(tmp), "TMPDIR": str(tmp)}
    argv = cmd
    exe = shutil.which(cmd[0]) or cmd[0]
    if os.name == "nt" and str(exe).lower().endswith((".cmd", ".bat")):
        argv = ["cmd.exe", "/c", *cmd]
    server = subprocess.Popen(argv, cwd=str(root), stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, env=env,
                              start_new_session=(os.name != "nt"))
    try:
        if not _wait_http(base + "/", min(45, timeout)):
            return {"ran": True, "ok": False, "routes": [], "base_url": base,
                    "error": "preview server did not become ready"}
        proc = subprocess.run([node, str(PROBE), base, json.dumps(routes, ensure_ascii=False),
                               str(out), chrome, str(timeout * 1000)],
                              capture_output=True, text=True, timeout=timeout + 30,
                              errors="replace", env=env)
        raw = (proc.stdout or "").strip()
        try:
            data = json.loads(raw.splitlines()[-1]) if raw else {}
        except Exception:  # noqa: BLE001
            data = {"ran": True, "ok": False, "error": "probe output not JSON",
                    "stdout": raw[-2000:], "stderr": (proc.stderr or "")[-2000:]}
        data.setdefault("base_url", base)
        data["routes_requested"] = routes
        evidence = out / f"browser-{int(time.time())}.json"
        evidence.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        data["evidence_path"] = str(evidence)
        return data
    except subprocess.TimeoutExpired:
        return {"ran": True, "ok": False, "routes": [], "base_url": base,
                "error": f"browser probe timeout after {timeout}s"}
    finally:
        # Windows: 只 terminate 会留下 npm/vite 子进程；必须杀整棵树。
        if os.name == "nt":
            try:
                subprocess.run(["taskkill", "/PID", str(server.pid), "/T", "/F"],
                               capture_output=True, timeout=15)
            except Exception:  # noqa: BLE001
                pass
        else:
            try:
                import signal
                os.killpg(os.getpgid(server.pid), signal.SIGTERM)
            except Exception:  # noqa: BLE001
                try:
                    server.terminate()
                except Exception:  # noqa: BLE001
                    pass
        try:
            server.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass
