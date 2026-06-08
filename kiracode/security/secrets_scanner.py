"""Secrets Scanner — detects sensitive information via regex patterns + entropy analysis.

Design decisions:
- Pattern-based detection for common secret formats (API keys, tokens, passwords).
- Shannon entropy analysis for high-entropy strings (potential secrets).
- Scans file content line by line, returns structured findings.
- Configurable entropy threshold and pattern list.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from pydantic import BaseModel, Field


class SecretFinding(BaseModel):
    line_number: int
    line_content: str
    pattern_name: str  # e.g. "AWS_KEY", "GENERIC_TOKEN", "HIGH_ENTROPY"
    matched_text: str
    confidence: float  # 0-1
    severity: str = "high"  # low, medium, high, critical
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScannerConfig(BaseModel):
    entropy_threshold: float = 4.5
    min_secret_length: int = 20
    max_line_length: int = 500
    ignore_comments: bool = True
    ignore_test_files: bool = True


# ── Patterns ───────────────────────────────────────────────────────────────

SECRET_PATTERNS: list[tuple[str, str, str, float]] = [
    # (name, regex, severity, confidence)
    ("AWS_ACCESS_KEY", r"AKIA[0-9A-Z]{16}", "critical", 0.95),
    ("AWS_SECRET_KEY", r"(?i)aws_secret_access_key\s*[=:]\s*['\"]?([A-Za-z0-9/+=]{40})", "critical", 0.9),
    ("GITHUB_TOKEN", r"gh[ps]_[A-Za-z0-9_]{36,}", "high", 0.9),
    ("GITLAB_TOKEN", r"glpat-[A-Za-z0-9\-_]{20,}", "high", 0.9),
    ("SLACK_TOKEN", r"xox[baprs]-[A-Za-z0-9\-]{10,}", "high", 0.85),
    ("JWT_TOKEN", r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", "high", 0.85),
    ("PRIVATE_KEY", r"-----BEGIN\s+(RSA|EC|DSA|OPENSSH)?\s*PRIVATE KEY-----", "critical", 0.99),
    ("GENERIC_SECRET", r"(?i)(password|passwd|secret|token|api_key|apikey)\s*[=:]\s*['\"]([^'\"]{8,})['\"]", "high", 0.7),
    ("DATABASE_URL", r"(?i)(mysql|postgres|mongodb|redis):\/\/[^\s]+", "high", 0.8),
    ("IP_WITH_PORT", r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{2,5}\b", "medium", 0.4),
]


def _shannon_entropy(text: str) -> float:
    """Calculate Shannon entropy of a string."""
    if not text:
        return 0.0
    freq = Counter(text)
    length = len(text)
    return -sum(
        (count / length) * math.log2(count / length)
        for count in freq.values()
    )


def _is_likely_false_positive(line: str, matched: str) -> bool:
    """Quick heuristic to filter common false positives."""
    lower = matched.lower()
    # Common placeholder values
    if lower in ("your-api-key", "your-api-key-here", "xxx", "changeme", "password", "secret"):
        return True
    # Test fixtures
    if "test" in line.lower() and "mock" in line.lower():
        return True
    return False


class SecretsScanner:
    """Scans text content for potential secrets."""

    def __init__(self, config: ScannerConfig | None = None) -> None:
        self.config = config or ScannerConfig()
        self._compiled_patterns = [
            (name, re.compile(pattern), severity, conf)
            for name, pattern, severity, conf in SECRET_PATTERNS
        ]

    def scan_text(self, content: str, filename: str = "") -> list[SecretFinding]:
        """Scan text content for secrets."""
        findings: list[SecretFinding] = []
        lines = content.split("\n")

        for line_num, line in enumerate(lines, 1):
            if len(line) > self.config.max_line_length:
                continue

            # Skip comments if configured
            stripped = line.strip()
            if self.config.ignore_comments and stripped.startswith(("#", "//", "/*")):
                continue

            # Pattern matching
            for name, pattern, severity, confidence in self._compiled_patterns:
                for match in pattern.finditer(line):
                    matched_text = match.group(0)
                    if _is_likely_false_positive(line, matched_text):
                        continue
                    findings.append(
                        SecretFinding(
                            line_number=line_num,
                            line_content=line[:200],
                            pattern_name=name,
                            matched_text=matched_text[:100],
                            confidence=confidence,
                            severity=severity,
                        )
                    )

            # Entropy-based detection for quoted strings
            self._scan_high_entropy_strings(line, line_num, findings)

        return findings

    def scan_file(self, filepath: str) -> list[SecretFinding]:
        """Scan a file for secrets."""
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return self.scan_text(content, filename=filepath)
        except Exception:
            return []

    def _scan_high_entropy_strings(
        self, line: str, line_num: int, findings: list[SecretFinding]
    ) -> None:
        """Find high-entropy strings that might be secrets."""
        # Extract quoted strings
        for match in re.finditer(r'["\']([A-Za-z0-9+/=_\-]{20,})["\']', line):
            candidate = match.group(1)
            if len(candidate) < self.config.min_secret_length:
                continue
            entropy = _shannon_entropy(candidate)
            if entropy >= self.config.entropy_threshold:
                # Check if already found by pattern
                already_found = any(
                    f.line_number == line_num and candidate in f.matched_text
                    for f in findings
                )
                if not already_found and not _is_likely_false_positive(line, candidate):
                    findings.append(
                        SecretFinding(
                            line_number=line_num,
                            line_content=line[:200],
                            pattern_name="HIGH_ENTROPY",
                            matched_text=candidate[:100],
                            confidence=min(1.0, entropy / 6.0),
                            severity="medium",
                            metadata={"entropy": round(entropy, 3)},
                        )
                    )

    def summary(self, findings: list[SecretFinding]) -> dict[str, Any]:
        by_severity: dict[str, int] = {}
        by_pattern: dict[str, int] = {}
        for f in findings:
            by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
            by_pattern[f.pattern_name] = by_pattern.get(f.pattern_name, 0) + 1
        return {
            "total_findings": len(findings),
            "by_severity": by_severity,
            "by_pattern": by_pattern,
        }
