"""CI Reporter — generates SARIF format reports for GitHub Actions / GitLab CI.

Design decisions:
- SARIF (Static Analysis Results Interchange Format) v2.1.0.
- Compatible with GitHub's Code Scanning / GitLab SAST.
- Can also output plain JSON summary for quick inspection.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from kiracode.security.bandit_adapter import SASTFinding


class SARIFReport(BaseModel):
    """SARIF v2.1.0 report structure."""

    version: str = "2.1.0"
    runs: list[dict[str, Any]] = Field(default_factory=list)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.model_dump(), indent=indent, ensure_ascii=False, default=str)


SEVERITY_TO_LEVEL: dict[str, str] = {
    "CRITICAL": "error",
    "HIGH": "error",
    "MEDIUM": "warning",
    "LOW": "note",
}


class CIReporter:
    """Generates SARIF reports from SAST findings."""

    def __init__(self, tool_name: str = "KiraCode-SAST", tool_version: str = "0.1.0") -> None:
        self.tool_name = tool_name
        self.tool_version = tool_version

    def generate_sarif(self, findings: list[SASTFinding], repo_uri: str = "file:///project") -> SARIFReport:
        rules = []
        results = []
        rule_ids_seen: set[str] = set()

        for f in findings:
            if f.rule_id not in rule_ids_seen:
                rule_ids_seen.add(f.rule_id)
                rules.append({
                    "id": f.rule_id,
                    "name": f.rule_name,
                    "shortDescription": {"text": f.description},
                    "defaultConfiguration": {
                        "level": SEVERITY_TO_LEVEL.get(f.severity, "warning"),
                    },
                    "properties": {
                        "tags": ["security", f.cwe_id.lower().replace("-", "")],
                    },
                    "helpUri": f"https://cwe.mitre.org/data/definitions/{f.cwe_id.split('-')[1]}.html" if "-" in f.cwe_id else "",
                })

            results.append({
                "ruleId": f.rule_id,
                "level": SEVERITY_TO_LEVEL.get(f.severity, "warning"),
                "message": {"text": f.description},
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {
                            "uri": f.filename,
                            "uriBaseId": "%SRCROOT%",
                        },
                        "region": {
                            "startLine": f.line_number,
                            "snippet": {"text": f.line_content},
                        },
                    },
                }],
                "fixes": [{
                    "description": {"text": f.remediation},
                }] if f.remediation else [],
            })

        run = {
            "tool": {
                "driver": {
                    "name": self.tool_name,
                    "version": self.tool_version,
                    "informationUri": "https://github.com/kiracode/kiracode",
                    "rules": rules,
                },
            },
            "results": results,
            "invocations": [{
                "executionSuccessful": True,
                "startTimeUtc": datetime.now(timezone.utc).isoformat(),
            }],
            "originalUriBaseIds": {
                "%SRCROOT%": {"uri": repo_uri},
            },
        }

        return SARIFReport(runs=[run])

    def generate_summary(self, findings: list[SASTFinding]) -> dict[str, Any]:
        by_severity: dict[str, int] = {}
        by_rule: dict[str, int] = {}
        for f in findings:
            by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
            by_rule[f.rule_id] = by_rule.get(f.rule_id, 0) + 1

        return {
            "tool": self.tool_name,
            "total_findings": len(findings),
            "by_severity": by_severity,
            "by_rule": by_rule,
            "sarif_version": "2.1.0",
        }
