"""Run with scripts/xiaoma.sh or uv run --directory apps/api xiaoma."""

import argparse
import getpass
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import httpx

from ..settings import ROOT
from .client import CliError, DebugClient, private_json, secure_directory
from .report import RunReport, sse_events


def print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def terminal_text(value):
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", "", str(value))


def archive(client, directory, *, yes):
    if not yes:
        raise CliError("批量归档需加 --yes；会先保存恢复清单，不清理知识库或业务数据")
    secure_directory(directory)
    name = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d-%H%M%S")
    target = directory / f"archive-{name}-{uuid4().hex[:8]}.json"
    backup = {"origin": client.origin, "conversations": [], "archived": [], "skipped": []}
    visited = set()
    while True:
        items = client.request("GET", "/api/v1/conversations")["items"]
        items = [item for item in items if item["id"] not in visited]
        if not items:
            break
        for item in items:
            visited.add(item["id"])
            backup["conversations"].append(item)
            private_json(target, backup)  # Export before the first mutation.
            if any(m.get("status") == "running" for m in item["messages"]):
                backup["skipped"].append({"id": item["id"], "reason": "对话正在运行"})
            else:
                try:
                    client.request("DELETE", f"/api/v1/conversations/{item['id']}")
                except CliError as exc:
                    backup["skipped"].append({"id": item["id"], "reason": str(exc)})
                else:
                    backup["archived"].append(item["id"])
            private_json(target, backup)
    private_json(target, backup)
    return {
        "archived": len(backup["archived"]),
        "skipped": backup["skipped"],
        "backup": str(target),
    }


def capture(client, args):
    if args.question and args.input:
        raise CliError("问题文本和 --input 只能选一个")
    question = args.question
    if args.input:
        question = sys.stdin.read() if args.input == "-" else Path(args.input).read_text()
    if not question or not question.strip():
        raise CliError("请提供问题文本，或使用 --input 文件 / --input -")
    request = {
        "conversation_id": str(args.thread or uuid4()),
        "question": question.strip(),
        "tools": {"knowledge": args.knowledge, "data": args.data},
        "skills": args.skill,
    }
    if args.model:
        request["model_id"] = args.model
    if len(question.strip()) > 4000:
        raise CliError("当前提问上限为 4000 字符，与网页一致")
    report = RunReport(args.artifacts_dir, request)
    response = None
    try:
        response = client.http.send(
            client.build("POST", "/api/v1/agent/serve", request), stream=True
        )
        if not response.is_success:
            response.read()
            client.check(response)
        if "text/event-stream" not in response.headers.get("content-type", ""):
            raise CliError("Agent 未返回 SSE 流")
        for event in sse_events(response.iter_lines()):
            report.record(event)
            if event["type"] == "delta" and not args.json:
                print(terminal_text(event["text"]), end="", flush=True)
            elif event["type"] == "step":
                print(terminal_text(event["text"]), file=sys.stderr)
            elif event["type"] == "tool":
                tool = event["tool"]
                print(terminal_text(f"[{tool['state']}] {tool['name']}"), file=sys.stderr)
            if event["type"] in {"complete", "error"}:
                break
    except KeyboardInterrupt:
        report.result.update(status="stopped", error="客户端已中断，部分输出保留")
    except (CliError, httpx.HTTPError, ValueError) as exc:
        detail = str(exc) if isinstance(exc, CliError) else "连接或事件解析失败；未自动重发问题"
        report.result.update(status="error", error=detail)
    finally:
        if response:
            response.close()
        result = report.finish()
    if result["run_id"]:
        try:
            runtime = None
            for _ in range(20):
                runtime = client.request("GET", f"/api/v1/admin/debug/runs/{result['run_id']}")
                if runtime["run"]["status"] != "running":
                    break
                time.sleep(0.1)
            private_json(report.path / "runtime.json", runtime)
            result["runtime_saved"] = True
        except (CliError, httpx.HTTPError):
            result["runtime_saved"] = False
            result["runtime_note"] = "运行快照暂未读取，可稍后用 inspect RUN_ID 获取"
        private_json(report.path / "result.json", result)
    if args.json:
        print_json(result)
    else:
        print()
        print(
            terminal_text(f"\n{result['status']} · run={result['run_id']} · {report.path}"),
            file=sys.stderr,
        )
        if result.get("error"):
            print(terminal_text(result["error"]), file=sys.stderr)
    return 0 if result["status"] == "completed" else 130 if result["status"] == "stopped" else 1


