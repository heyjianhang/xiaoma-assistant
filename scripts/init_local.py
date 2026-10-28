"""Create a gitignored local .env once; never print secrets or replace an existing file."""

import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / ".env"
if path.exists():
    print(".env already exists; unchanged")
else:
    password = secrets.token_urlsafe(24)
    content = (root / ".env.example").read_text().replace("CHANGE_ME", password)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(content)
    print("Created .env (0600). Fill MODEL_BASE_URL, MODEL_API_KEY and MINERU_API_KEY locally.")
