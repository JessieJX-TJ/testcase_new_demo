import os
from typing import Dict


def _parse_env_lines(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            continue
        if (len(v) >= 2) and ((v[0] == v[-1]) and v[0] in ("\"", "'")):
            v = v[1:-1]
        out[k] = v
    return out


def load_dotenv(path: str = ".env", override: bool = False) -> None:
    """Load a .env file into os.environ.

    - Does nothing if the file does not exist.
    - If override is False, existing environment variables are not replaced.
    """
    if not path or not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as f:
        data = _parse_env_lines(f.read())

    for k, v in data.items():
        if not override and k in os.environ:
            continue
        os.environ[k] = v
