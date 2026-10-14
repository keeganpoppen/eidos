"""Packaged resources and authored local process lifecycle; never launch Codex."""
from dataclasses import replace
import hashlib
from importlib import resources
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

import pytest

from eidos import native_containment as module
from eidos.codex import AppServerClient
from eidos.native_managed_contract import ManagedLaunchError, ManagedPolicy


def wait_until(predicate, seconds=2):
    deadline = time.monotonic()+seconds
    while not predicate():
        if time.monotonic() >= deadline: raise AssertionError("local lifecycle condition did not finish")
        time.sleep(.005)


@pytest.fixture
def runtime(monkeypatch, tmp_path, request):
    if platform.system() != "Linux" or platform.machine() != "aarch64":
        pytest.skip("reviewed containment setup is Linux/aarch64")
    # A local Python file snapshot stands in for the pinned binary; no command
    # from this resource is executed and no DNS resolver is allowed to run.
    monkeypatch.setattr(module, "MANAGED_BINARY_SHA256", hashlib.sha256(Path("/usr/bin/python3").read_bytes()).hexdigest())
    roots = tmp_path/"public-roots.pem"
    roots.write_text("-----BEGIN CERTIFICATE-----\nAUTHORED_FIXTURE\n-----END CERTIFICATE-----\n")
    monkeypatch.setattr(module, "PUBLIC_ROOTS", roots)
    if getattr(request, "param", False):
        from eidos.native_managed import managed_config, managed_catalog
        config, catalog = managed_config(), managed_catalog()
    else:
        config, catalog = 'model="fixture"\n', b'{}'
    with tempfile.TemporaryDirectory(prefix="nema-investigation-") as cwd:
        value = module.ContainedRuntime(cwd, config_toml=config, catalog_bytes=catalog,
                                       policy=ManagedPolicy(), binary="/usr/bin/python3")
        yield value
        report = value.close()
        assert report["allWorkersJoined"] and report["errors"] == [] and report["stateRemoved"], report


def test_snapshot_paths_and_explicit_environment(runtime):
    assert runtime.env == {}
    with pytest.raises(TypeError): runtime.env["HOME"] = "/owner"
    command = list(runtime.command)
    assert command[0] == "/usr/bin/bwrap" and "--unshare-all" in command and "--disable-userns" in command
    assert "/etc/ssl/certs/ca-certificates.crt" in command and "--clearenv" in command
    assert str(runtime.cwd) in command
    assert runtime.evidence["transport"] == "fixed-live-destinations"
    changed = runtime.evidence; changed["limits"]["max_active"] = 99
    assert runtime.evidence["limits"]["max_active"] == 2
    assert not (runtime._root/"broker.sock").exists()  # construction performs no DNS/startup
    assert runtime._processes == set()


def test_startup_consumed_once_with_only_authored_resolution(runtime, monkeypatch):
    calls = []
    def resolve(command, *, seconds):
        calls.append(command)
        return b'[[2,"8.8.8.8"]]'
    monkeypatch.setattr(runtime, "_run", resolve)
    runtime.require_contained_startup()
    assert len(calls) == 2 and all(command[-2] == "resolve" for command in calls)
    assert runtime._broker.snapshot()["phase"] == "issuer-only"
    assert runtime.remaining_preparation() > 0
    runtime.activate_provider()
    assert runtime.remaining_turn() > 0
    with pytest.raises(ManagedLaunchError, match="consumed"):
        runtime.require_contained_startup()
    assert runtime._closed.is_set()


@pytest.mark.parametrize("asset", ["config.toml", "codex", "public-roots.pem", "native_guard"])
def test_modified_asset_refuses_before_resolution(runtime, monkeypatch, asset):
    (runtime._root/"assets"/asset).chmod(0o600)
    (runtime._root/"assets"/asset).write_text("changed")
    monkeypatch.setattr(runtime, "_run", lambda *a, **k: pytest.fail("must not resolve"))
    with pytest.raises(ManagedLaunchError, match="changed"): runtime.require_contained_startup()


