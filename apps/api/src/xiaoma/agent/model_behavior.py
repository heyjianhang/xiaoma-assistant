"""Narrow latency policy: genuine greetings need no extended reasoning."""

import re
from urllib.parse import urlparse


def is_greeting(question: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?:你好|您好|嗨|哈喽|早上好|下午好|晚上好|再见|拜拜|谢谢|多谢|"
            r"hello|hi|thanks|thank you)"
            r"[!！?？。.,，\s]*",
            question.strip(),
            re.IGNORECASE,
        )
    )


def plain_response_settings(model):
    """Only pass provider-specific switches to the verified hybrid Qwen endpoint."""
    host = urlparse(str(getattr(model, "openai_api_base", "") or "")).hostname or ""
    name = getattr(model, "model_name", "")
    if name != "qwen3.8-flash" or not host.endswith((".maas.aliyuncs.com", ".aliyuncs.com")):
        return {}
    return {"extra_body": {**(getattr(model, "extra_body", None) or {}), "enable_thinking": False}}
