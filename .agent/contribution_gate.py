#!/usr/bin/env python3
"""Static and executable zero-context contribution gate."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


REQUIRED_CLASSIFICATION_KEYS = (
    "one_off_judgment",
    "repeatable_defect",
    "missing_domain_knowledge",
    "agent_behavior_failure",
)
SHELL_INLINE_EXECUTORS = {"sh", "bash", "zsh", "fish", "cmd", "powershell", "pwsh"}
SHELL_INLINE_FLAGS = {"-c", "/c", "-command", "-encodedcommand"}
INLINE_CODE_FLAGS = {"-c", "-e"}
NETWORK_EXECUTORS = {"curl", "wget", "scp", "ssh"}
PACKAGE_MANAGERS = {
    "apt",
    "apt-get",
    "brew",
    "bun",
    "cargo",
    "conda",
    "gem",
    "go",
    "mamba",
    "npm",
    "pip",
    "pip3",
    "pipenv",
    "pipx",
    "pnpm",
    "poetry",
    "uv",
    "yarn",
}
INSTALL_SUBCOMMANDS = {
    "install",
    "add",
    "sync",
    "bootstrap",
    "setup",
    "restore",
    "ensurepip",
    "ci",
    "i",
    "update",
    "upgrade",
}
PACKAGE_FETCH_EXECUTORS = {"bunx", "npx", "pnpx"}
PACKAGE_FETCH_SUBCOMMANDS = {"dlx", "exec", "x"}
TRUSTED_RUN_SUBCOMMANDS = {"npm", "pnpm", "yarn", "bun"}
EXECUTABLE_BLOCKED_SUBCOMMANDS = {
    "cargo": {"install"},
    "conda": {"create", "install", "update", "upgrade"},
    "gem": {"install", "update", "upgrade"},
    "go": {"get", "install"},
    "mamba": {"create", "install", "update", "upgrade"},
    "pipenv": {"install", "sync", "update", "upgrade"},
    "pipx": {"ensurepath", "inject", "install", "reinstall", "upgrade"},
}
PYTHON_MODULE_PACKAGE_MANAGERS = {"pip", "ensurepip", "uv", "pipx", "pipenv"}
DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 300
DEFAULT_OUTPUT_LIMIT_BYTES = 16 * 1024
MAX_OUTPUT_LIMIT_BYTES = 64 * 1024
PROCESS_TERMINATION_GRACE_SECONDS = 0.5
COLLECTOR_JOIN_TIMEOUT_SECONDS = 1.0
CHILD_ENV_PASSTHROUGH = (
    "PATH",
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
    "TMPDIR",
    "TEMP",
    "TMP",
    "LANG",
    "LC_ALL",
)
INLINE_CODE_EXECUTOR_RE = re.compile(r"^python(?:\d+(?:\.\d+)*)?$")
ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")


class BoundedStreamCollector(threading.Thread):
    """Read a pipe without letting captured output grow unbounded."""

    def __init__(self, stream: Any, limit_bytes: int) -> None:
        super().__init__(daemon=True)
        self._stream = stream
        self._limit_bytes = limit_bytes
        self._buffer = bytearray()
        self.total_bytes = 0
        self.truncated = False

    def run(self) -> None:
        try:
            while True:
                chunk = self._stream.read(4096)
                if not chunk:
                    break
                self.total_bytes += len(chunk)
                remaining = self._limit_bytes - len(self._buffer)
                if remaining > 0:
                    self._buffer.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    self.truncated = True
        finally:
            self._stream.close()

    def text(self) -> str:
        return self._buffer.decode("utf-8", errors="replace")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("audit", "verify"), help="Gate mode to run.")
    parser.add_argument("--repo-root", default=".", help="Repo root to audit or verify.")
    parser.add_argument(
        "--contract",
        default=".agent/contribution-contract.json",
        help="Contract path relative to repo root unless absolute.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON.",
    )
    return parser.parse_args(list(argv))


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def safe_rel_path(raw: Any, label: str, errors: List[str]) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        errors.append(f"{label} must be a non-empty string.")
        return None
    candidate = raw.strip()
    path = Path(candidate)
    if path.is_absolute():
        errors.append(f"{label} must be relative, got absolute path {candidate!r}.")
        return None
    if any(part == ".." for part in path.parts):
        errors.append(f"{label} must not escape the repo root: {candidate!r}.")
        return None
    return candidate


def load_contract(repo_root: Path, contract_arg: str) -> Tuple[Dict[str, Any] | None, Path, List[str]]:
    errors: List[str] = []
    contract_path = Path(contract_arg)
    if not contract_path.is_absolute():
        contract_path = repo_root / contract_path
    contract_path = contract_path.resolve()

    if not is_relative_to(contract_path, repo_root):
        errors.append("contract path must stay inside the repo root.")
        return None, contract_path, errors
    if not contract_path.is_file():
        errors.append(f"contract file is missing: {contract_path.relative_to(repo_root)}")
        return None, contract_path, errors

    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"contract JSON is malformed: {exc}")
        return None, contract_path, errors

    if not isinstance(contract, dict):
        errors.append("contract root must be a JSON object.")
        return None, contract_path, errors
    return contract, contract_path, errors


def ensure_string_list(
    value: Any,
    label: str,
    errors: List[str],
    *,
    allow_empty: bool = False,
) -> List[str]:
    if not isinstance(value, list):
        errors.append(f"{label} must be a list.")
        return []
    result: List[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{label}[{index}] must be a non-empty string.")
            continue
        result.append(item.strip())
    if not allow_empty and not result:
        errors.append(f"{label} must not be empty.")
    return result


def validate_optional_int(
    raw: Any,
    label: str,
    errors: List[str],
    *,
    default: int,
    maximum: int,
) -> Tuple[int, int]:
    if raw is None:
        return default, default
    if isinstance(raw, bool) or not isinstance(raw, int):
        errors.append(f"{label} must be a positive integer.")
        return default, default
    if raw <= 0:
        errors.append(f"{label} must be a positive integer.")
        return default, default
    return min(raw, maximum), raw


def validate_command_env(raw: Any, label: str, errors: List[str]) -> Dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        errors.append(f"{label} must be an object mapping environment variable names to string values.")
        return {}
    result: Dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key or "=" in key:
            errors.append(f"{label} keys must be non-empty strings without '='.")
            continue
        if any(char in key for char in ("\x00", "\n", "\r")):
            errors.append(f"{label} keys contain disallowed control characters.")
            continue
        if not isinstance(value, str):
            errors.append(f"{label}.{key} must be a string.")
            continue
        if any(char in value for char in ("\x00", "\n", "\r")):
            errors.append(f"{label}.{key} contains disallowed control characters.")
            continue
        result[key] = value
    return result


def unwrap_env_command(argv: Sequence[str]) -> List[str]:
    if not argv:
        return []
    executable = os.path.basename(argv[0]).lower()
    if executable != "env":
        return list(argv)

    index = 1
    while index < len(argv):
        token = argv[index]
        lowered = token.lower()
        if token == "--":
            index += 1
            break
        if ENV_ASSIGNMENT_RE.match(token):
            index += 1
            continue
        if lowered in {"-i", "--ignore-environment"}:
            index += 1
            continue
        if lowered in {"-u", "--unset"}:
            index += 2
            continue
        if lowered.startswith("--unset="):
            index += 1
            continue
        break
    return list(argv[index:])


def is_inline_code_executor(executable: str) -> bool:
    return bool(INLINE_CODE_EXECUTOR_RE.fullmatch(executable)) or executable in {"node", "nodejs", "ruby", "perl"}


def has_blocked_package_manager_tokens(executable: str, lowered: Sequence[str]) -> bool:
    package_tokens = lowered[1:]
    if executable == "uv" and len(package_tokens) >= 2 and package_tokens[0] == "pip":
        return any(token in INSTALL_SUBCOMMANDS for token in package_tokens[1:])
    if executable == "poetry" and len(package_tokens) >= 2 and package_tokens[0] == "self":
        return any(token in INSTALL_SUBCOMMANDS for token in package_tokens[1:])
    if executable in EXECUTABLE_BLOCKED_SUBCOMMANDS:
        return any(token in EXECUTABLE_BLOCKED_SUBCOMMANDS[executable] for token in package_tokens)
    return any(token in INSTALL_SUBCOMMANDS or token in PACKAGE_FETCH_SUBCOMMANDS for token in package_tokens)


def is_forbidden_package_manager_command(executable: str, lowered: Sequence[str]) -> bool:
    if executable in PACKAGE_FETCH_EXECUTORS:
        return True
    if executable == "yarn" and len(lowered) == 1:
        return True
    if executable in TRUSTED_RUN_SUBCOMMANDS and len(lowered) >= 2 and lowered[1] == "run":
        return False
    if executable == "bun":
        if len(lowered) == 1:
            return True
        if has_blocked_package_manager_tokens(executable, lowered):
            return True
        return False
    if executable not in PACKAGE_MANAGERS:
        return False
    if has_blocked_package_manager_tokens(executable, lowered):
        return True
    return False


def is_forbidden_python_module_package_manager_command(executable: str, lowered: Sequence[str]) -> bool:
    if not executable.startswith("python") or len(lowered) < 3 or lowered[1] != "-m":
        return False

    module_name = lowered[2]
    if module_name not in PYTHON_MODULE_PACKAGE_MANAGERS:
        return False

    module_tokens = lowered[3:]
    if module_name == "uv" and len(module_tokens) >= 2 and module_tokens[0] == "pip":
        return any(token in INSTALL_SUBCOMMANDS for token in module_tokens[1:])
    if module_name == "ensurepip":
        return True
    if module_name == "pip":
        return any(token in INSTALL_SUBCOMMANDS for token in module_tokens)
    if module_name in EXECUTABLE_BLOCKED_SUBCOMMANDS:
        return any(token in EXECUTABLE_BLOCKED_SUBCOMMANDS[module_name] for token in module_tokens)
    return False


def build_child_env(overrides: Dict[str, str]) -> Dict[str, str]:
    env = {
        key: value
        for key in CHILD_ENV_PASSTHROUGH
        if (value := os.environ.get(key))
    }
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env.update(overrides)
    return env


def popen_session_kwargs() -> Dict[str, Any]:
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return {"creationflags": creationflags}
    return {"start_new_session": True}


def terminate_command(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            process.kill()
        return

    ctrl_break = getattr(signal, "CTRL_BREAK_EVENT", None)
    if ctrl_break is not None:
        try:
            process.send_signal(ctrl_break)
            process.wait(timeout=PROCESS_TERMINATION_GRACE_SECONDS)
            return
        except (OSError, subprocess.TimeoutExpired, ValueError):
            pass
    process.kill()


def finalize_collectors(
    collectors: Sequence[BoundedStreamCollector],
) -> bool:
    all_joined = True
    for collector in collectors:
        collector.join(timeout=COLLECTOR_JOIN_TIMEOUT_SECONDS)
        if collector.is_alive():
            all_joined = False
    return all_joined


def sanitize_command_for_output(command: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(command)
    env = result.pop("env", {})
    result["env_keys"] = sorted(env)
    return result


def validate_command_shape(command: Any, index: int, errors: List[str]) -> Dict[str, Any] | None:
    label = f"verification.commands[{index}]"
    if not isinstance(command, dict):
        errors.append(f"{label} must be an object.")
        return None

    command_id = command.get("id")
    if not isinstance(command_id, str) or not command_id.strip():
        errors.append(f"{label}.id must be a non-empty string.")

    cwd = safe_rel_path(command.get("cwd", "."), f"{label}.cwd", errors)
    argv = command.get("argv")
    if not isinstance(argv, list) or not argv:
        errors.append(f"{label}.argv must be a non-empty argv array.")
        return None

    clean_argv: List[str] = []
    for arg_index, arg in enumerate(argv):
        if not isinstance(arg, str) or not arg:
            errors.append(f"{label}.argv[{arg_index}] must be a non-empty string.")
            continue
        if any(char in arg for char in ("\x00", "\n", "\r")):
            errors.append(f"{label}.argv[{arg_index}] contains disallowed control characters.")
            continue
        clean_argv.append(arg)
    if not clean_argv:
        errors.append(f"{label}.argv must contain at least one usable string.")
        return None

    effective_argv = unwrap_env_command(clean_argv)
    if not effective_argv:
        errors.append(f"{label} wraps env without naming an executable.")
        return None

    lowered = [item.lower() for item in effective_argv]
    executable = os.path.basename(lowered[0])
    timeout_seconds, requested_timeout_seconds = validate_optional_int(
        command.get("timeout_seconds"),
        f"{label}.timeout_seconds",
        errors,
        default=DEFAULT_TIMEOUT_SECONDS,
        maximum=MAX_TIMEOUT_SECONDS,
    )
    output_limit_bytes, requested_output_limit_bytes = validate_optional_int(
        command.get("output_limit_bytes"),
        f"{label}.output_limit_bytes",
        errors,
        default=DEFAULT_OUTPUT_LIMIT_BYTES,
        maximum=MAX_OUTPUT_LIMIT_BYTES,
    )
    command_env = validate_command_env(command.get("env"), f"{label}.env", errors)

    if executable in SHELL_INLINE_EXECUTORS and any(flag in lowered[1:] for flag in SHELL_INLINE_FLAGS):
        errors.append(f"{label} uses shell-inline execution, which is forbidden.")
    if is_inline_code_executor(executable) and any(flag in lowered[1:] for flag in INLINE_CODE_FLAGS):
        errors.append(f"{label} uses inline code execution, which is forbidden.")
    if executable in NETWORK_EXECUTORS:
        errors.append(f"{label} uses a network-oriented executable ({effective_argv[0]!r}), which is forbidden.")
    if is_forbidden_package_manager_command(executable, lowered):
        errors.append(f"{label} looks like setup/install or ephemeral package-fetch work, which is forbidden.")
    if is_forbidden_python_module_package_manager_command(executable, lowered):
        errors.append(f"{label} looks like setup/install or ephemeral package-fetch work, which is forbidden.")

    return {
        "id": command_id.strip() if isinstance(command_id, str) else "",
        "cwd": cwd or ".",
        "argv": clean_argv,
        "effective_argv": effective_argv,
        "description": command.get("description", ""),
        "timeout_seconds": timeout_seconds,
        "requested_timeout_seconds": requested_timeout_seconds,
        "output_limit_bytes": output_limit_bytes,
        "requested_output_limit_bytes": requested_output_limit_bytes,
        "env": command_env,
    }


def validate_contract(
    contract: Dict[str, Any],
    repo_root: Path,
    contract_path: Path,
) -> Tuple[List[str], Dict[str, Any]]:
    errors: List[str] = []
    report: Dict[str, Any] = {
        "canonical_doctrine": None,
        "source_of_truth": [],
        "required_files": [],
        "commands": [],
    }

    version = contract.get("version")
    if not isinstance(version, int) or version < 1:
        errors.append("version must be a positive integer.")

    repo = contract.get("repo")
    if not isinstance(repo, str) or not repo.strip():
        errors.append("repo must be a non-empty string.")

    canonical = safe_rel_path(contract.get("canonical_doctrine"), "canonical_doctrine", errors)
    source_of_truth = [
        item
        for index, raw in enumerate(ensure_string_list(contract.get("source_of_truth"), "source_of_truth", errors))
        if (item := safe_rel_path(raw, f"source_of_truth[{index}]", errors))
    ]
    required_files = [
        item
        for index, raw in enumerate(ensure_string_list(contract.get("required_files"), "required_files", errors))
        if (item := safe_rel_path(raw, f"required_files[{index}]", errors))
    ]

    if canonical and canonical not in source_of_truth:
        errors.append("canonical_doctrine must also appear in source_of_truth.")

    boundaries = contract.get("boundaries")
    if not isinstance(boundaries, dict):
        errors.append("boundaries must be an object.")
    else:
        for key in ("portable_paths", "protected_paths", "forbidden_actions"):
            items = ensure_string_list(boundaries.get(key), f"boundaries.{key}", errors)
            if key != "forbidden_actions":
                for index, raw in enumerate(items):
                    safe_rel_path(raw, f"boundaries.{key}[{index}]", errors)

    review = contract.get("review")
    if not isinstance(review, dict):
        errors.append("review must be an object.")
    else:
        ensure_string_list(review.get("rules"), "review.rules", errors)
        classification = review.get("classification")
        if not isinstance(classification, dict):
            errors.append("review.classification must be an object.")
        else:
            for key in REQUIRED_CLASSIFICATION_KEYS:
                value = classification.get(key)
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"review.classification.{key} must be a non-empty string.")

    ensure_string_list(contract.get("escalate_if"), "escalate_if", errors)

    verification = contract.get("verification")
    validated_commands: List[Dict[str, Any]] = []
    if not isinstance(verification, dict):
        errors.append("verification must be an object.")
    else:
        commands = verification.get("commands")
        if not isinstance(commands, list) or not commands:
            errors.append("verification.commands must be a non-empty list.")
        else:
            seen_ids = set()
            for index, command in enumerate(commands):
                validated = validate_command_shape(command, index, errors)
                if not validated:
                    continue
                if validated["id"] in seen_ids:
                    errors.append(f"verification.commands[{index}].id must be unique.")
                seen_ids.add(validated["id"])
                validated_commands.append(validated)

    for path_label, collection in (
        ("source_of_truth", source_of_truth),
        ("required_files", required_files),
    ):
        for raw in collection:
            resolved = (repo_root / raw).resolve()
            if not is_relative_to(resolved, repo_root):
                errors.append(f"{path_label} entry escapes repo root: {raw!r}.")
                continue
            if not resolved.exists():
                errors.append(f"missing {path_label} entry: {raw}")
                continue
            if raw.endswith("/") and not resolved.is_dir():
                errors.append(f"{path_label} entry should be a directory: {raw}")
            if not raw.endswith("/") and resolved.is_dir() and path_label == "required_files":
                errors.append(f"required_files entry should name a file, not a directory: {raw}")

    if contract_path.name != "contribution-contract.json":
        errors.append("contract file should be named contribution-contract.json.")

    report["canonical_doctrine"] = canonical
    report["source_of_truth"] = source_of_truth
    report["required_files"] = required_files
    report["commands"] = validated_commands
    return errors, report


def run_commands(repo_root: Path, commands: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    results: List[Dict[str, Any]] = []
    errors: List[str] = []
    for command in commands:
        cwd = (repo_root / command["cwd"]).resolve()
        if not is_relative_to(cwd, repo_root):
            errors.append(f"command {command['id']!r} cwd escapes repo root: {command['cwd']}")
            continue
        if not cwd.is_dir():
            errors.append(f"command {command['id']!r} cwd does not exist: {command['cwd']}")
            continue
        try:
            started_at = time.monotonic()
            process = subprocess.Popen(
                command["argv"],
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
                env=build_child_env(command["env"]),
                **popen_session_kwargs(),
            )
        except FileNotFoundError as exc:
            errors.append(f"command {command['id']!r} could not start: {exc}")
            results.append(
                {
                    "id": command["id"],
                    "argv": command["argv"],
                    "cwd": command["cwd"],
                    "ok": False,
                    "returncode": None,
                    "timed_out": False,
                    "duration_seconds": 0.0,
                    "timeout_seconds": command["timeout_seconds"],
                    "output_limit_bytes": command["output_limit_bytes"],
                    "stdout": "",
                    "stderr": str(exc),
                    "stdout_truncated": False,
                    "stderr_truncated": False,
                    "stdout_bytes": 0,
                    "stderr_bytes": len(str(exc).encode("utf-8")),
                }
            )
            continue
        except OSError as exc:
            errors.append(f"command {command['id']!r} could not start: {exc}")
            results.append(
                {
                    "id": command["id"],
                    "argv": command["argv"],
                    "cwd": command["cwd"],
                    "ok": False,
                    "returncode": None,
                    "timed_out": False,
                    "duration_seconds": 0.0,
                    "timeout_seconds": command["timeout_seconds"],
                    "output_limit_bytes": command["output_limit_bytes"],
                    "stdout": "",
                    "stderr": str(exc),
                    "stdout_truncated": False,
                    "stderr_truncated": False,
                    "stdout_bytes": 0,
                    "stderr_bytes": len(str(exc).encode("utf-8")),
                }
            )
            continue

        stdout_collector = BoundedStreamCollector(process.stdout, command["output_limit_bytes"])
        stderr_collector = BoundedStreamCollector(process.stderr, command["output_limit_bytes"])
        stdout_collector.start()
        stderr_collector.start()

        timed_out = False
        collector_timeout = False
        try:
            returncode = process.wait(timeout=command["timeout_seconds"])
        except subprocess.TimeoutExpired:
            timed_out = True
            terminate_command(process)
            returncode = process.wait()

        collectors_joined = finalize_collectors(
            (stdout_collector, stderr_collector),
        )
        if not collectors_joined:
            collector_timeout = True
            timed_out = True
        duration_seconds = round(time.monotonic() - started_at, 3)

        result = {
            "id": command["id"],
            "argv": command["argv"],
            "cwd": command["cwd"],
            "ok": (returncode == 0) and not timed_out,
            "returncode": returncode,
            "timed_out": timed_out,
            "duration_seconds": duration_seconds,
            "timeout_seconds": command["timeout_seconds"],
            "output_limit_bytes": command["output_limit_bytes"],
            "stdout": stdout_collector.text(),
            "stderr": stderr_collector.text(),
            "stdout_truncated": stdout_collector.truncated,
            "stderr_truncated": stderr_collector.truncated,
            "stdout_bytes": stdout_collector.total_bytes,
            "stderr_bytes": stderr_collector.total_bytes,
        }
        results.append(result)
        if collector_timeout:
            errors.append(
                f"command {command['id']!r} timed out after {command['timeout_seconds']} seconds."
            )
        elif timed_out:
            errors.append(f"command {command['id']!r} timed out after {command['timeout_seconds']} seconds.")
        elif returncode != 0:
            errors.append(f"command {command['id']!r} failed with exit code {returncode}.")
    return results, errors


def build_output(
    mode: str,
    repo_root: Path,
    contract_path: Path,
    audit: Dict[str, Any],
    command_results: List[Dict[str, Any]],
    errors: List[str],
) -> Dict[str, Any]:
    return {
        "ok": not errors,
        "mode": mode,
        "repo_root": str(repo_root),
        "contract_path": str(contract_path),
        "audit": {
            **audit,
            "commands": [sanitize_command_for_output(command) for command in audit.get("commands", [])],
        },
        "commands": command_results,
        "errors": errors,
    }


def render_text(payload: Dict[str, Any]) -> str:
    lines = []
    status = "PASS" if payload["ok"] else "FAIL"
    lines.append(f"{status} {payload['mode']}")
    audit = payload["audit"]
    if audit.get("canonical_doctrine"):
        lines.append(f"canonical doctrine: {audit['canonical_doctrine']}")
    if audit.get("source_of_truth"):
        lines.append(f"source_of_truth entries: {len(audit['source_of_truth'])}")
    if audit.get("required_files"):
        lines.append(f"required_files entries: {len(audit['required_files'])}")
    if audit.get("commands"):
        lines.append(f"verification commands: {len(audit['commands'])}")
    for command in payload["commands"]:
        state = "ok" if command["ok"] else "failed"
        lines.append(
            f"command {command['id']}: {state} "
            f"(cwd={command['cwd']}, exit={command['returncode']}, "
            f"timeout={command['timeout_seconds']}s, duration={command['duration_seconds']:.3f}s)"
        )
        if command.get("timed_out"):
            lines.append("result: timed out and was terminated by the gate")
        if command["stdout"].strip():
            lines.append("stdout:")
            lines.extend(command["stdout"].rstrip().splitlines())
            if command.get("stdout_truncated"):
                lines.append(
                    f"[stdout truncated at {command['output_limit_bytes']} bytes; saw {command['stdout_bytes']} bytes total]"
                )
        if command["stderr"].strip():
            lines.append("stderr:")
            lines.extend(command["stderr"].rstrip().splitlines())
            if command.get("stderr_truncated"):
                lines.append(
                    f"[stderr truncated at {command['output_limit_bytes']} bytes; saw {command['stderr_bytes']} bytes total]"
                )
    if payload["errors"]:
        lines.append("errors:")
        for error in payload["errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    if not repo_root.is_dir():
        payload = {
            "ok": False,
            "mode": args.mode,
            "repo_root": str(repo_root),
            "contract_path": args.contract,
            "audit": {},
            "commands": [],
            "errors": ["repo root does not exist or is not a directory."],
        }
        print(json.dumps(payload, indent=2) if args.json_output else render_text(payload))
        return 1

    contract, contract_path, load_errors = load_contract(repo_root, args.contract)
    audit: Dict[str, Any] = {}
    errors = list(load_errors)
    command_results: List[Dict[str, Any]] = []

    if contract is not None:
        validation_errors, audit = validate_contract(contract, repo_root, contract_path)
        errors.extend(validation_errors)
        if args.mode == "verify" and not errors:
            command_results, command_errors = run_commands(repo_root, audit["commands"])
            errors.extend(command_errors)

    payload = build_output(args.mode, repo_root, contract_path, audit, command_results, errors)
    if args.json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(render_text(payload))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
