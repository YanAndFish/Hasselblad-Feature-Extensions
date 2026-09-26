/* X2D 4.2.0: diagnostic module for a dedicated version-only test process.
 * Never deploy globally or preload the main GUI. No camera APIs or memory patching.
 * On the explicitly selected probe process, record its context and exit before Qt.
 */
extern int open(const char *, int, ...);
extern long read(int, void *, unsigned long);
extern long write(int, const void *, unsigned long);
extern int close(int);
extern unsigned int getuid(void);
extern unsigned long getauxval(unsigned long);
extern char *getenv(const char *);
extern void _exit(int) __attribute__((noreturn));

static int equal(const char *a, const char *b) {
    if (!a || !b) return 0;
    while (*a && *a == *b) { ++a; ++b; }
    return *a == *b;
}

static int selected_process(void) {
    char buf[2048];
    int fd = open("/proc/self/cmdline", 0);
    if (fd < 0) return 0;
    long n = read(fd, buf, sizeof(buf));
    close(fd);
    if (n <= 0 || n == sizeof(buf) || buf[n - 1] != 0) return 0;
    if (!equal(buf, "/system/bin/camera-test")) return 0;
    int version = 0;
    for (long i = 0; i < n;) {
        if (equal(buf + i, "--version")) version = 1;
        while (i < n && buf[i]) ++i;
        ++i;
    }
    return version;
}

__attribute__((constructor)) static void probe_context(void) {
    if (!equal(getenv("X2D_AUTOLOAD_PROBE"), "1") || !selected_process()) return;
    /* O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW. Refuse an existing status or symlink. */
    int out = open("/tmp/x2d-autoload-probe/status", 0x200c1, 0600);
    if (out < 0) _exit(21);
    const char *uid = getuid() == 0 ? "uid=root\n" : "uid=nonroot\n";
    unsigned long uidlen = getuid() == 0 ? 9 : 12;
    const char *secure = getauxval(23) ? "secure=1\n" : "secure=0\n";
    int ok = write(out, "module_loaded=1\n", 16) == 16;
    ok = (write(out, uid, uidlen) == (long)uidlen) && ok;
    ok = (write(out, secure, 9) == 9) && ok;
    int in = open("/proc/self/attr/current", 0);
    char context[256];
    long n = in < 0 ? -1 : read(in, context, sizeof(context));
    if (in >= 0) close(in);
    if (n <= 0 || n == sizeof(context)) ok = 0;
    else {
        ok = (write(out, "domain=", 7) == 7) && ok;
        ok = (write(out, context, n) == n) && ok;
        ok = (write(out, "\n", 1) == 1) && ok;
    }
    close(out);
    _exit(ok ? 0 : 22);
}