def test_cancel_setup_process_and_join(runtime):
    failures = []
    def run():
        try: runtime._run([sys.executable, "-I", "-S", "-c", "import time; time.sleep(10)"], seconds=10)
        except ManagedLaunchError as exc: failures.append(str(exc))
    thread = threading.Thread(target=run); thread.start()
    wait_until(lambda: bool(runtime._processes))
    started = time.monotonic(); runtime._cancelled.set()
    thread.join(2)
    report = runtime.close("cancelled")
    assert not thread.is_alive() and time.monotonic()-started < 2
    assert failures and report["allWorkersJoined"]


def test_constructor_process_cancellation_after_both_pipes_close(tmp_path):
    # Isolate the constructor primitive: no lifetime watcher may rescue it.
    value = object.__new__(module.ContainedRuntime)
    value.policy = ManagedPolicy()
    value.created = time.monotonic()
    value._cancelled = threading.Event()
    value._stop = threading.Event()
    value._turn_started = None
    value._lock = threading.Lock()
    value._processes = set()
    marker = tmp_path/"closed-pipes"
    script = f"import os,time;os.close(1);os.close(2);open({str(marker)!r},'w').close();time.sleep(10)"
    failures = []
    def run():
        try: value._run([sys.executable, "-I", "-S", "-c", script], seconds=10)
        except ManagedLaunchError as exc: failures.append(str(exc))
    worker = threading.Thread(target=run); worker.start()
    try:
        wait_until(marker.exists)
        began = time.monotonic(); value._cancelled.set()
        worker.join(1)
        assert not worker.is_alive() and failures and time.monotonic()-began < 1
        assert not value._processes
    finally:
        value._cancelled.set()
        for child in list(value._processes): value._terminate(child)
        worker.join(1)


def test_close_during_killable_resolver_never_starts_broker(runtime, monkeypatch):
    original = runtime._run
    def held(command, *, seconds):
        assert command[-2] == "resolve"
        return original([sys.executable, "-I", "-S", "-c", "import time; time.sleep(10)"], seconds=10)
    monkeypatch.setattr(runtime, "_run", held)
    errors = []
    def start():
        try: runtime.require_contained_startup()
        except ManagedLaunchError as exc: errors.append(str(exc))
    worker = threading.Thread(target=start); worker.start()
    wait_until(lambda: bool(runtime._processes))
    report = runtime.close("cancelled")
    worker.join(2)
    assert not worker.is_alive() and errors and report["allWorkersJoined"]
    assert runtime._broker.snapshot()["attempts"] == 0


def test_resolver_cancel_unwinds_client_start_lock_before_waiting_for_abort(runtime, monkeypatch):
    original = runtime._run
    def held(command, *, seconds):
        return original([sys.executable, "-I", "-S", "-c", "import time;time.sleep(10)"], seconds=10)
    monkeypatch.setattr(runtime, "_run", held)
    client = AppServerClient(["AUTHORED_MUST_NOT_LAUNCH"], launch_guard=runtime.require_contained_startup,
                             env={}, inherit_env=False)
    runtime.bind_abort(client.close)
    errors = []
    def start():
        try: client.start()
        except ManagedLaunchError as exc: errors.append(str(exc))
    worker = threading.Thread(target=start); worker.start()
    wait_until(lambda: bool(runtime._processes))
    began = time.monotonic(); runtime._cancelled.set()
    worker.join(1.5)
    assert not worker.is_alive() and errors and time.monotonic()-began < 1.5
    assert client.process is None and runtime.close()["allWorkersJoined"]


