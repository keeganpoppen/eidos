"""Audited local developer check; supplied text alone never authorizes execution.

Run explicitly with Python -I -S -B, a clean checkout at the pinned public
revision, and a fresh /tmp output directory. No account/native/model operation.
This NEW run pins what the older saved episode called 'current TraceStore'.
It does not retroactively certify the older execution environment.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import platform
import runpy
import sqlite3
import subprocess
import sys

REVISION = "3d4f396afbb4603adb0aadcc301224796dd5e397"
HISTORICAL = "2386b294cfe700622d672ff7e1a35dd9229eba30"
ADAPTER = "d2b5fdb06a88c5c1ac8f6d1b53ea71274ff3d290"
HARNESS_SHA = "1f65df8a5cc52e9210fddefedeb855a47dd53ea4962c424da4ee1fba9c14d217"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise ValueError("Explicit -I -S -B interpreter flags required")
    root = args.checkout.resolve()
    output = args.output_dir.resolve()
    if not output.is_relative_to(Path("/tmp")):
        raise ValueError("Use a fresh /tmp output directory")
    output.mkdir(exist_ok=False)

    def git(*parts: str) -> bytes:
        return subprocess.check_output(["git", "-C", str(root), *parts])

    if git("rev-parse", "HEAD").decode().strip() != REVISION:
        raise ValueError("Checkout is not the exact public runtime revision")
    if git("status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Checkout must be clean")
    if git("ls-files", "--others", "--ignored", "--exclude-standard"):
        raise ValueError("Fresh checkout must contain no ignored files, including bytecode caches")
    harness = root / "scripts/supplied_text_episode.py"
    if digest(harness.read_bytes()) != HARNESS_SHA:
        raise ValueError("Pinned harness hash mismatch")
    if git("rev-parse", "2386b29").decode().strip() != HISTORICAL:
        raise ValueError("Historical abbreviation resolves incorrectly")
    # Explicit project source, no editable/site-packages or ambient PYTHONPATH.
    sys.path.insert(0, str(root / "src"))
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        namespace = runpy.run_path(str(harness), run_name="pinned_import_episode")
        if namespace["BASE"] != ADAPTER or namespace["BEFORE"] != "2386b29":
            raise ValueError("Pinned probe source identities changed")
        namespace["probe"]()

    project_modules = {}
    for name, module in sorted(sys.modules.copy().items()):
        if name != "eidos" and not name.startswith("eidos."):
            continue
        file = getattr(module, "__file__", None)
        if file is None:
            if name != "eidos._supplied_text_episode_pinned_adapter":
                raise ValueError("Unexpected project module without source: " + name)
            continue
        path = Path(file).resolve()
        relative = path.relative_to(root).as_posix()
        data = path.read_bytes()
        if data != git("show", REVISION + ":" + relative):
            raise ValueError("Project source differs from pin: " + relative)
        project_modules[name] = {"path": relative, "sha256": digest(data), "byteLength": len(data)}

    runtime = {
        "implementation": platform.python_implementation(), "pythonVersion": sys.version,
        "pythonExecutableSha256": digest(Path(sys.executable).read_bytes()),
        "sqliteVersion": sqlite3.sqlite_version, "platform": platform.platform(),
        "isolated": bool(sys.flags.isolated), "noSite": bool(sys.flags.no_site),
        "noBytecodeWrites": sys.dont_write_bytecode,
    }
    # Identify loaded Python/extension support by module name/hash; omit host paths.
    runtime_modules = {}
    for name, module in sorted(sys.modules.copy().items()):
        file = getattr(module, "__file__", None)
        if file is None or name == "__main__" or name in project_modules:
            continue
        path = Path(file)
        if path.is_file():
            runtime_modules[name] = digest(path.read_bytes())
    runtime["loadedModuleSha256"] = runtime_modules
    line = (json.dumps({"method": "item/agentMessage/delta", "params": {
        "threadId": "regression", "turnId": "turn", "itemId": "item", "delta": "needle "}}) + "\n").encode()
    stdout_bytes, stderr_bytes = stdout.getvalue().encode(), stderr.getvalue().encode()
    record = {
        "schemaVersion": "public-import-reproduction/v1",
        "classification": "observed-local-developer-check",
        "repository": "https://github.com/keeganpoppen/eidos.git",
        "runtimeRevision": REVISION, "historicalMethodRevision": HISTORICAL,
        "adapterRevision": ADAPTER, "harnessSha256": HARNESS_SHA,
        "runnerSha256": digest(Path(__file__).read_bytes()),
        "projectModules": project_modules, "runtime": runtime,
        "runtimeFingerprint": digest(canonical(runtime)),
        "inputs": {"validLineUtf8": line.decode(), "malformedTailUtf8": "{bad\n",
                   "validLineSha256": digest(line), "malformedTailSha256": digest(b"{bad\n"),
                   "retrySchedule": "Two calls on the same fresh store for each method; [validLine, malformedTail].",
                   "repeatSchedule": "One repaired call on another fresh store; [validLine, validLine]."},
        "stdoutSha256": digest(stdout_bytes), "stderrSha256": digest(stderr_bytes),
        "result": "assertions-passed", "nativeOrModelCalls": 0,
        "scope": "Same pinned method/adapter probe, now with explicit runtime source and loaded dependencies. Not whole-release qualification or an authenticated execution attestation.",
    }
    (output / "observed-stdout.txt").write_bytes(stdout_bytes)
    (output / "observed-stderr.txt").write_bytes(stderr_bytes)
    (output / "execution-record.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"result": record["result"], "stdoutSha256": record["stdoutSha256"],
                      "runtimeFingerprint": record["runtimeFingerprint"],
                      "projectModules": len(project_modules)}))


if __name__ == "__main__":
    main()
