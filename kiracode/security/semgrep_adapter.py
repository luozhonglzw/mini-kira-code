"""Semgrep Rule Adapter — supports loading custom YAML rules for pattern matching.

Design decisions:
- Rules are defined in a simplified YAML-like format (parsed as dicts).
- Each rule has: id, pattern (regex), message, severity, languages, metadata.
- Supports pattern variables: $VAR matches any identifier.
- Focuses on Python-specific patterns that Semgrep would catch.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from kiracode.security.bandit_adapter import SASTFinding


class SemgrepRule(BaseModel):
    id: str
    pattern: str  # regex pattern
    message: str = ""
    severity: str = "WARNING"
    languages: list[str] = Field(default_factory=lambda: ["python"])
    cwe_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Built-in Semgrep-style rules ───────────────────────────────────────────

BUILTIN_SEMGREP_RULES: list[SemgrepRule] = [
    SemgrepRule(
        id="python.flask.debug-mode",
        pattern=r"app\.run\s*\([^)]*debug\s*=\s*True",
        message="Flask app running in debug mode. This exposes the debugger in production.",
        severity="ERROR",
        cwe_id="CWE-489",
    ),
    SemgrepRule(
        id="python.flask.secret-key-hardcoded",
        pattern=r'app\.secret_key\s*=\s*["\'][^"\']+["\']',
        message="Hardcoded Flask secret key.",
        severity="ERROR",
        cwe_id="CWE-798",
    ),
    SemgrepRule(
        id="python.django.debug-true",
        pattern=r"DEBUG\s*=\s*True",
        message="Django DEBUG mode enabled.",
        severity="WARNING",
        cwe_id="CWE-489",
    ),
    SemgrepRule(
        id="python.requests.verify-false",
        pattern=r"requests\.\w+\s*\([^)]*verify\s*=\s*False",
        message="SSL certificate verification disabled.",
        severity="ERROR",
        cwe_id="CWE-295",
    ),
    SemgrepRule(
        id="python.jwt.alg-none",
        pattern=r"(?i)(algorithms?\s*=\s*\[[\"']none[\"']|algorithm\s*=\s*[\"']none[\"'])",
        message="JWT algorithm set to 'none' — token signature bypass.",
        severity="ERROR",
        cwe_id="CWE-347",
    ),
    SemgrepRule(
        id="python.os.system",
        pattern=r"os\.system\s*\(",
        message="Use of os.system() — prefer subprocess with shell=False.",
        severity="WARNING",
        cwe_id="CWE-78",
    ),
    SemgrepRule(
        id="python.pickle.loads",
        pattern=r"pickle\.loads?\s*\(",
        message="Pickle deserialization of untrusted data.",
        severity="ERROR",
        cwe_id="CWE-502",
    ),
    SemgrepRule(
        id="python.yaml.load-unsafe",
        pattern=r"yaml\.load\s*\((?!.*Loader)",
        message="yaml.load() without safe Loader.",
        severity="ERROR",
        cwe_id="CWE-502",
    ),
    SemgrepRule(
        id="python.mako.disable-escape",
        pattern=r"(?i)(Template\s*\([^)]*disable_unicode\s*=\s*True|default_filters\s*=\s*\[[\"']none)",
        message="Mako template auto-escaping disabled.",
        severity="WARNING",
        cwe_id="CWE-79",
    ),
    SemgrepRule(
        id="python.markdown.extensions",
        pattern=r"(?i)markdown\.markdown\s*\([^)]*extensions\s*=\s*\[[\"']unsafe",
        message="Markdown rendered with 'unsafe' extension.",
        severity="WARNING",
        cwe_id="CWE-79",
    ),
    SemgrepRule(
        id="python.cors.allow-all",
        pattern=r"(?i)(CORS\s*\([^)]*\*|Access-Control-Allow-Origin.*\*)",
        message="CORS wildcard — allows all origins.",
        severity="WARNING",
        cwe_id="CWE-942",
    ),
    SemgrepRule(
        id="python.sql.string-format",
        pattern=r'(?i)(?:execute|raw)\s*\(\s*f["\']|.*%s.*%',
        message="SQL query built with string formatting.",
        severity="ERROR",
        cwe_id="CWE-89",
    ),
]


class SemgrepRuleAdapter:
    """Scans code using Semgrep-style rules loaded from YAML or built-in."""

    def __init__(self, rules: list[SemgrepRule] | None = None) -> None:
        self._rules = rules or BUILTIN_SEMGREP_RULES
        self._compiled = [(r, re.compile(r.pattern, re.IGNORECASE)) for r in self._rules]

    @classmethod
    def from_yaml(cls, path: str | Path) -> SemgrepRuleAdapter:
        """Load rules from a YAML file."""
        p = Path(path)
        if not p.exists():
            return cls([])
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        rules = [SemgrepRule(**r) for r in data.get("rules", [])]
        return cls(rules)

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
                            rule_id=rule.id,
                            rule_name=rule.id.split(".")[-1],
                            severity=rule.severity,
                            confidence="MEDIUM",
                            cwe_id=rule.cwe_id,
                            filename=filename,
                            line_number=line_num,
                            line_content=line.strip()[:200],
                            description=rule.message,
                        )
                    )
        return findings

    def scan_file(self, filepath: str) -> list[SASTFinding]:
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return self.scan_text(content, filename=filepath)
        except Exception:
            return []

    def get_rules(self) -> list[SemgrepRule]:
        return list(self._rules)