@pytest.mark.parametrize("runtime", [True], indirect=True)
def test_managed_launch_cancel_unwinds_composed_start_lock(runtime, monkeypatch):
    from eidos.native_managed import ManagedLaunch
    from eidos.native_managed_contract import ManagedAttemptIdentity
    # Same real resource/guard path; the target is authored Python, never Codex.
    runtime._evidence.update(transport="authored-local", classification="synthetic")
    identity = ManagedAttemptIdentity("attempt-local", "context-local", "a"*64, "b"*64, "authored-local")
    launch = ManagedLaunch(runtime, identity, runtime.policy, runtime._cancelled)
    original = runtime._run
    held = threading.Event()
    release = threading.Event()
    def resolve(command, *, seconds):
        held.set()
        release.wait(2)
        return original([sys.executable, "-I", "-S", "-c", "raise SystemExit(0)"], seconds=1)
    monkeypatch.setattr(runtime, "_run", resolve)
    client = AppServerClient(["AUTHORED_MUST_NOT_LAUNCH"], launch_guard=launch.require_contained_startup,
                             env={}, inherit_env=False)
    callback_entered = threading.Event()
    def abort():
        callback_entered.set()
        client.close()
    launch.bind_abort(abort)
    errors = []
    def start():
        try: client.start()
        except ManagedLaunchError as exc: errors.append(str(exc))
    worker = threading.Thread(target=start); worker.start()
    try:
        assert held.wait(1)
        runtime._cancelled.set()
        assert callback_entered.wait(1)  # concurrent closer blocked on client's start lock
        began = time.monotonic(); release.set()
        worker.join(1.5)
        assert not worker.is_alive() and errors and time.monotonic()-began < 1.5
        assert client.process is None
        report = launch.close()
        assert report["allWorkersJoined"] and report["errors"] == [] and report["stateRemoved"]
        assert launch.read_challenge(identity) is None
    finally:
        runtime._cancelled.set(); release.set(); worker.join(7)


def test_bounded_process_output_and_descendant_cleanup(runtime, tmp_path):
    with pytest.raises(ManagedLaunchError, match="output limit"):
        runtime._run([sys.executable, "-I", "-S", "-c", "import os; os.write(1,b'x'*100000)"], seconds=1)
    pid_file = tmp_path/"pid"
    script = "import os,time; p=os.fork(); " + (
        f"open({str(pid_file)!r},'w').write(str(p)) if p else time.sleep(10); os._exit(0)")
    with pytest.raises(ManagedLaunchError, match="deadline"):
        runtime._run([sys.executable, "-I", "-S", "-c", script], seconds=.2)
    pid = int(pid_file.read_text())
    wait_until(lambda: not Path(f"/proc/{pid}/stat").exists() or Path(f"/proc/{pid}/stat").read_text().split()[2] == "Z")
    assert not runtime._processes


def test_concurrent_close_and_callback_are_bounded(runtime):
    called = []
    runtime.bind_abort(lambda: called.append("closed"))
    results = []
    workers = [threading.Thread(target=lambda: results.append(runtime.close("test"))) for _ in range(4)]
    for worker in workers: worker.start()
    for worker in workers: worker.join(2)
    assert all(not worker.is_alive() for worker in workers)
    assert called == ["closed"] and len(results) == 4
    assert all(result["allWorkersJoined"] for result in results)


def test_preparation_deadline_cleanup(runtime):
    called = threading.Event()
    runtime.bind_abort(called.set)
    runtime.created = time.monotonic()-runtime.policy.preparation_seconds
    assert called.wait(1)
    wait_until(runtime._closed.is_set)
    assert runtime.close()["reason"] == "deadline"


def test_broker_close_exception_does_not_skip_owned_client_or_completion(runtime, monkeypatch):
    called = []
    original = runtime._broker.close
    def failed():
        original()
        raise RuntimeError("authored cleanup failure")
    monkeypatch.setattr(runtime._broker, "close", failed)
    runtime.bind_abort(lambda: called.append(True))
    result = runtime.close()
    assert called == [True] and runtime._closed.is_set()
    assert not result["allWorkersJoined"] and "broker-close:RuntimeError" in result["errors"]
    # Preserve the diagnostic failure; remove this test's retained disposable
    # directory ourselves because the successful-fixture finalizer expects none.
    monkeypatch.setattr(runtime._broker, "close", original)
    import shutil
    shutil.rmtree(runtime._root)
    runtime._report = {**result, "allWorkersJoined": True, "errors": [], "stateRemoved": True}


def test_constructor_cancellation_precedes_asset_read(tmp_path):
    cancelled = threading.Event(); cancelled.set()
    with pytest.raises(ManagedLaunchError, match="cancelled"):
        module.ContainedRuntime(tmp_path, config_toml="", catalog_bytes=b"{}", policy=ManagedPolicy(), cancelled=cancelled)


def test_unsupported_platform_refuses_without_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(module.platform, "machine", lambda: "x86_64")
    with pytest.raises(ManagedLaunchError, match="Linux/aarch64"):
        module.ContainedRuntime(tmp_path, config_toml="", catalog_bytes=b"{}", policy=ManagedPolicy())


