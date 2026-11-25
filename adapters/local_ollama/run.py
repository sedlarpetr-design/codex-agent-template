"""Launch one local Ollama model using this adapter's conservative defaults."""

import argparse
import shutil
import subprocess
import sys


DEFAULT_MODEL = "qwen3.5:4b"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("prompt", nargs="*", help="Optional prompt passed to `ollama run`.")
    args = parser.parse_args()
    executable = shutil.which("ollama")
    if executable is None:
        parser.error("Ollama executable was not found on PATH")
    available = subprocess.run(
        [executable, "show", args.model], capture_output=True, text=True, check=False
    )
    if available.returncode:
        parser.error(
            f"model {args.model!r} is not available locally; install it before running"
        )
    return subprocess.call([executable, "run", args.model, *args.prompt])


if __name__ == "__main__":
    sys.exit(main())
