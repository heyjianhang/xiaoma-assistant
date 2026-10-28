"""Create an initial local admin password without printing or committing it."""

import json
import os
import secrets
from pathlib import Path

from dotenv import dotenv_values, set_key

from xiaoma.access import password_hash

root = Path(__file__).resolve().parents[1]
env = root / ".env"
values = dotenv_values(env)
if not values.get("ADMIN_PASSWORD_HASH"):
    password = secrets.token_urlsafe(24)
    set_key(env, "ADMIN_PASSWORD_HASH", password_hash(password))
    directory = root / "var"
    directory.mkdir(exist_ok=True)
    target = directory / "admin-credentials.json"
    target.write_text(
        json.dumps(
            {
                "login_url": values.get("WEB_ORIGIN", "http://127.0.0.1:3002") + "/admin",
                "password": password,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    os.chmod(target, 0o600)
    os.chmod(env, 0o600)
    print("管理员初始凭据已保存至 var/admin-credentials.json（0600，Git忽略）；未打印密码。")
else:
    print("已存在管理员密码配置，保持不变。")