def parser():
    cli = argparse.ArgumentParser(description="小马助手：真实 HTTP Agent 调试客户端")
    cli.add_argument("--url", default=os.getenv("XIAOMA_API_URL", "http://127.0.0.1:2025"))
    cli.add_argument("--state-dir", type=Path, default=ROOT / "var/debug-cli")
    cli.add_argument("--artifacts-dir", type=Path, default=ROOT / "var/debug-runs")
    cli.add_argument("--json", action="store_true", help="chat 的 stdout 仅输出一个结果 JSON")
    sub = cli.add_subparsers(dest="command", required=True)
    login = sub.add_parser("login", help="使用管理员密码登录；不接收命令行明文密码")
    login.add_argument("--password-stdin", action="store_true")
    for name in ("whoami", "logout", "models", "skills"):
        sub.add_parser(name)
    chat = sub.add_parser("chat", help="默认新建对话；--thread ID 在同一对话中追问")
    chat.add_argument("question", nargs="?")
    chat.add_argument("--input", help="从 UTF-8 文件或 -（stdin）读取问题")
    chat.add_argument("--thread", type=UUID)
    chat.add_argument("--model")
    chat.add_argument("--skill", action="append", default=[])
    chat.add_argument("--knowledge", action=argparse.BooleanOptionalAction, default=True)
    chat.add_argument("--data", action=argparse.BooleanOptionalAction, default=True)
    inspect = sub.add_parser("inspect", help="查看本身份某次运行的服务端快照与完整结果")
    inspect.add_argument("id", type=UUID)
    threads = sub.add_parser("threads").add_subparsers(dest="action", required=True)
    threads.add_parser("list")
    for action in ("show", "archive", "restore"):
        command = threads.add_parser(action)
        command.add_argument("id", type=UUID)
    clear = threads.add_parser("clear", help="导出并软删除当前身份全部可见对话；跳过运行中对话")
    clear.add_argument("--yes", action="store_true")
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    client = None
    try:
        client = DebugClient(args.url, args.state_dir)
        if args.command == "login":
            password = (
                sys.stdin.readline().rstrip("\r\n")
                if args.password_stdin
                else getpass.getpass("管理员密码：")
            )
            if not password:
                raise CliError("密码不能为空")
            print_json(client.login(password))
        elif args.command == "chat":
            return capture(client, args)
        elif args.command == "threads":
            if args.action == "clear":
                print_json(archive(client, args.artifacts_dir, yes=args.yes))
            elif args.action == "list":
                items = client.request("GET", "/api/v1/conversations")["items"]
                print_json(
                    {
                        "items": [
                            {
                                "id": item["id"],
                                "title": item["title"],
                                "messages": len(item["messages"]),
                            }
                            for item in items
                        ]
                    }
                )
            else:
                if args.action == "show":
                    result = client.request("GET", f"/api/v1/admin/debug/conversations/{args.id}")
                elif args.action == "archive":
                    result = client.request("DELETE", f"/api/v1/conversations/{args.id}")
                else:
                    result = client.request("POST", f"/api/v1/conversations/{args.id}/restore")
                print_json(result)
        elif args.command == "inspect":
            print_json(client.request("GET", f"/api/v1/admin/debug/runs/{args.id}"))
        elif args.command == "logout":
            result = client.request("POST", "/api/v1/auth/logout")
            client.http.cookies.clear()
            client.save()
            print_json(result)
        else:
            path = "/auth/me" if args.command == "whoami" else f"/agent/{args.command}"
            print_json(client.request("GET", "/api/v1" + path))
        return 0
    except KeyboardInterrupt:
        print("已中断", file=sys.stderr)
        return 130
    except (CliError, httpx.HTTPError, OSError, ValueError) as exc:
        message = (
            str(exc)
            if isinstance(exc, CliError)
            else f"调试客户端失败（{type(exc).__name__}），请检查服务、输入或本地状态文件"
        )
        print(terminal_text(message), file=sys.stderr)
        return 1
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