@pytest.fixture(scope="module")
def compiled_guard(tmp_path_factory):
    if platform.system() != "Linux" or platform.machine() != "aarch64":
        pytest.skip("reviewed guard ABI is Linux/aarch64")
    root = tmp_path_factory.mktemp("guard")
    source = resources.files("eidos").joinpath("resources/native_guard.c")
    subprocess.run(["/usr/bin/cc", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread", str(source), "-o", str(root/"guard")],
                   check=True, timeout=20, capture_output=True)
    return root/"guard"


def test_guard_allows_threads_but_refuses_child_exec_and_leaks_no_listener(compiled_guard, tmp_path):
    authored = r'''
import ctypes,json,os,threading
out={}
t=threading.Thread(target=lambda:out.update(thread=True));t.start();t.join()
try: os.fork()
except OSError as e: out['fork']=e.errno
try: os.execv('/usr/bin/true',['true'])
except OSError as e: out['execve']=e.errno
lib=ctypes.CDLL(None,use_errno=True)
out['clone']=lib.syscall(220,17,0,0,0,0);out['cloneErrno']=ctypes.get_errno()
out['clone3']=lib.syscall(435,0,0);out['clone3Errno']=ctypes.get_errno()
out['execveat']=lib.syscall(281,-100,b'/usr/bin/true',0,0,0);out['execveatErrno']=ctypes.get_errno()
out['listeners']=[os.readlink('/proc/self/fd/'+f) for f in os.listdir('/proc/self/fd') if f not in {'0','1','2'} and os.path.exists('/proc/self/fd/'+f)]
print(json.dumps(out))
'''
    result = subprocess.run([str(compiled_guard), "3", str(tmp_path/"policy.json"), "/usr/bin/python3", "-I", "-S", "-c", authored],
                            check=True, capture_output=True, timeout=5)
    assert json.loads(result.stdout) == {"thread": True, "fork": 1, "execve": 38, "clone": -1, "cloneErrno": 1,
        "clone3": -1, "clone3Errno": 38, "execveat": -1, "execveatErrno": 38, "listeners": []}


def test_guard_parent_death_stops_authored_child(compiled_guard, tmp_path):
    pid_file = tmp_path/"child"
    code = f"import os,time; open({str(pid_file)!r},'w').write(str(os.getpid())); time.sleep(20)"
    process = subprocess.Popen([str(compiled_guard), "10", str(tmp_path/"policy.json"), "/usr/bin/python3", "-I", "-S", "-c", code],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        wait_until(pid_file.exists)
        pid = int(pid_file.read_text())
        process.kill(); process.wait(timeout=1)
        wait_until(lambda: not Path(f"/proc/{pid}/stat").exists() or Path(f"/proc/{pid}/stat").read_text().split()[2] == "Z")
    finally:
        if process.poll() is None: process.kill(); process.wait(timeout=1)
        process.stdout.close(); process.stderr.close()


def test_parent_death_between_fork_and_registration_never_executes_target(tmp_path):
    if platform.machine() != "aarch64": pytest.skip("reviewed Linux/aarch64 ABI")
    # Instrument only a deterministic scheduling delay in a test copy; the
    # packaged guard has no runtime hook capable of delaying/bypassing policy.
    source = resources.files("eidos").joinpath("resources/native_guard.c").read_text()
    assert source.count("if (!child) {") == 1
    source = source.replace("if (!child) {", "if (!child) { usleep(300000);")
    (tmp_path/"guard.c").write_text(source)
    subprocess.run(["/usr/bin/cc", "-O2", "-Wall", "-Wextra", "-Werror", str(tmp_path/"guard.c"), "-o", str(tmp_path/"guard")],
                   check=True, timeout=20, capture_output=True)
    marker = tmp_path/"must-not-exec"
    process = subprocess.Popen([str(tmp_path/"guard"), "2", str(tmp_path/"policy.json"), "/usr/bin/python3", "-I", "-S", "-c",
                                f"open({str(marker)!r},'w').write('unexpected')"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        children = Path(f"/proc/{process.pid}/task/{process.pid}/children")
        wait_until(lambda: children.exists() and children.read_text().strip())
        pid = int(children.read_text().strip())
        process.kill(); process.wait(timeout=1)
        wait_until(lambda: not Path(f"/proc/{pid}/stat").exists() or Path(f"/proc/{pid}/stat").read_text().split()[2] == "Z")
        assert not marker.exists()
    finally:
        if process.poll() is None: process.kill(); process.wait(timeout=1)
        process.stdout.close(); process.stderr.close()


def test_packaged_resources_are_not_probe_imports():
    bundle = resources.files("eidos").joinpath("resources")
    assert "getppid() != parent" in bundle.joinpath("native_guard.c").read_text()
    text = bundle.joinpath("native_runtime.py").read_text()
    assert "probe_native" not in text and "import eidos" not in text
    assert "CODEX_CA_CERTIFICATE" not in text


def test_packaged_namespace_launches_and_closes_only_authored_c_process(monkeypatch, tmp_path):
    if platform.system() != "Linux" or platform.machine() != "aarch64": pytest.skip("reviewed Linux/aarch64 ABI")
    source = tmp_path/"authored.c"
    source.write_text('#include <stdio.h>\n#include <stdlib.h>\n#include <unistd.h>\n'
        'int main(void){char cwd[4096];getcwd(cwd,sizeof(cwd));'
        'printf("%s %d %d %d\\n",cwd,access("host-only-canary",F_OK),'
        'access("/etc/ssl/certs/ca-certificates.crt",R_OK),getenv("HTTPS_PROXY")!=NULL);'
        'fflush(stdout);sleep(30);return 0;}')
    target = tmp_path/"authored-native"
    subprocess.run(["/usr/bin/cc", str(source), "-o", str(target)], check=True, timeout=20, capture_output=True)
    monkeypatch.setattr(module, "MANAGED_BINARY_SHA256", hashlib.sha256(target.read_bytes()).hexdigest())
    with tempfile.TemporaryDirectory(prefix="nema-investigation-") as cwd:
        (Path(cwd)/"host-only-canary").write_text("AUTHORED_HOST_ONLY")
        runtime = module.ContainedRuntime(cwd, config_toml="", catalog_bytes=b"{}", policy=ManagedPolicy(), binary=str(target))
        def no_dns(command, *, seconds):
            assert command[-2] == "resolve"
            return b'[[2,"8.8.8.8"]]'
        monkeypatch.setattr(runtime, "_run", no_dns)
        process = None
        try:
            runtime.require_contained_startup()
            process = subprocess.Popen(runtime.command, cwd=cwd, env={}, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            def abort():
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=2)
                    except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=2)
            runtime.bind_abort(abort)
            import select
            assert select.select([process.stdout], [], [], 3)[0]
            assert process.stdout.readline().decode().strip() == f"{cwd} -1 0 1"
            assert json.loads((runtime._root/"state/policy.json").read_text())["allListenerCopiesClosed"]
            report = runtime.close("test-cancel")
            assert report["allWorkersJoined"] and process.poll() is not None
        finally:
            runtime.close()
            if process is not None:
                if process.poll() is None: process.kill(); process.wait(timeout=2)
                process.stdin.close(); process.stdout.close(); process.stderr.close()


def test_wheel_contains_runtime_resources_and_imports_outside_checkout(tmp_path):
    root = Path(__file__).parents[1]
    subprocess.run(["uv", "build", "--offline", "--wheel", "--out-dir", str(tmp_path)],
                   cwd=root, check=True, timeout=30, capture_output=True)
    wheel = next(tmp_path.glob("*.whl"))
    installed = tmp_path/"installed"
    with zipfile.ZipFile(wheel) as archive:
        for name in ("native_guard.c", "native_runtime.py", "native_models_original.json", "native_models_patch.json",
                     "native_models_provenance.json", "native_models_LICENSE.txt"):
            assert f"eidos/resources/{name}" in archive.namelist()
        archive.extractall(installed)
    code = "import sys;sys.path.insert(0,sys.argv[1]);from eidos.native_containment import ContainedRuntime;from importlib.resources import files;assert files('eidos').joinpath('resources/native_guard.c').is_file()"
    subprocess.run([sys.executable, "-I", "-S", "-c", code, str(installed)], cwd=tmp_path,
                   check=True, timeout=5, capture_output=True)
