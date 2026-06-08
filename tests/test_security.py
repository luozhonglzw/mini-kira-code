"""Tests for security modules: SecretsScanner, Sandbox, Rollback."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kiracode.security.rollback import RollbackManager
from kiracode.security.sandbox import Sandbox, SandboxConfig
from kiracode.security.secrets_scanner import SecretsScanner


# ── SecretsScanner Tests ───────────────────────────────────────────────────


@pytest.mark.unit
class TestSecretsScanner:
    def test_aws_key_detection(self):
        scanner = SecretsScanner()
        code = 'AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"'
        findings = scanner.scan_text(code)
        aws_findings = [f for f in findings if f.pattern_name == "AWS_ACCESS_KEY"]
        assert len(aws_findings) == 1
        assert aws_findings[0].severity == "critical"

    def test_generic_secret_detection(self):
        scanner = SecretsScanner()
        code = 'password = "super_secret_password_123"'
        findings = scanner.scan_text(code)
        assert len(findings) >= 1
        assert any(f.severity == "high" for f in findings)

    def test_github_token_detection(self):
        scanner = SecretsScanner()
        code = 'token = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"'
        findings = scanner.scan_text(code)
        assert any(f.pattern_name == "GITHUB_TOKEN" for f in findings)

    def test_database_url_detection(self):
        scanner = SecretsScanner()
        code = 'db = "postgres://user:pass@host:5432/db"'
        findings = scanner.scan_text(code)
        assert any(f.pattern_name == "DATABASE_URL" for f in findings)

    def test_private_key_detection(self):
        scanner = SecretsScanner()
        code = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA..."
        findings = scanner.scan_text(code)
        assert any(f.pattern_name == "PRIVATE_KEY" for f in findings)
        assert any(f.severity == "critical" for f in findings)

    def test_no_false_positives_on_normal_code(self):
        scanner = SecretsScanner()
        code = """
def login(username: str, password: str) -> dict:
    if not username:
        return {"error": "username required"}
    return {"success": True}
"""
        findings = scanner.scan_text(code)
        # Should not flag normal code
        assert len(findings) == 0

    def test_summary(self):
        scanner = SecretsScanner()
        code = 'AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\npassword = "my_secret_pass_123"'
        findings = scanner.scan_text(code)
        s = scanner.summary(findings)
        assert s["total_findings"] >= 2
        assert "by_severity" in s
        assert "by_pattern" in s


# ── Sandbox Tests ──────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSandbox:
    def test_normal_execution(self):
        async def run():
            sandbox = Sandbox(SandboxConfig(timeout=5))
            result = await sandbox.run_code('print("hello")')
            assert result.success
            assert "hello" in result.stdout
            assert result.exit_code == 0
            assert result.duration_ms > 0

        asyncio.run(run())

    def test_timeout(self):
        async def run():
            sandbox = Sandbox(SandboxConfig(timeout=1))
            result = await sandbox.run_code("import time; time.sleep(10)")
            assert result.timed_out
            assert not result.success

        asyncio.run(run())

    def test_exit_code_capture(self):
        async def run():
            sandbox = Sandbox(SandboxConfig(timeout=5))
            result = await sandbox.run_code("import sys; sys.exit(42)")
            assert not result.success
            assert result.exit_code == 42

        asyncio.run(run())

    def test_stderr_capture(self):
        async def run():
            sandbox = Sandbox(SandboxConfig(timeout=5))
            result = await sandbox.run_code("import sys; sys.stderr.write('err msg\\n')")
            assert "err msg" in result.stderr

        asyncio.run(run())

    def test_command_execution(self):
        async def run():
            sandbox = Sandbox(SandboxConfig(timeout=5))
            result = await sandbox.run_command(["echo", "test output"])
            assert result.success
            assert "test output" in result.stdout

        asyncio.run(run())


# ── Rollback Tests ─────────────────────────────────────────────────────────


@pytest.mark.unit
class TestRollback:
    def test_create_and_rollback(self):
        rb = RollbackManager()

        # Create a temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("original content")
            tmp = f.name

        try:
            sid = rb.take_snapshot([tmp], label="before edit")
            assert sid is not None

            # Modify the file
            with open(tmp, "w") as f:
                f.write("modified content")

            # Rollback
            result = rb.rollback(sid)
            assert result["success"] is True
            assert result["restored_files"] == 1

            # Verify content restored
            with open(tmp) as f:
                assert f.read() == "original content"
        finally:
            os.unlink(tmp)

    def test_rollback_new_file_creation(self):
        rb = RollbackManager()
        tmp = tempfile.mktemp(suffix=".py")

        # Snapshot before file exists
        sid = rb.take_snapshot([tmp])

        # Create the file
        with open(tmp, "w") as f:
            f.write("new file content")

        # Rollback should delete the file
        result = rb.rollback(sid)
        assert result["success"] is True
        assert not os.path.exists(tmp)

    def test_nonexistent_snapshot(self):
        rb = RollbackManager()
        result = rb.rollback("nonexistent")
        assert result["success"] is False

    def test_list_and_discard(self):
        rb = RollbackManager()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("test")
            tmp = f.name

        try:
            sid = rb.take_snapshot([tmp], label="test")
            assert len(rb.list_snapshots()) == 1
            rb.discard_snapshot(sid)
            assert len(rb.list_snapshots()) == 0
        finally:
            os.unlink(tmp)
