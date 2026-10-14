"""Exercise real managed preparation and private publication with authored stdio.

This is an explicit synthetic runtime, without a native process, DNS or network.
Seed/serve: --db /tmp/managed-demo.db --output /tmp/managed-demo.json --serve.
Release only an authored pending login by touching its per-launch release-login.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import threading
import time
import tomllib
from unittest.mock import patch

from eidos.api import EidosAPI
from eidos.native_managed import ManagedExecutionProfile
from eidos.native_managed_contract import MANAGED_VERSION, ManagedLaunchError, ManagedPolicy
from eidos.private_investigation import PrivateInvestigationWorker
import eidos.serve as server_module

FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/managed_attempt_server.py"


class AuthoredRuntime:
    """Test seam labels itself synthetic; none of these fields establish containment."""

    def __init__(self, directory: Path, cwd, *, config_toml, catalog_bytes, policy, binary="unused", cancelled=None):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "config.json").write_text(json.dumps(tomllib.loads(config_toml)))
        self.command = (sys.executable, "-I", "-S", str(FIXTURE), str(directory))
        self.env = {}
        self.policy, self.cancelled = policy, cancelled
        self._lock, self._state, self._abort = threading.RLock(), "prepared", None
        self._started = time.monotonic()
        self._turn_deadline = None
        self.evidence = {"version": MANAGED_VERSION, "transport": "authored-local", "classification": "synthetic",
            "binarySha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
            "configSha256": hashlib.sha256(config_toml.encode()).hexdigest(),
            "catalogSha256": hashlib.sha256(catalog_bytes).hexdigest(), "limits": policy.as_dict()}

    def require_contained_startup(self):
        with self._lock:
            if self._state != "prepared" or (self.cancelled is not None and self.cancelled.is_set()):
                raise ManagedLaunchError("Authored runtime is closed.")
            self._state = "issuer-only"

    def bind_abort(self, callback):
        with self._lock:
            if self._abort is not None:
                raise ManagedLaunchError("Authored abort already bound.")
            self._abort = callback

    def remaining_preparation(self):
        return self._started + self.policy.preparation_seconds - time.monotonic()

    def remaining_turn(self):
        return min(self._turn_deadline or 0, self._started + self.policy.lifetime_seconds) - time.monotonic()

    def activate_provider(self):
        with self._lock:
            if self._state != "issuer-only" or (self.cancelled is not None and self.cancelled.is_set()):
                raise ManagedLaunchError("Authored issuer did not close in order.")
            self._state = "provider-only"
            self._turn_deadline = time.monotonic() + self.policy.turn_seconds

    def close(self, reason="closed", *, wait=True):
        with self._lock:
            self._state = "closed"
            callback = self._abort
        if callback is not None:
            callback()
        return {"allWorkersJoined": True, "errors": [], "reason": reason, "classification": "synthetic"}


def authored_profile(root: Path, *, policy=None, release=False, mode="complete"):
    def factory(cwd, **kwargs):
        runtime = AuthoredRuntime(root / Path(cwd).name, cwd, **kwargs)
        (runtime.directory / "mode").write_text(mode)
        if release:
            (runtime.directory / "release-login").touch()
        return runtime
    return ManagedExecutionProfile(policy=policy or ManagedPolicy(), runtime_factory=factory)


def make_api(trace, *, codex=None):
    api = EidosAPI(trace)
    api.investigation_worker.close()
    api.investigation_worker.close_evidence()
    profile = authored_profile(Path(str(trace.path) + ".fixture"))
    api.investigation_worker = PrivateInvestigationWorker(trace, managed_profile=profile)
    capabilities = api.investigation_capabilities()
    capabilities["nativeExecution"] = {"available": True, "mode": "synthetic",
        "reason": "Authored managed preparation fixture; no native, account or model call."}
    api.investigation_capabilities = lambda: deepcopy(capabilities)
    return api


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("owned_demo_seed", Path(__file__).with_name("owned_attempt_demo.py"))
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    value = seed.inspect(args.db) if args.resume else seed.seed(args.db)
    value["classification"] = "authored-managed-preparation-fixture"
    if args.output:
        args.output.write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps(value, indent=2), flush=True)
    if args.serve:
        with patch.object(server_module, "EidosAPI", make_api):
            server_module.serve(args.db, port=args.port)


if __name__ == "__main__":
    main()
