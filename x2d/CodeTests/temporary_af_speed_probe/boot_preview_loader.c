/* Dedicated boot host only. No camera API, no global preload, no GUI restart. */
extern char *getenv(const char *);
extern int unsetenv(const char *);
extern int open(const char *, int, ...);
extern long read(int, void *, unsigned long);
extern int close(int);
extern int execl(const char *, const char *, ...);
extern void _exit(int) __attribute__((noreturn));
static int equal(const char *a, const char *b) {
    if (!a || !b) return 0;
    while (*a && *a == *b) { ++a; ++b; }
    return *a == *b;
}
__attribute__((constructor)) static void start_loader(void) {
    if (!equal(getenv("X2D_PREVIEW_BOOT"), "1")) return;
    char cmd[256];
    int fd = open("/proc/self/cmdline", 0);
    if (fd < 0) return;
    long n = read(fd, cmd, sizeof(cmd)); close(fd);
    /* Exact two-argument host, reject truncated/extra arguments. */
    static const char expected[] = "/system/bin/camera-test\0--version";
    if (n != sizeof(expected)) return;
    for (long i = 0; i < n; ++i) if (cmd[i] != expected[i]) return;
    if (unsetenv("LD_PRELOAD") || unsetenv("X2D_PREVIEW_BOOT")) _exit(70);
    execl("/system/bin/sh", "sh", "/system/etc/x2d-preview-loader.sh", (char *)0);
    _exit(71);
}
