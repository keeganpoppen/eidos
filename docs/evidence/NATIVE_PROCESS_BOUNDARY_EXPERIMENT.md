# Native startup survives pre-configuration process denial

**2026-10-13 · implementation base `711c3d1` · C6 / V1-05 / V1-12.**
This is an observed prerequisite for a bounded, text-only native specialist:
Codex **0.154.0** can initialize and inventory its configuration while a kernel
filter prevents it from creating processes or executing another program. The
filter is installed **before the initial native exec**, hence before native
configuration loads. An enabled, unexpected executable MCP cannot start.

This does **not** establish complete native admission. An enabled HTTP MCP still
makes requests from the native process. The synthetic broker rejects them; process
identity alone does not distinguish that integration from a future native model
request. The production gate remains unchanged, and shared-relay caller admission
from the [previous experiment](NATIVE_GATEWAY_ADMISSION_EXPERIMENT.md) remains
unresolved.

The [sanitized JSON artifact](NATIVE_PROCESS_BOUNDARY_0_154_0.json) records commands,
native acknowledgements, syscall challenges, synthetic broker events, binary/source
hashes and resource limits. All accounts are null; there are zero model RPCs,
existing credential mounts, real upstream requests or production modifications.

## Observed comparison

All three cases use fresh disposable state, a disconnected network namespace,
read-only runtime/fixture/packet mounts and a single synthetic host Unix broker.
The broker has no upstream client. Its one exact-content permit is deliberately
open **before startup**: the public request is available to the fixture MCP.

| Case | Native startup/inventory | Enabled executable MCP | Synthetic broker |
| --- | --- | --- | --- |
| Filter absent | Succeeds | Runs before inventory | MCP consumes one permit; duplicate refused |
| Filter installed before native exec | Succeeds | Fails with `Operation not permitted (os error 1)` | Zero requests; permit untouched |
| Filter installed; HTTP MCP also enabled | Succeeds | Same executable failure | HTTP MCP sends initialization/discovery requests; all refused 422/403 |

Each case completes `initialize`, `account/read` without refresh, `config/read`,
`thread/start` and `mcpServerStatus/list`. The configuration acknowledgement keeps
the unexpected MCP enabled; its failure is not a disabled-server shortcut. The
filtered process leaves no executable-MCP startup/egress marker. The unfiltered
fixture runs the previous outside-read/write, packet-write, symlink, parent-root,
host-loopback, external-route, namespace and remount challenges: all remain blocked.
The packet is readable, capabilities are zero, and its detached heartbeat stops
after namespace closure. These active outer challenges run in the unfiltered
control; a missing filtered MCP is not counted as having performed them.

The HTTP scope control adds a trusted fixture relay **before** launching the
filtered native process. The native HTTP MCP targets the same synthetic response
route. Its MCP initialization body fails exact-content checking; its GET and OAuth
discovery routes fail routing checks. The artifact records ten requests in this
run, with native errors explicitly acknowledging the fake HTTP 422 response. No
permit is consumed. This shows that in-process startup requests reach the broker;
it does **not** show that HTTP MCP can imitate the exact approved model body.
The relay peer is not called the authenticated original caller.

## Initial exec and the trust boundary

The installed native binary is a statically linked aarch64 ELF executable, so a
preload-constructor policy is unavailable. The experiment compiles a small C
launcher from the source embedded in
[`probe_native_process_boundary.py`](../../scripts/probe_native_process_boundary.py).
It runs on Linux **7.2.4-1-aarch64-ARCH**, bubblewrap **0.12.0**. Local syscall
headers supply the ABI; no libseccomp dependency is required.

1. Inside the outer namespace, the trusted launcher opens the fixed target with
   `O_PATH|O_CLOEXEC`, creates a private socketpair and performs its one initial
   fork **outside** the filter. The supervisor is nondumpable.
2. The single-threaded child sets `no_new_privs`, installs the filter, transfers
   its notification listener to the supervisor, and closes its listener/socket
   copies. It immediately calls `execveat` on the pinned target descriptor with
   `AT_EMPTY_PATH`. No native configuration has loaded at this point.
3. The supervisor checks the known child PID, architecture, syscall, numeric
   descriptor and exec flags. It continues this **one trusted initial transition**
   and closes the final listener. The target descriptor closes on successful exec.
4. All later `execve`/`execveat` calls reach a notification filter with no listener,
   so the kernel returns `ENOSYS`. Even a later request arriving before the final
   close receives no second continuation. Threads inherit the filter.

The policy JSON is explicitly a trusted-launcher self-report, not an independent
kernel attestation. A separate post-exec fixture enumerates `/proc/self/fd` and
finds no descriptors above stdio (excluding its own enumeration descriptor),
including no notification listener or bootstrap socket. The later exec syscall
challenges independently exercise the closed-listener behavior.

