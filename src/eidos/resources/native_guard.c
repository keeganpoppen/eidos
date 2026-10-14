
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
static int guard(unsigned lifetime, const char *report, char **target) {
    alarm(lifetime);
    check(prctl(PR_SET_DUMPABLE, 0) == 0, "supervisor-nondumpable");
    int executable = open(target[0], O_PATH|O_CLOEXEC), sockets[2];
    check(executable >= 0, "pin-target");
    check(socketpair(AF_UNIX, SOCK_SEQPACKET|SOCK_CLOEXEC, 0, sockets) == 0, "socketpair");
    pid_t parent = getpid();
    pid_t child = fork(); check(child >= 0, "initial-trusted-fork");
    if (!child) {
        close(sockets[0]);
        check(prctl(PR_SET_PDEATHSIG, SIGKILL) == 0, "parent-death");
        if (getppid() != parent) _exit(121);
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
    FILE *evidence = fopen(report, "w"); check(evidence != NULL, "policy-evidence");
    fputs("{\"recordKind\":\"trusted-launcher-self-report\",\"installedBeforeInitialExec\":true,\"initialExecContinued\":1,\"allListenerCopiesClosed\":true}", evidence);
    fclose(evidence);
    int status; check(waitpid(child, &status, 0) == child, "wait-target");
    return WIFEXITED(status) ? WEXITSTATUS(status) : 128+WTERMSIG(status);
}
int main(int argc, char **argv) {
    if (argc < 4 || argv[3][0] != '/') return 122;
    char *end = NULL;
    unsigned long lifetime = strtoul(argv[1], &end, 10);
    if (!argv[1][0] || *end || lifetime == 0 || lifetime > 900) return 122;
    return guard((unsigned)lifetime, argv[2], argv+3);
}
