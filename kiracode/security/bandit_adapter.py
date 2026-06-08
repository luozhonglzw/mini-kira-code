"""Bandit Rule Adapter — wraps Bandit-style SAST rules for code analysis.

Design decisions:
- Implements Bandit's core detection rules in pure Python (no Bandit dependency).
- Rules are data-driven: each rule is a pattern + severity + CWE mapping.
- Covers: SQL injection, hardcoded passwords, eval/exec, insecure random,
  insecure deserialization, debug mode, weak crypto.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field


class SASTFinding(BaseModel):
    rule_id: str
    rule_name: str
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    confidence: str  # LOW, MEDIUM, HIGH
    cwe_id: str  # CWE-XXX
    filename: str = ""
    line_number: int = 0
    line_content: str = ""
    description: str = ""
    remediation: str = ""


class BanditRule(BaseModel):
    rule_id: str
    name: str
    pattern: str
    severity: str = "MEDIUM"
    confidence: str = "MEDIUM"
    cwe_id: str = "CWE-000"
    description: str = ""
    remediation: str = ""
    flags: int = re.IGNORECASE


# ── Bandit Rule Definitions ────────────────────────────────────────────────

BANDIT_RULES: list[BanditRule] = [
    BanditRule(
        rule_id="B101",
        name="assert_used",
        pattern=r"\bassert\s+",
        severity="LOW",
        confidence="HIGH",
        cwe_id="CWE-617",
        description="Use of assert detected. Asserts are removed when Python is run with -O flag.",
        remediation="Use proper exception handling instead of assert.",
    ),
    BanditRule(
        rule_id="B102",
        name="exec_used",
        pattern=r"\bexec\s*\(",
        severity="HIGH",
        confidence="HIGH",
        cwe_id="CWE-78",
        description="Use of exec() detected — potential code injection.",
        remediation="Avoid exec(). Use safer alternatives like importlib.",
    ),
    BanditRule(
        rule_id="B103",
        name="set_bad_file_permissions",
        pattern=r"os\.chmod\s*\(\s*[^,]+,\s*0?777\s*\)",
        severity="MEDIUM",
        confidence="HIGH",
        cwe_id="CWE-732",
        description="Setting permissive file permissions (0777).",
        remediation="Use restrictive permissions like 0o600 or 0o644.",
    ),
    BanditRule(
        rule_id="B105",
        name="hardcoded_password_string",
        pattern=r'(?i)(password|passwd|pwd)\s*=\s*["\'][^"\']{4,}["\']',
        severity="MEDIUM",
        confidence="MEDIUM",
        cwe_id="CWE-259",
        description="Hardcoded password detected.",
        remediation="Use environment variables or a secrets manager.",
    ),
    BanditRule(
        rule_id="B106",
        name="hardcoded_password_funcarg",
        pattern=r'(?i)def\s+\w+\([^)]*(?:password|passwd|pwd)\s*=\s*["\'][^"\']+["\']',
        severity="MEDIUM",
        confidence="MEDIUM",
        cwe_id="CWE-259",
        description="Hardcoded password in function argument default.",
        remediation="Use environment variables or a secrets manager.",
    ),
    BanditRule(
        rule_id="B107",
        name="hardcoded_password_default",
        pattern=r'(?i)(?:password|passwd|pwd)\s*:\s*str\s*=\s*["\'][^"\']{4,}["\']',
        severity="MEDIUM",
        confidence="MEDIUM",
        cwe_id="CWE-259",
        description="Hardcoded password in type-annotated default.",
        remediation="Use environment variables or a secrets manager.",
    ),
    BanditRule(
        rule_id="B201",
        name="flask_debug_true",
        pattern=r"(?i)(app\.run\s*\([^)]*debug\s*=\s*True|FLASK_DEBUG\s*=\s*1)",
        severity="HIGH",
        confidence="HIGH",
        cwe_id="CWE-489",
        description="Flask debug mode enabled in production.",
        remediation="Set debug=False in production.",
    ),
    BanditRule(
        rule_id="B301",
        name="pickle_loads",
        pattern=r"(?i)(pickle\.loads?\s*\(|cPickle\.loads?\s*\(|_pickle\.loads?\s*\()",
        severity="HIGH",
        confidence="MEDIUM",
        cwe_id="CWE-502",
        description="Deserialization of untrusted data via pickle.",
        remediation="Use safer serialization formats like JSON. If pickle is required, verify data source.",
    ),
    BanditRule(
        rule_id="B302",
        name="marshal_loads",
        pattern=r"marshal\.loads?\s*\(",
        severity="HIGH",
        confidence="MEDIUM",
        cwe_id="CWE-502",
        description="Deserialization via marshal.",
        remediation="Use safer serialization formats.",
    ),
    BanditRule(
        rule_id="B303",
        name="insecure_hash",
        pattern=r"(?i)(hashlib\.md5|hashlib\.sha1)\s*\(",
        severity="MEDIUM",
        confidence="HIGH",
        cwe_id="CWE-328",
        description="Use of weak hash algorithm (MD5/SHA1).",
        remediation="Use SHA-256 or stronger.",
    ),
    BanditRule(
        rule_id="B304",
        name="insecure_random",
        pattern=r"(?i)(random\.random|random\.randint|random\.choice|random\.shuffle)\s*\(",
        severity="LOW",
        confidence="MEDIUM",
        cwe_id="CWE-330",
        description="Use of non-cryptographic random module.",
        remediation="Use secrets module for security-sensitive operations.",
    ),
    BanditRule(
        rule_id="B305",
        name="insecure_cipher",
        pattern=r"(?i)(DES|RC4|Blowfish|ARC4)\b",
        severity="HIGH",
        confidence="MEDIUM",
        cwe_id="CWE-327",
        description="Use of insecure cipher algorithm.",
        remediation="Use AES-256-GCM or ChaCha20-Poly1305.",
    ),
    BanditRule(
        rule_id="B306",
        name="mktemp_q",
        pattern=r"tempfile\.mktemp\s*\(",
        severity="MEDIUM",
        confidence="HIGH",
        cwe_id="CWE-377",
        description="Use of insecure tempfile.mktemp().",
        remediation="Use tempfile.mkstemp() or tempfile.NamedTemporaryFile().",
    ),
    BanditRule(
        rule_id="B307",
        name="eval_used",
        pattern=r"\beval\s*\(",
        severity="HIGH",
        confidence="HIGH",
        cwe_id="CWE-95",
        description="Use of eval() detected — potential code injection.",
        remediation="Use ast.literal_eval() for safe evaluation.",
    ),
    BanditRule(
        rule_id="B308",
        name="mark_safe_used",
        pattern=r"(?i)mark_safe\s*\(",
        severity="MEDIUM",
        confidence="MEDIUM",
        cwe_id="CWE-79",
        description="Use of mark_safe() — potential XSS.",
        remediation="Ensure content is properly escaped before marking safe.",
    ),
    BanditRule(
        rule_id="B309",
        name="httpsconnection",
        pattern=r"http\.client\.HTTPConnection\s*\(",
        severity="MEDIUM",
        confidence="MEDIUM",
        cwe_id="CWE-319",
        description="Use of HTTP instead of HTTPS.",
        remediation="Use HTTPS connections.",
    ),
    BanditRule(
        rule_id="B310",
        name="urllib_urlopen",
        pattern=r"urllib\.request\.urlopen\s*\(",
        severity="MEDIUM",
        confidence="MEDIUM",
        cwe_id="CWE-918",
        description="Use of urllib.request.urlopen — potential SSRF.",
        remediation="Validate and restrict URLs. Consider using requests with allow_redirects=False.",
    ),
    BanditRule(
        rule_id="B311",
        name="sql_injection",
        pattern=r'(?i)(?:execute|cursor\.execute)\s*\(\s*["\'].*%s|.*\.format\(|.*f["\']',
        severity="HIGH",
        confidence="MEDIUM",
        cwe_id="CWE-89",
        description="Potential SQL injection via string formatting.",
        remediation="Use parameterized queries.",
    ),
    BanditRule(
        rule_id="B312",
        name="jinja2_autoescape_false",
        pattern=r"(?i)Environment\s*\([^)]*autoescape\s*=\s*False",
        severity="HIGH",
        confidence="HIGH",
        cwe_id="CWE-79",
        description="Jinja2 autoescape disabled — potential XSS.",
        remediation="Enable autoescape: Environment(autoescape=True).",
    ),
    BanditRule(
        rule_id="B313",
        name="yaml_load",
        pattern=r"(?i)yaml\.load\s*\((?!.*Loader)",
        severity="HIGH",
        confidence="MEDIUM",
        cwe_id="CWE-502",
        description="Use of yaml.load() without safe Loader.",
        remediation="Use yaml.safe_load() or specify Loader=yaml.SafeLoader.",
    ),
    BanditRule(
        rule_id="B314",
        name="xml_etree",
        pattern=r"(?i)xml\.etree\.ElementTree\.(parse|fromstring)\s*\(",
        severity="MEDIUM",
        confidence="MEDIUM",
        cwe_id="CWE-776",
        description="XML parsing without defusing — potential XXE.",
        remediation="Use defusedxml for untrusted XML input.",
    ),
    BanditRule(
        rule_id="B315",
        name="subprocess_shell",
        pattern=r"subprocess\.(call|run|Popen|check_output)\s*\([^)]*shell\s*=\s*True",
        severity="HIGH",
        confidence="MEDIUM",
        cwe_id="CWE-78",
        description="subprocess with shell=True — potential command injection.",
        remediation="Use shell=False and pass arguments as a list.",
    ),
    BanditRule(
        rule_id="B316",
        name="secret_key_hardcoded",
        pattern=r'(?i)(SECRET_KEY|JWT_SECRET|API_SECRET)\s*=\s*["\'][^"\']{8,}["\']',
        severity="CRITICAL",
        confidence="HIGH",
        cwe_id="CWE-798",
        description="Hardcoded secret key detected.",
        remediation="Use environment variables or a secrets manager.",
    ),
    BanditRule(
        rule_id="B317",
        name="debug_mode",
        pattern=r'(?i)DEBUG\s*=\s*True',
        severity="MEDIUM",
        confidence="HIGH",
        cwe_id="CWE-489",
        description="DEBUG mode enabled.",
        remediation="Disable DEBUG in production.",
    ),
]


class BanditRuleAdapter:
    """Scans Python code using Bandit-style rules."""

    def __init__(self, rules: list[BanditRule] | None = None) -> None:
        self._rules = rules or BANDIT_RULES
        self._compiled = [(r, re.compile(r.pattern, r.flags)) for r in self._rules]

    def scan_file(self, filepath: str) -> list[SASTFinding]:
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return self.scan_text(content, filename=filepath)
        except Exception:
            return []

    def scan_text(self, content: str, filename: str = "<string>") -> list[SASTFinding]:
        findings: list[SASTFinding] = []
        lines = content.split("\n")

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue

            for rule, pattern in self._compiled:
                if pattern.search(line):
                    findings.append(
                        SASTFinding(
                            rule_id=rule.rule_id,
                            rule_name=rule.name,
                            severity=rule.severity,
                            confidence=rule.confidence,
                            cwe_id=rule.cwe_id,
                            filename=filename,
                            line_number=line_num,
                            line_content=line.strip()[:200],
                            description=rule.description,
                            remediation=rule.remediation,
                        )
                    )
        return findings

    def get_rules(self) -> list[BanditRule]:
        return list(self._rules)

    def summary(self, findings: list[SASTFinding]) -> dict[str, Any]:
        by_severity: dict[str, int] = {}
        by_cwe: dict[str, int] = {}
        for f in findings:
            by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
            by_cwe[f.cwe_id] = by_cwe.get(f.cwe_id, 0) + 1
        return {
            "total_findings": len(findings),
            "by_severity": by_severity,
            "by_cwe": by_cwe,
        }