Linux documents notification-listener transfer, filter inheritance and the
no-listener `ENOSYS` result. Seccomp constrains syscalls; it is not a complete
logical-information-flow policy.
[Linux kernel seccomp documentation](https://www.kernel.org/doc/html/latest/userspace-api/seccomp_filter.html).

`CONTINUE` is unsafe as a general untrusted pointer/path authorization mechanism.
This experiment makes no such authorization decision: the initial caller is the
fixed, single-threaded launcher; its target is already open, and there is no
untrusted code or signal handler in that transition. The supervisor does not read
remote argument strings. It never continues a request from running native code.
The installed header's warning also motivates denying both ways to add another
seccomp filter, which could otherwise override a notification action.
[Linux notification API and caveats](https://man7.org/linux/man-pages/man2/seccomp_unotify.2.html).

The launcher, installed native executable, compiler/runtime, kernel and approved
relay are trusted. This is a boundary against their attempted child creation and
exec, not protection against compromise of native code or arbitrary machine code
inside an allowed thread. The supervisor and HTTP relay are explicit trusted
processes outside the target's filter. The experiment does not claim that every
process in the namespace is filtered. Host-side replacement of read-only-mounted
runtime files is outside the tested threat model.

## Syscall counterexamples

The filter checks `AUDIT_ARCH_AARCH64`; other syscall ABIs are killed. This host
has no separate aarch64 `fork`/`vfork` syscalls. Legacy `clone` is permitted only
with `CLONE_THREAD|CLONE_VM|CLONE_SIGHAND` present and a zero low-byte exit signal.
Other clone flags remain subject to kernel validation and outer namespace policy.
All `clone3` calls return `ENOSYS`, enabling libc fallback to legacy thread clone.
This is deliberately narrower than interpreting its pointer-based argument struct.
These flags describe a shared thread group/address space, not a new isolated
principal. [Linux clone semantics](https://man7.org/linux/man-pages/man2/clone.2.html).

| Challenge | Observed result |
| --- | --- |
| Post-initial-exec descriptor inventory | No descriptors beyond stdio; no listener/socket leak |
| Create/join pthread under filter | Succeeds; callback value recovered |
| Fork or exec from that pthread | EPERM / ENOSYS, confirming inherited restriction |
| libc fork, vfork, posix_spawn | EPERM |
| raw clone with SIGCHLD or VM without THREAD | EPERM |
| raw clone THREAD missing VM, or with exit signal | EPERM |
| raw clone3 process and thread variants | ENOSYS |
| direct execve, execveat with reopened FD, execveat pathname | ENOSYS; executable marker absent |
| Same three exec challenges without filter | Marker written; target exits 77 |
| Add notification filter via seccomp or prctl | EPERM |

The filter also denies ptrace, process_vm_writev and pidfd_getfd to prevent target
interference with its supervisor. Those three individual denials and the foreign
ABI kill branch were reviewed in source, not exercised by separate runtime
challenges. There is no claim covering other architectures or future process
creation syscalls. Native startup succeeds with the filter; shell/MCP subprocess
tools and later native sandbox setup requiring child processes are incompatible
by design. Model execution compatibility remains untested.

## Reproduction, limits and continuation

From the repository root:

```sh
uv run pytest tests/test_native_process_boundary_probe.py
NEMA_NATIVE_PROCESS_PROBE=1 uv run pytest tests/test_native_process_boundary_probe.py
uv run python scripts/probe_native_process_boundary.py --output /tmp/native-process-boundary.json
```

The default suite performs only no-model RPC guard tests; it never starts native
processes, compiles the helper or creates namespaces. The opt-in suite performs
the disposable syscall challenges and three real native **no-model** startups.
The script itself is an explicit opt-in experiment. It fails without the reviewed
Linux/aarch64 ABI, compiler, bubblewrap or seccomp features; there is no uncontained
fallback. Worktree runs used the main checkout's existing uv environment with
`UV_PROJECT_ENVIRONMENT=/home/elkeegano.guest/eidos/.venv uv run --no-sync`.

Verification at this implementation: **34 passed** with the native opt-in enabled;
the related process/gateway/outer/account/profile/worker/native-review/seed suite
passed **200 tests with 28 intentional opt-in skips**. The standalone script also
generated the committed artifact. Internal report links and staged whitespace
checks passed. The independent reviewer inspected the launch/filter boundary and
requested the descriptor audit above. The parent integrator inspected the source
and independently reran the opt-in suite on the integrated tree: **34 passed**,
including the native HTTP-MCP scope control. This reproduces the narrow process
boundary; it does not establish full admission.

Each native case has a 20-second watchdog; the C supervisor also has a 20-second
alarm. Individual syscall challenges have five-second timeouts, compilation has
20 seconds, and each broker handles at most 24 requests with two-second parsing
deadlines, 8 KiB headers, 4 KiB bodies and 4 KiB response bodies. The inherited
relay limits transfer bytes/time and accepts at most 24 connections. Closing the
owned namespace tears down its processes. These bounds are not aggregate CPU,
memory, PID or disk quotas.

**Next discriminating experiment:** retain this process filter and compare native
HTTP-MCP startup requests with a supported provider's request shape at a synthetic
service. First capture permitted no-model startup routes with default-deny HTTP
admission; verify that MCP initialization, discovery, redirects, duplicate attempts
and header variations cannot be admitted as provider requests. A native model
request, credentials or real forward route requires a separately resolved scope.
The unresolved question is whether supported native configuration/transport can
bind the intended operation independently of any other enabled in-process client.
Do not promote an exact body, relay token or native PID into that answer.

Lane ownership: only this script, focused tests and uniquely named evidence files
changed in `codex/native-account-admission`; the integrator owns canonical state,
handoff and any future admission decision.
