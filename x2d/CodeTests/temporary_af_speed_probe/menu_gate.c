/* Hold only the dedicated image-test child before Qt creates its window.
 * The parent prepares that child's memory, then releases this bounded gate.
 * No hooks or configuration are applied to the factory main GUI here. */
extern char *getenv(const char *);
extern int unsetenv(const char *);
extern int open(const char *, int, ...);
extern long read(int, void *, unsigned long);
extern long write(int, const void *, unsigned long);
extern int close(int);
extern int usleep(unsigned int);
extern void _exit(int) __attribute__((noreturn));

static int equal(const char *a, const char *b) {
    if (!a || !b) return 0;
    while (*a && *a == *b) { ++a; ++b; }
    return *a == *b;
}

__attribute__((constructor)) static void wait_for_menu_parent(void) {
    if (!equal(getenv("X2D_MENU_CHILD"), "1")) return;
    static const char expected[] = "/system/bin/camera-gui\0-platform\0wayland-egl\0--fullscreen\0--bus\0none\0--imagetest\0-u\0file:/system/etc/x2d-preview-page.png\0-o\0" "2147483647\0-e\0" "2147483646\0--timeout\0" "5";
    char cmd[512];
    int fd = open("/proc/self/cmdline", 0);
    if (fd < 0) _exit(80);
    long n = read(fd, cmd, sizeof(cmd));
    close(fd);
    if (n != sizeof(expected)) _exit(81);
    for (long i = 0; i < n; ++i) if (cmd[i] != expected[i]) _exit(81);
    if (unsetenv("LD_PRELOAD") || unsetenv("X2D_MENU_CHILD")) _exit(82);
    // O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW. Stale markers fail closed.
    fd = open("/tmp/x2d-preview/menu-ready", 0x200c1, 0600);
    if (fd < 0) _exit(83);
    n = write(fd, "READY\n", 6);
    close(fd);
    if (n != 6) _exit(84);
    for (unsigned i = 0; i < 750; ++i) {
        fd = open("/tmp/x2d-preview/menu-go", 0x20000);
        if (fd >= 0) {
            char marker[2];
            n = read(fd, marker, sizeof(marker));
            close(fd);
            if (n == 1 && marker[0] == '1') return;
            _exit(85);
        }
        if (usleep(20000)) _exit(86);
    }
    _exit(87);
}
