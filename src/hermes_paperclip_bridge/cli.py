import argparse
import json
import sqlite3
import sys
import time
from dataclasses import asdict
from pathlib import Path

import structlog

from . import __version__
from .config import Settings, uuid_value
from .hermes import Hermes
from .lifecycle import bind, import_bot, provision
from .models import BridgeError
from .paperclip import Paperclip
from .reconcile import reconcile
from .rpc import RPC
from .state import Store
from .wiring import wire


def parser():
    root = argparse.ArgumentParser(description="TeamShift Agent Bridge")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--config", type=Path, default=Path("bridge.toml"))
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Show local bindings and unfinished operations")
    for command in ("bind", "provision", "import", "reconcile", "resolve", "watch", "wire"):
        sub = commands.add_parser(command)
        sub.add_argument("--apply", action="store_true", help="Apply changes; otherwise preview")
        if command in ("bind", "provision"):
            sub.add_argument("agent")
        if command in ("bind", "import"):
            sub.add_argument("profile")
        if command == "import":
            sub.add_argument("--manager-id")
        if command in ("resolve", "wire"):
            sub.add_argument("binding")
        if command == "resolve":
            sub.add_argument("--prefer", choices=("paperclip", "hermes"), required=True)
        if command == "watch":
            sub.add_argument("--interval", type=float, default=30)
        if command == "wire":
            sub.add_argument(
                "--execution-url", required=True, help="Native Hermes API listener base URL"
            )
            sub.add_argument("--secret-id", required=True, help="Existing Paperclip secret UUID")
            sub.add_argument("--key-env", required=True, help="Matching execution-key env name")
    return root


def emit(value):
    print(json.dumps(value, ensure_ascii=True), flush=True)


def outcome(results):
    if any(row.get("status") == "error" for row in results):
        return 3
    if any(row.get("status") in ("conflict", "missing") for row in results):
        return 2
    return 0


def main(argv=None):
    args = parser().parse_args(argv)
    logging_config = structlog.get_config().copy()
    structlog.configure(logger_factory=structlog.PrintLoggerFactory(file=sys.stderr))
    store = pc = None
    try:
        settings = Settings.load(args.config)
        store = Store(settings.state, scope=settings.scope)
        if args.command == "status":
            with store.exclusive():
                emit(
                    {
                        "bindings": [asdict(b) for b in store.bindings()],
                        "operations": store.operations(),
                    }
                )
            return 0
        pc = Paperclip(settings.paperclip.url, settings.company_id, settings.paperclip.token())
        hm = Hermes(
            RPC(settings.hermes.url, settings.hermes.token(), settings.auth_mode),
            settings.install_id,
        )
        if args.command == "bind":
            result = bind(store, pc, hm, uuid_value(args.agent), args.profile, apply=args.apply)
        elif args.command == "provision":
            result = provision(store, pc, hm, uuid_value(args.agent), apply=args.apply)
        elif args.command == "import":
            result = import_bot(
                store, pc, hm, args.profile, manager=args.manager_id, apply=args.apply
            )
        elif args.command == "wire":
            result = wire(
                store,
                pc,
                hm,
                args.binding,
                execution_url=args.execution_url,
                secret_id=args.secret_id,
                key_env=args.key_env,
                apply=args.apply,
            )
        else:
            prefer = None
            if args.command == "resolve":
                store.get(args.binding)
                prefer = {args.binding: args.prefer}
            if args.command == "watch" and args.interval < 1:
                raise BridgeError("Watch interval must be at least one second.")
            while True:
                results = reconcile(
                    store,
                    pc,
                    hm,
                    apply=args.apply,
                    prefer=prefer,
                    only={args.binding} if args.command == "resolve" else None,
                )
                emit(results)
                code = outcome(results)
                if args.command != "watch":
                    return code
                time.sleep(args.interval)
        emit(result)
        return 0
    except KeyboardInterrupt:
        return 130
    except BridgeError as exc:
        emit({"status": "error", "message": str(exc)})
        return 3
    except (OSError, sqlite3.Error):
        emit({"status": "error", "message": "Cannot access bridge state or configuration."})
        return 3
    finally:
        structlog.configure(**logging_config)
        if pc is not None:
            pc.close()
        if store is not None:
            store.close()


if __name__ == "__main__":
    sys.exit(main())
