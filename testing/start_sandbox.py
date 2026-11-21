"""Start Codex with the project sandbox selected for this operating system."""

import shutil
import subprocess
import sys


def main():
    if sys.argv[1:] not in ([], ["--check"]):
        print("Použití: python testing/start_sandbox.py [--check]", file=sys.stderr)
        return 2

    codex = shutil.which("codex")
    if codex is None:
        print("Codex CLI není v PATH.", file=sys.stderr)
        return 2

    backend = []
    if sys.platform == "win32":
        backend = ["-c", 'windows.sandbox="mxc"']
        probe = ["cmd.exe", "/d", "/c", "echo SANDBOX_OK"]
    elif sys.platform == "linux":
        if shutil.which("bwrap") is None:
            print("Nainstaluj bubblewrap z balíčků distribuce.", file=sys.stderr)
            return 2
        probe = ["/bin/echo", "SANDBOX_OK"]
    else:
        print("Tento spouštěč podporuje Windows a Linux.", file=sys.stderr)
        return 2

    command = [codex, *backend]
    check = subprocess.run([
        *command, "sandbox", "--include-managed-config",
        "--permission-profile", ":read-only", "--", *probe,
    ], check=False)
    if check.returncode:
        return check.returncode
    if sys.argv[1:] == ["--check"]:
        return 0

    return subprocess.run([
        *command, "--sandbox", "read-only", "--ask-for-approval", "on-request",
    ], check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
