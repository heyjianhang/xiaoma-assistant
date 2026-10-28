"""Agent Skills packages: parse metadata and keep immutable resources without executing them."""

import base64
import hashlib
import io
import json
import mimetypes
import re
import stat
import zipfile
from pathlib import PurePosixPath

import yaml

NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
MAX_ARCHIVE = 5 * 1024**2
MAX_TOTAL = 10 * 1024**2
MAX_FILE = 2 * 1024**2


def safe_path(path):
    if not path or "\\" in path or "\x00" in path or path.startswith("/"):
        raise ValueError("技能文件路径无效")
    parts = path.split("/")
    if any(p in ("", ".", "..") or ":" in p for p in parts):
        raise ValueError("技能文件路径不能跨目录")
    return str(PurePosixPath(path))


def parse_skill(markdown):
    if len(markdown.encode()) > 100000:
        raise ValueError("SKILL.md 超过100KB，请把详细资料移到 references")
    parts = re.fullmatch(
        r"---\n(.*?)\n---(?:\n|$)(.*)", markdown.replace("\r\n", "\n"), flags=re.DOTALL
    )
    if parts is None:
        raise ValueError("SKILL.md 必须包含 YAML frontmatter")
    header, body = parts[1], parts[2].lstrip("\n")
    if len(header.encode()) > 8192:
        raise ValueError("Skill 元数据过长")
    try:
        if any(
            isinstance(t, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken))
            for t in yaml.scan(header)
        ):
            raise ValueError("技能元数据不支持 YAML 引用")
        metadata = yaml.safe_load(header)
    except yaml.YAMLError as exc:
        raise ValueError("Skill YAML 格式无效") from exc
    if not isinstance(metadata, dict):
        raise ValueError("Skill 元数据必须是对象")
    name, description = metadata.get("name"), metadata.get("description")
    if not isinstance(name, str) or len(name) > 64 or not NAME.fullmatch(name):
        raise ValueError("Skill name 需为1–64位小写英文、数字和单连字符")
    if not isinstance(description, str) or not 1 <= len(description.strip()) <= 1024:
        raise ValueError("Skill description 需为1–1024个字符")
    extra = metadata.get("metadata", {})
    if not isinstance(extra, dict) or any(
        not isinstance(k, str) or not isinstance(v, str) for k, v in extra.items()
    ):
        raise ValueError("metadata 必须是字符串键值对")
    for field, maximum in [("compatibility", 500), ("license", 1024), ("allowed-tools", 4096)]:
        if field in metadata and (
            not isinstance(metadata[field], str) or not 1 <= len(metadata[field]) <= maximum
        ):
            raise ValueError(f"{field} 格式无效")
    if not body.strip():
        raise ValueError("Skill 说明不能为空")
    return metadata, body.strip()


def make_package(files, source="uploaded"):
    if "SKILL.md" not in files or len(files) > 200:
        raise ValueError("技能包需要一个 SKILL.md，最多200个文件")
    try:
        markdown = files["SKILL.md"].decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("SKILL.md 需要 UTF-8 编码") from exc
    meta, body = parse_skill(markdown)
    encoded, index, total = {}, [], 0
    for path, content in sorted(files.items()):
        safe_path(path)
        total += len(content)
        if len(content) > MAX_FILE or total > MAX_TOTAL:
            raise ValueError("技能包单文件最多2MB，解包总量最多10MB")
        encoded[path] = base64.b64encode(content).decode()
        try:
            content.decode("utf-8")
            is_text = b"\x00" not in content
        except UnicodeDecodeError:
            is_text = False
        index.append(
            {
                "path": path,
                "size": len(content),
                "text": is_text,
                "type": mimetypes.guess_type(path)[0] or "application/octet-stream",
            }
        )
    digest = hashlib.sha256(json.dumps(encoded, sort_keys=True).encode()).hexdigest()
    return {
        "id": meta["name"],
        "body": body,
        "files": encoded,
        "manifest": {"frontmatter": meta, "files": index, "source": source, "sha256": digest},
    }


def read_package(content):
    if len(content) > MAX_ARCHIVE:
        raise ValueError("Skill ZIP 最多5MB")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            if len(infos) > 400:
                raise ValueError("技能包文件过多")
            files, total, seen = {}, 0, set()
            for info in infos:
                path = safe_path(info.filename.rstrip("/"))
                mode = stat.S_IFMT(info.external_attr >> 16)
                if mode not in (0, stat.S_IFREG, stat.S_IFDIR) or info.flag_bits & 1:
                    raise ValueError("技能包不支持链接、设备或加密文件")
                if (
                    info.is_dir()
                    or path.startswith("__MACOSX/")
                    or PurePosixPath(path).name == ".DS_Store"
                ):
                    continue
                if path.casefold() in seen:
                    raise ValueError("技能包有重复文件路径")
                seen.add(path.casefold())
                total += info.file_size
                if info.file_size > MAX_FILE or total > MAX_TOTAL:
                    raise ValueError("技能包展开后过大")
                files[path] = archive.read(info)
            roots = [p for p in files if PurePosixPath(p).name == "SKILL.md"]
            if len(roots) != 1:
                raise ValueError("每个 ZIP 只能包含一个 Skill")
            root = roots[0].removesuffix("SKILL.md")
            if any(not p.startswith(root) for p in files):
                raise ValueError("所有文件应位于同一技能目录")
            package = make_package({p[len(root) :]: v for p, v in files.items()})
            if root and root.rstrip("/") != package["id"]:
                raise ValueError("Skill 目录名必须与 frontmatter name 相同")
            return package
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise ValueError("无法读取 Skill ZIP") from exc


def export_package(package):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, value in package["files"].items():
            archive.writestr(f"{package['id']}/{safe_path(path)}", base64.b64decode(value))
    return output.getvalue()


def package_from_legacy(skill, source="builtin", files=None, frontmatter=None):
    meta = dict(frontmatter or {})
    meta.update(name=skill["id"], description=skill["description"])
    extra = dict(meta.get("metadata", {}))
    extra.update(
        {
            "xiaoma-display-name": skill["name"],
            "xiaoma-required-tools": " ".join(skill["required_tools"]),
        }
    )
    meta["metadata"] = extra
    content = (
        "---\n"
        + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
        + "---\n\n"
        + skill["body"]
        + "\n"
    )
    decoded = {path: base64.b64decode(value) for path, value in (files or {}).items()}
    decoded["SKILL.md"] = content.encode()
    return make_package(decoded, source)
