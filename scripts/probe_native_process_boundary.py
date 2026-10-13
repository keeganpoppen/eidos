#!/usr/bin/env python3
"""Opt-in, no-credential native startup under a pre-exec process filter.

Linux/aarch64 experiment only. There is no real upstream, model RPC, admission
token, or production integration. All writable state and C helpers are temporary.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
from pathlib import Path
import shutil
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
from typing import Any

_spec = importlib.util.spec_from_file_location(
    "process_probe_gateway", Path(__file__).with_name("probe_native_gateway.py"))
assert _spec and _spec.loader
gateway = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gateway)

ALLOWED_METHODS = gateway.ALLOWED_METHODS
CASE_SECONDS = 20
CHALLENGES = ("fd-audit", "pthread", "pthread-fork", "pthread-exec", "fork", "vfork", "clone-process", "clone-vm",
              "clone-thread-missing-vm", "clone-thread-signal", "clone3-process", "clone3-thread",
              "posix-spawn", "execve", "execveat", "execveat-path", "seccomp-stack", "prctl-stack")


class NoModelClient(gateway.NoModelClient):
    """Inherit the strict no-model method/notification/response guards."""


# This trusted launcher installs the filter while single-threaded, before reading
# native configuration. Its initial fork is deliberately OUTSIDE the filter.
# The supervisor continues one pinned execveat and closes the last notification
# FD. Subsequent exec calls get ENOSYS from the kernel, with no userspace decider.
# Do not generalize this continuation into pointer/path policy for untrusted code.
HELPER_C = r'''
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/sched.h>
#include <linux/seccomp.h>
#include <poll.h>
#include <pthread.h>
#include <signal.h>
#include <spawn.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>
#if !defined(__aarch64__)
#error This experiment reviews only the Linux aarch64 syscall ABI.
#endif
extern char **environ;
static void die(const char *s) { perror(s); exit(120); }
static void check(int ok, const char *s) { if (!ok) die(s); }
#define DENY(n, e) BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K, (n), 0, 1), BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_ERRNO|(e))
#define NOTIFY(n) BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K, (n), 0, 1), BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_USER_NOTIF)
static int install(void) {
    const unsigned required = CLONE_THREAD|CLONE_VM|CLONE_SIGHAND;
    struct sock_filter code[] = {
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS, offsetof(struct seccomp_data, arch)),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K, AUDIT_ARCH_AARCH64, 1, 0),
        BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS, offsetof(struct seccomp_data, nr)),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K, SYS_clone, 0, 5),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS, offsetof(struct seccomp_data, args[0])),
        BPF_STMT(BPF_ALU|BPF_AND|BPF_K, required|0xff),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K, required, 1, 0),
        BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_ERRNO|EPERM),
        BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_ALLOW),
        DENY(SYS_clone3, ENOSYS),
        NOTIFY(SYS_execve), NOTIFY(SYS_execveat),
        /* A later USER_NOTIF filter must not override exec refusal. */
        DENY(SYS_seccomp, EPERM), DENY(SYS_ptrace, EPERM),
        DENY(SYS_process_vm_writev, EPERM), DENY(SYS_pidfd_getfd, EPERM),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K, SYS_prctl, 0, 3),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS, offsetof(struct seccomp_data, args[0])),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K, PR_SET_SECCOMP, 0, 1),
        BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_ERRNO|EPERM),
        BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_ALLOW)
    };
    struct sock_fprog program = {sizeof(code)/sizeof(code[0]), code};
    check(prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == 0, "no-new-privs");
    int listener = syscall(SYS_seccomp, SECCOMP_SET_MODE_FILTER,
                           SECCOMP_FILTER_FLAG_NEW_LISTENER, &program);
    check(listener >= 0, "install-filter");
    return listener;
}
static void send_fd(int sock, int fd) {
    char byte = 'F', ancillary[CMSG_SPACE(sizeof(int))] = {0};
    struct iovec io = {&byte, 1};
    struct msghdr msg = {.msg_iov=&io, .msg_iovlen=1,
                        .msg_control=ancillary, .msg_controllen=sizeof(ancillary)};
    struct cmsghdr *cmsg = CMSG_FIRSTHDR(&msg);
    cmsg->cmsg_level=SOL_SOCKET; cmsg->cmsg_type=SCM_RIGHTS;
    cmsg->cmsg_len=CMSG_LEN(sizeof(int)); memcpy(CMSG_DATA(cmsg), &fd, sizeof(fd));
    check(sendmsg(sock, &msg, 0) == 1, "send-listener");
}
static int receive_fd(int sock) {
    char byte, ancillary[CMSG_SPACE(sizeof(int))] = {0};
    struct iovec io = {&byte, 1};
    struct msghdr msg = {.msg_iov=&io, .msg_iovlen=1,
                        .msg_control=ancillary, .msg_controllen=sizeof(ancillary)};
    check(recvmsg(sock, &msg, MSG_CMSG_CLOEXEC) == 1, "receive-listener");
    struct cmsghdr *cmsg = CMSG_FIRSTHDR(&msg);
    check(cmsg && cmsg->cmsg_level == SOL_SOCKET && cmsg->cmsg_type == SCM_RIGHTS
          && cmsg->cmsg_len == CMSG_LEN(sizeof(int))
          && !(msg.msg_flags & (MSG_CTRUNC|MSG_TRUNC)), "listener-shape");
    int fd; memcpy(&fd, CMSG_DATA(cmsg), sizeof(fd)); return fd;
}
static int guard(char **target) {
    alarm(20);
    check(prctl(PR_SET_DUMPABLE, 0) == 0, "supervisor-nondumpable");
    int executable = open(target[0], O_PATH|O_CLOEXEC), sockets[2];
    check(executable >= 0, "pin-target");
    check(socketpair(AF_UNIX, SOCK_SEQPACKET|SOCK_CLOEXEC, 0, sockets) == 0, "socketpair");
    pid_t child = fork(); check(child >= 0, "initial-trusted-fork");
    if (!child) {
        close(sockets[0]);
        check(prctl(PR_SET_PDEATHSIG, SIGKILL) == 0, "parent-death");
        int listener = install();
        send_fd(sockets[1], listener); close(listener); close(sockets[1]);
        syscall(SYS_execveat, executable, "", target, environ, AT_EMPTY_PATH);
        die("initial-execveat");
    }
    close(sockets[1]); close(executable);
    int listener = receive_fd(sockets[0]); close(sockets[0]);
    struct seccomp_notif_sizes sizes;
    check(syscall(SYS_seccomp, SECCOMP_GET_NOTIF_SIZES, 0, &sizes) == 0, "notification-sizes");
    struct seccomp_notif *req = calloc(1, sizes.seccomp_notif);
    struct seccomp_notif_resp *resp = calloc(1, sizes.seccomp_notif_resp);
    check(req && resp, "notification-allocation");
    check(ioctl(listener, SECCOMP_IOCTL_NOTIF_RECV, req) == 0, "initial-notification");
    check(req->pid == (unsigned)child && req->data.arch == AUDIT_ARCH_AARCH64
          && req->data.nr == SYS_execveat && req->data.args[0] == (unsigned)executable
          && req->data.args[4] == AT_EMPTY_PATH, "trusted-initial-transition");
    resp->id=req->id; resp->flags=SECCOMP_USER_NOTIF_FLAG_CONTINUE;
    check(ioctl(listener, SECCOMP_IOCTL_NOTIF_SEND, resp) == 0, "continue-once");
    close(listener); free(req); free(resp);
    FILE *evidence = fopen("/state/policy.json", "w"); check(evidence != NULL, "policy-evidence");
    fputs("{\"recordKind\":\"trusted-launcher-self-report\",\"installedBeforeInitialExec\":true,\"initialExecContinued\":1,\"allListenerCopiesClosed\":true}", evidence);
    fclose(evidence);
    int status; check(waitpid(child, &status, 0) == child, "wait-target");
    return WIFEXITED(status) ? WEXITSTATUS(status) : 128+WTERMSIG(status);
}
static void *thread_body(void *unused) { (void)unused; return (void *)42; }
struct thread_attempt { const char *name; long result; int error; };
static void *thread_attack(void *value) {
    struct thread_attempt *a=value;
    char *args[]={"/fixture/guard", "marker", NULL};
    a->result=!strcmp(a->name, "pthread-fork") ? fork() : syscall(SYS_execve, args[0], args, environ);
    a->error=errno;
    if (!a->result) _exit(88);
    return NULL;
}
static pid_t try_vfork(void) { pid_t child=vfork(); if (!child) _exit(88); return child; }
static int challenge(const char *name) {
    long result = -1; int error = 0; pid_t child;
    char *marker_args[] = {"/fixture/guard", "marker", NULL};
    struct clone_args args = {0};
    if (!strcmp(name, "fd-audit")) {
        DIR *fds=opendir("/proc/self/fd"); check(fds != NULL, "fd-audit-open");
        int count=0, listener=0, socket_fd=0; struct dirent *entry;
        while ((entry=readdir(fds))) {
            int fd=atoi(entry->d_name);
            if (fd <= 2 || fd == dirfd(fds)) continue;
            char path[64], target[256]; snprintf(path, sizeof(path), "/proc/self/fd/%d", fd);
            ssize_t n=readlink(path, target, sizeof(target)-1); check(n >= 0, "fd-audit-readlink");
            target[n]=0; count++;
            listener |= strstr(target, "seccomp") != NULL;
            socket_fd |= strstr(target, "socket:") != NULL;
        }
        closedir(fds);
        printf("{\"case\":\"fd-audit\",\"openAboveStdio\":%d,\"seccompListenerVisible\":%s,\"socketVisible\":%s}\n",
               count, listener ? "true" : "false", socket_fd ? "true" : "false");
        return 0;
    }
    errno=0;
    if (!strcmp(name, "pthread")) {
        pthread_t thread; void *value = NULL;
        error=pthread_create(&thread, NULL, thread_body, NULL);
        if (!error) error=pthread_join(thread, &value);
        result=error ? -1 : (long)value;
    } else if (!strcmp(name, "pthread-fork") || !strcmp(name, "pthread-exec")) {
        pthread_t thread; struct thread_attempt attempt={name, -2, 0};
        check(pthread_create(&thread, NULL, thread_attack, &attempt) == 0, "thread-attack-create");
        check(pthread_join(thread, NULL) == 0, "thread-attack-join");
        result=attempt.result; error=attempt.error;
    } else if (!strcmp(name, "fork")) result=fork();
    else if (!strcmp(name, "vfork")) result=try_vfork();
    else if (!strcmp(name, "clone-process")) result=syscall(SYS_clone, SIGCHLD, 0, 0, 0, 0);
    else if (!strcmp(name, "clone-vm")) result=syscall(SYS_clone, CLONE_VM|SIGCHLD, 0, 0, 0, 0);
    else if (!strcmp(name, "clone-thread-missing-vm")) result=syscall(SYS_clone, CLONE_THREAD|CLONE_SIGHAND, 0, 0, 0, 0);
    else if (!strcmp(name, "clone-thread-signal")) result=syscall(SYS_clone, CLONE_THREAD|CLONE_VM|CLONE_SIGHAND|SIGCHLD, 0, 0, 0, 0);
    else if (!strcmp(name, "clone3-process") || !strcmp(name, "clone3-thread")) {
        if (!strcmp(name, "clone3-thread")) args.flags=CLONE_THREAD|CLONE_VM|CLONE_SIGHAND;
        else args.exit_signal=SIGCHLD;
        result=syscall(SYS_clone3, &args, sizeof(args));
    } else if (!strcmp(name, "posix-spawn")) {
        error=posix_spawn(&child, marker_args[0], NULL, NULL, marker_args, environ);
        result=error ? -1 : child;
    } else if (!strcmp(name, "execve")) result=syscall(SYS_execve, marker_args[0], marker_args, environ);
    else if (!strcmp(name, "execveat-path")) result=syscall(SYS_execveat, AT_FDCWD, marker_args[0], marker_args, environ, 0);
    else if (!strcmp(name, "execveat")) {
        int fd=open(marker_args[0], O_PATH|O_CLOEXEC); check(fd >= 0, "challenge-open");
        result=syscall(SYS_execveat, fd, "", marker_args, environ, AT_EMPTY_PATH);
    } else if (!strcmp(name, "seccomp-stack") || !strcmp(name, "prctl-stack")) {
        struct sock_filter code[] = {BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_USER_NOTIF)};
        struct sock_fprog prog={1, code};
        result=!strcmp(name, "seccomp-stack")
            ? syscall(SYS_seccomp, SECCOMP_SET_MODE_FILTER, SECCOMP_FILTER_FLAG_NEW_LISTENER, &prog)
            : prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &prog);
    } else return 121;
    if (!error) error=errno;
    if (!result && strcmp(name, "pthread")) _exit(88); /* unexpected clone child */
    printf("{\"case\":\"%s\",\"result\":%ld,\"errno\":%d}\n", name, result, error);
    return 0;
}
int main(int argc, char **argv) {
    if (argc >= 3 && !strcmp(argv[1], "guard")) return guard(argv+2);
    if (argc == 3 && !strcmp(argv[1], "challenge")) return challenge(argv[2]);
    if (argc == 2 && !strcmp(argv[1], "marker")) {
        FILE *f=fopen("/state/unexpected-exec", "w"); if (f) { fputs("ran", f); fclose(f); }
        return 77;
    }
    return 122;
}
'''


def namespace_command(root: Path, bwrap: Path, target: list[str], *, broker: bool = False) -> list[str]:
    command = [str(bwrap), "--unshare-all", "--unshare-user", "--disable-userns",
               "--die-with-parent", "--new-session", "--cap-drop", "ALL",
               "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin",
               "--symlink", "usr/lib", "/lib", "--proc", "/proc", "--dev", "/dev",
               "--tmpfs", "/tmp", "--bind", str(root / "state"), "/state",
               "--ro-bind", str(root / "fixture"), "/fixture",
               "--ro-bind", str(root / "packet"), "/packet"]
    if broker:
        command += ["--ro-bind", str(root / "broker.sock"), "/gateway/broker.sock"]
    return command + ["--clearenv", "--setenv", "HOME", "/state/home",
                      "--setenv", "CODEX_HOME", "/state/codex", "--setenv", "PATH", "/usr/bin:/bin",
                      "--setenv", "LANG", "C.UTF-8", "--chdir", "/state/workspace", "--", *target]


def prepare(root: Path, helper: Path) -> None:
    for name in ("state/home", "state/codex", "state/workspace", "fixture", "packet", "outside"):
        (root / name).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(helper, root / "fixture/guard")
    (root / "fixture/guard").chmod(0o555)


def compile_helper(directory: Path) -> Path:
    if platform.system() != "Linux" or platform.machine() != "aarch64":
        raise RuntimeError("process experiment requires the reviewed Linux/aarch64 ABI")
    source = directory / "guard.c"
    source.write_text(HELPER_C)
    helper = directory / "guard"
    try:
        subprocess.run(["/usr/bin/cc", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread",
                        str(source), "-o", str(helper)], check=True, timeout=20, capture_output=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("probe helper compilation failed: " + exc.stderr.decode()[:4096]) from exc
    return helper


def run_challenges(helper: Path, bwrap: Path) -> dict[str, Any]:
    results = {}
    for case in (*CHALLENGES, "unfiltered-execve", "unfiltered-execveat", "unfiltered-execveat-path"):
        with tempfile.TemporaryDirectory(prefix="nema-process-challenge-") as tmp:
            root = Path(tmp)
            prepare(root, helper)
            target = ["/fixture/guard", "challenge", case.removeprefix("unfiltered-")]
            if not case.startswith("unfiltered-"):
                target = ["/fixture/guard", "guard", *target]
            command = namespace_command(root, bwrap, target)
            output = subprocess.run(command, capture_output=True, text=True, timeout=5)
            results[case] = {"exitCode": output.returncode, "stderr": output.stderr,
                             "unexpectedExecutableRan": (root / "state/unexpected-exec").exists(),
                             "result": json.loads(output.stdout) if output.stdout.strip() else None,
                             "policy": json.loads((root / "state/policy.json").read_text()) if (root / "state/policy.json").exists() else None}
    return results


EGRESS = r'''
body = pathlib.Path('/packet/request.json').read_bytes()
with socket.socket(socket.AF_UNIX) as broker:
    broker.settimeout(2)
    broker.connect('/gateway/broker.sock')
    broker.sendall(b'POST /backend-api/codex/responses HTTP/1.1\r\nHost: synthetic\r\nContent-Length: '
                   + str(len(body)).encode() + b'\r\n\r\n' + body)
    response = broker.recv(4096)
pathlib.Path('/state/egress.json').write_text(json.dumps({'status': int(response.split(b' ')[1])}))
'''


HTTP_LAUNCHER = r'''
import os, pathlib, subprocess, sys, time
subprocess.Popen(['/usr/bin/python3', '/fixture/relay.py'], stdin=subprocess.DEVNULL,
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
port = pathlib.Path('/state/relay-port')
deadline = time.monotonic() + 3
while not port.exists():
    if time.monotonic() >= deadline:
        raise RuntimeError('synthetic relay did not start')
    time.sleep(.01)
with pathlib.Path('/state/codex/config.toml').open('a') as config:
    config.write('\n[mcp_servers.http_inprocess]\nurl="http://127.0.0.1:' + port.read_text()
                 + '/backend-api/codex/responses"\nstartup_timeout_sec=2\n')
os.execv('/fixture/guard', ['/fixture/guard', 'guard', sys.argv[1], 'app-server',
                          '--listen', 'stdio://', '--strict-config'])
'''


def run_native_case(helper: Path, binary: Path, bwrap: Path, *, guarded: bool,
                    http_mcp: bool = False) -> dict[str, Any]:
    if http_mcp and not guarded:
        raise ValueError("HTTP scope control requires the process filter")
    with tempfile.TemporaryDirectory(prefix="nema-native-process-") as tmp, socket.socket() as listener:
        root = Path(tmp)
        prepare(root, helper)
        canary = root / "outside/canary"
        canary.write_text("synthetic undisclosed canary")
        packet = root / "packet/evidence.txt"
        packet.write_text("synthetic selected packet")
        (root / "packet/escape").symlink_to(canary)
        (root / "packet/request.json").write_bytes(gateway.EXPECTED_BODY)
        fixture = gateway.outer.FIXTURE.replace("for raw in sys.stdin:", EGRESS + "\nfor raw in sys.stdin:")
        (root / "fixture/mcp.py").write_text(fixture)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(0.1)
        (root / "state/codex/config.toml").write_text("\n".join([
            'model_provider="openai"', 'model="nema-no-model"',
            'forced_login_method="chatgpt"', 'approval_policy="never"',
            'sandbox_mode="read-only"', 'web_search="disabled"',
            '[features]', 'plugins=false', 'apps=false', 'hooks=false',
            'shell_tool=false', 'shell_snapshot=false', 'code_mode=false',
            'skip_host_skill_discovery=true',
            '[mcp_servers.unexpected]', 'command="/usr/bin/python3"',
            f'args={json.dumps(["/fixture/mcp.py", str(canary), str(listener.getsockname()[1])])}',
            'startup_timeout_sec=3',
        ]))
        broker = gateway.SyntheticBroker()
        # Deliberately admit public content before startup: process creation is
        # the variable here; no claim that content itself authenticates a caller.
        broker.admit()

        class Handler(socketserver.BaseRequestHandler):
            def handle(self) -> None:
                try:
                    self.request.sendall(broker.exchange(self.request))
                except OSError:
                    pass

        with socketserver.UnixStreamServer(str(root / "broker.sock"), Handler) as server:
            server.timeout = 0.05
            stop = threading.Event()

            def serve() -> None:
                while not stop.is_set() and broker.requests < gateway.MAX_REQUESTS:
                    server.handle_request()

            worker = threading.Thread(target=serve, daemon=True)
            worker.start()
            native = [str(binary), "app-server", "--listen", "stdio://", "--strict-config"]
            target = ["/fixture/guard", "guard", *native] if guarded else native
            if http_mcp:
                (root / "fixture/relay.py").write_text(gateway.RELAY)
                (root / "fixture/http_launcher.py").write_text(HTTP_LAUNCHER)
                target = ["/usr/bin/python3", "/fixture/http_launcher.py", str(binary)]
            command = namespace_command(root, bwrap, target, broker=True)
            client = NoModelClient(command, cwd=root, env={}, inherit_env=False)
            watchdog = threading.Timer(CASE_SECONDS, client.close)
            watchdog.daemon = True
            watchdog.start()
            replies: dict[str, Any] = {}
            failure = None
            before_inventory = False
            try:
                replies["initialize"] = client.initialize()
                replies["account/read"] = client.request("account/read", {"refreshToken": False})
                if replies["account/read"] != {"account": None, "requiresOpenaiAuth": True}:
                    raise RuntimeError("disposable native probe unexpectedly has account/provider credentials")
                config = client.request("config/read", {"includeLayers": False})
                replies["configuredMcp"] = config.get("config", {}).get("mcp_servers", {})
                thread = client.request("thread/start", {
                    "cwd": "/state/workspace", "approvalPolicy": "never", "sandbox": "read-only",
                    "environments": [], "ephemeral": True,
                })
                replies["threadStarted"] = bool(thread.get("thread", {}).get("id"))
                # The positive control must give the MCP time to finish startup;
                # the guarded case waits equally for an attempted startup.
                deadline = time.monotonic() + 3.5
                while not (root / "state/egress.json").exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                before_inventory = (root / "state/startup.json").exists()
                replies["mcpServerStatus/list"] = client.request("mcpServerStatus/list", {
                    "threadId": thread["thread"]["id"], "limit": 100, "detail": "full",
                })
            except Exception as exc:
                failure = {"type": type(exc).__name__, "message": str(exc)}
            finally:
                watchdog.cancel()
                client.close()
                stop.set()
                worker.join(timeout=3)
                if worker.is_alive():
                    raise RuntimeError("bounded synthetic broker did not stop")
            heartbeat = root / "state/heartbeat"
            before = heartbeat.read_text() if heartbeat.exists() else None
            time.sleep(0.1)
            heartbeat_stopped = not heartbeat.exists() or heartbeat.read_text() == before
            try:
                connection, _ = listener.accept()
                connection.close()
                listener_untouched = False
            except TimeoutError:
                listener_untouched = True

        def evidence(name: str) -> Any:
            path = root / "state" / name
            return json.loads(path.read_text()) if path.exists() else None

        report = {
            "guarded": guarded, "httpMcp": http_mcp, "command": command, "nativeReplies": replies,
            "failure": failure, "nativeStderr": client.stderr_tail,
            "nativeMethodsObserved": client.methods, "policy": evidence("policy.json"),
            "mcpRanBeforeInventory": before_inventory, "mcpStartup": evidence("startup.json"),
            "mcpSyntheticEgress": evidence("egress.json"), "brokerEvents": broker.events,
            "brokerRequests": broker.requests, "syntheticPermitConsumed": broker.consumed,
            "hostCanaryUnchanged": canary.read_text() == "synthetic undisclosed canary",
            "packetUnchanged": packet.read_text() == "synthetic selected packet",
            "hostListenerUntouched": listener_untouched,
            "descendantHeartbeatStoppedAfterClose": heartbeat_stopped,
        }
        return json.loads(json.dumps(report).replace(str(root), "<probe>"))


def run_probe() -> dict[str, Any]:
    binary, bwrap = Path("/usr/bin/codex"), Path("/usr/bin/bwrap")
    with tempfile.TemporaryDirectory(prefix="nema-process-build-") as tmp:
        helper = compile_helper(Path(tmp))
        challenges = run_challenges(helper, bwrap)
        native = {label: run_native_case(helper, binary, bwrap, guarded=guarded)
                  for label, guarded in (("unfilteredControl", False), ("filtered", True))}
        native["filteredHttpScopeControl"] = run_native_case(helper, binary, bwrap, guarded=True, http_mcp=True)
    return {
        "schemaVersion": "nema-native-process-boundary-probe/1",
        "classification": "OBSERVED_NO_MODEL_SYNTHETIC",
        "nativeVersion": subprocess.check_output([str(binary), "--version"], text=True).strip(),
        "binarySha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "helperSourceSha256": hashlib.sha256(HELPER_C.encode()).hexdigest(),
        "bwrapVersion": subprocess.check_output([str(bwrap), "--version"], text=True).strip(),
        "kernel": platform.release(), "architecture": platform.machine(),
        "allowedNativeMethods": sorted(ALLOWED_METHODS), "challenges": challenges,
        "nativeCases": native, "modelTurns": 0, "existingCredentialsMounted": False,
        "realUpstreamRequests": 0, "liveAdmission": False,
        "callerAuthenticationEstablished": False,
        "mechanismDisposition": "EXPERIMENT_ONLY; HTTP integrations and full native admission remain unresolved",
        "limits": {"nativeCaseSeconds": CASE_SECONDS, "helperAlarmSeconds": 20,
                   "challengeSeconds": 5, "compileSeconds": 20,
                   "brokerRequestsPerCase": gateway.MAX_REQUESTS,
                   "brokerHeaderBytes": gateway.MAX_HEADER_BYTES,
                   "brokerBodyBytes": gateway.MAX_BODY_BYTES,
                   "brokerResponseBytes": gateway.MAX_RESPONSE_BYTES,
                   "brokerRequestSeconds": gateway.REQUEST_SECONDS,
                   "aggregateCpuMemoryPidDiskLimit": False},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_probe()
    encoded = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
