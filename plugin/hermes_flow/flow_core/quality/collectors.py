"""真实质量采集器：vite build / vue-tsc / 可选 Playwright。

设计原则：采集器只读项目并执行构建/检查命令，不修改源码；失败时保留日志尾部作为证据。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def _run(cmd: List[str], cwd: Path, timeout: int = 300,
         env_extra: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    started = time.time()
    argv = list(cmd)
    exe = shutil.which(argv[0]) or argv[0]
    # Windows 的 npm/npx 是 .cmd，CreateProcess 不能直接执行；统一走 cmd /c
    if os.name == "nt" and str(exe).lower().endswith((".cmd", ".bat")):
        argv = ["cmd.exe", "/c", *argv]
    env = {**os.environ, **(env_extra or {})}
    try:
        proc = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True,
                              timeout=timeout, errors="replace", env=env)
        out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        return {"ran": True, "ok": proc.returncode == 0, "command": " ".join(cmd),
                "exit_code": proc.returncode, "duration": round(time.time() - started, 2),
                "log_tail": out[-6000:], "error": ""}
    except FileNotFoundError as exc:
        return {"ran": False, "ok": False, "command": " ".join(cmd),
                "duration": round(time.time() - started, 2), "log_tail": "",
                "error": f"command not found: {exc}"}
    except subprocess.TimeoutExpired as exc:
        return {"ran": True, "ok": False, "command": " ".join(cmd),
                "duration": round(time.time() - started, 2),
                "log_tail": ((exc.stdout or "") if isinstance(exc.stdout, str) else "")[-3000:],
                "error": f"timeout after {timeout}s"}


def detect_commands(project_root: str | Path) -> Dict[str, Optional[List[str]]]:
    root = Path(project_root)
    pkg_path = root / "package.json"
    pkg: Dict[str, Any] = {}
    if pkg_path.is_file():
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8-sig"))
        except Exception:  # noqa: BLE001
            pkg = {}
    scripts = pkg.get("scripts") or {}
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
    build = None
    if "build" in scripts:
        build = ["npm", "run", "build"]
    elif "vite" in deps:
        build = ["npx", "vite", "build"]
    typecheck = None
    if "type-check" in scripts:
        typecheck = ["npm", "run", "type-check"]
    elif "typecheck" in scripts:
        typecheck = ["npm", "run", "typecheck"]
    elif (root / "tsconfig.json").is_file():
        typecheck = ["npx", "vue-tsc", "--noEmit"]
    test = ["npm", "test"] if "test" in scripts else None
    return {"build": build, "typecheck": typecheck, "test": test}


def collect(project_root: str | Path, *, build: bool = True, typecheck: bool = True,
            tests: bool = False, browser: bool = False, timeout: int = 300,
            log_dir: Optional[str | Path] = None,
            routes: Optional[List[str]] = None) -> Dict[str, Any]:
    root = Path(project_root).resolve()
    commands = detect_commands(root)
    # Windows esbuild 会清理系统 %TEMP% 下的临时文件；某些沙箱/ACL 环境会
    # 拒绝删除，导致 build 假失败。把 TMP/TEMP 固定到项目内可写目录。
    tmp_dir = root / ".quality-tmp"
    try:
        tmp_dir.mkdir(exist_ok=True)
    except OSError:
        tmp_dir = Path(tempfile.mkdtemp(dir=str(root)))
    env_extra = {"TMP": str(tmp_dir), "TEMP": str(tmp_dir), "TMPDIR": str(tmp_dir)}
    results: Dict[str, Any] = {
        "ok": True, "project_root": str(root), "commands": commands,
        "build": None, "typecheck": None, "tests": None, "browser": None,
        "started_at": time.time(),
    }
    if build:
        cmd = commands.get("build")
        if cmd is None:
            results["build"] = {"ran": False, "ok": False, "error": "no build script / vite dependency"}
        else:
            results["build"] = _run(cmd, root, timeout, env_extra)
    if typecheck:
        cmd = commands.get("typecheck")
        if cmd is None:
            results["typecheck"] = {"ran": False, "ok": True, "skipped": True,
                                    "error": "no typecheck script / tsconfig"}
        else:
            results["typecheck"] = _run(cmd, root, timeout, env_extra)
    if tests:
        cmd = commands.get("test")
        results["tests"] = _run(cmd, root, timeout, env_extra) if cmd else {
            "ran": False, "ok": True, "skipped": True, "error": "no test script"}
    if browser:
        from .browser import probe
        results["browser"] = probe(root, routes=routes,
                                   out_dir=(Path(log_dir) if log_dir else root / ".quality-browser"),
                                   timeout=timeout)
    checks = [results[k] for k in ("build", "typecheck", "tests", "browser")
              if results[k] and results[k].get("ran") and not results[k].get("skipped")]
    results["ok"] = all(c.get("ok") for c in checks) if checks else False
    results["duration"] = round(time.time() - results["started_at"], 2)
    if log_dir:
        try:
            out = Path(log_dir)
            out.mkdir(parents=True, exist_ok=True)
            path = out / f"quality-{int(results['started_at'])}.json"
            path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            results["evidence_path"] = str(path)
        except Exception:  # noqa: BLE001
            pass
    return results


def collect_for_gate(project_root: str | Path, *, timeout: int = 300,
                     log_dir: Optional[str | Path] = None) -> Dict[str, Any]:
    """返回可直接喂给 ``aggregate_gate`` 的字段。"""
    raw = collect(project_root, build=True, typecheck=True, browser=False,
                  timeout=timeout, log_dir=log_dir)
    build = raw.get("build") or {}
    type_ = raw.get("typecheck") or {}
    build_ok = bool(build.get("ok"))
    type_ok = bool(type_.get("ok") or type_.get("skipped"))
    return {
        "raw": raw,
        "full_build_ok": build_ok,
        "typecheck_ok": type_ok,
        "browser_ok": False,
        "browser_checked": False,
        "signals": {
            "ast": 100.0 if build_ok else 0.0,
            "build": 100.0 if build_ok else 0.0,
            "types": 100.0 if type_ok else 0.0,
            "browser": 0.0,
            "behavior": 0.0,
        },
    }
