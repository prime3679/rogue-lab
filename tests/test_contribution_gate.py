import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / ".agent" / "contribution_gate.py"


class ContributionGateTests(unittest.TestCase):
    def run_gate(self, repo_root: Path, mode: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(GATE), mode, "--repo-root", str(repo_root)],
            capture_output=True,
            text=True,
            check=False,
        )

    def make_repo(self, temp: Path, contract: dict, extra_files: dict[str, str] | None = None) -> None:
        (temp / ".agent").mkdir(parents=True, exist_ok=True)
        (temp / "docs").mkdir(parents=True, exist_ok=True)
        (temp / "tests").mkdir(parents=True, exist_ok=True)
        (temp / "docs" / "doctrine.md").write_text("# doctrine\n", encoding="utf-8")
        for rel_path, content in (extra_files or {}).items():
            path = temp / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        (temp / ".agent" / "contribution-contract.json").write_text(
            json.dumps(contract, indent=2),
            encoding="utf-8",
        )

    def base_contract(self, command_argv: list[str]) -> dict:
        return {
            "version": 1,
            "repo": "fixture",
            "canonical_doctrine": "docs/doctrine.md",
            "source_of_truth": ["docs/doctrine.md"],
            "required_files": ["docs/doctrine.md"],
            "boundaries": {
                "portable_paths": ["docs/", ".agent/", "tests/"],
                "protected_paths": ["docs/"],
                "forbidden_actions": ["deploy"]
            },
            "review": {
                "rules": ["Report deterministic problems first."],
                "classification": {
                    "one_off_judgment": "subjective",
                    "repeatable_defect": "reproducible",
                    "missing_domain_knowledge": "undocumented",
                    "agent_behavior_failure": "ignored instructions"
                }
            },
            "escalate_if": ["Verification needs remote access."],
            "verification": {
                "commands": [
                    {
                        "id": "cmd",
                        "cwd": ".",
                        "argv": command_argv
                    }
                ]
            }
        }

    def test_audit_rejects_shell_inline_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            contract = self.base_contract(["bash", "-c", "echo nope"])
            self.make_repo(repo_root, contract)
            result = self.run_gate(repo_root, "audit")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("shell-inline execution", result.stdout)

    def test_audit_rejects_missing_required_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            contract = self.base_contract(["python3", "tests/pass.py"])
            contract["required_files"].append("README.md")
            self.make_repo(repo_root, contract, {"tests/pass.py": "print('ok')\n"})
            result = self.run_gate(repo_root, "audit")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing required_files entry: README.md", result.stdout)

    def test_verify_fails_closed_on_nonzero_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            contract = self.base_contract(["python3", "tests/fail.py"])
            self.make_repo(repo_root, contract, {"tests/fail.py": "raise SystemExit(7)\n"})
            result = self.run_gate(repo_root, "verify")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("command 'cmd' failed with exit code 7.", result.stdout)


if __name__ == "__main__":
    unittest.main()
