"""Security Deep Transformation Demo — 3 directions in action.

Direction A: DevSecOps SAST (Bandit + Semgrep) + SARIF report
Direction B: CVE Intelligence RAG (risk assessment)
Direction C: PentestAgent (ATT&CK script generation)
"""

from __future__ import annotations

import json
import os
import sys

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

SEPARATOR = "=" * 72


def demo_direction_a():
    """Direction A: DevSecOps — SAST scanning + SARIF report generation."""
    print(SEPARATOR)
    print("Direction A: DevSecOps — SAST Scanning + SARIF Report")
    print(SEPARATOR)

    from kiracode.security.bandit_adapter import BanditRuleAdapter
    from kiracode.security.semgrep_adapter import SemgrepRuleAdapter
    from kiracode.security.ci_reporter import CIReporter

    # Vulnerable sample code
    vulnerable_code = '''
import os
import pickle
import sqlite3
from flask import Flask, request

app = Flask(__name__)
app.secret_key = "super_secret_key_123"
app.run(debug=True)

@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]
    db = sqlite3.connect("users.db")
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    cursor = db.execute(query)
    return str(cursor.fetchone())

@app.route("/load")
def load_data():
    data = request.args.get("data")
    obj = pickle.loads(data.encode())
    return str(obj)

@app.route("/run")
def run_cmd():
    cmd = request.args.get("cmd")
    os.system(cmd)
    return "done"
'''

    # Direction A.1: Bandit SAST scan
    print("\n[A.1] Bandit-style SAST scan (24 rules)")
    bandit = BanditRuleAdapter()
    findings = bandit.scan_text(vulnerable_code, filename="app.py")

    print(f"  Rules loaded: {len(bandit.get_rules())}")
    print(f"  Findings: {len(findings)}")
    for f in findings:
        print(f"    [{f.severity}] {f.rule_id}: L{f.line_number} — {f.description}")

    # Direction A.2: Semgrep scan
    print("\n[A.2] Semgrep-style scan (12 rules)")
    semgrep = SemgrepRuleAdapter()
    semgrep_findings = semgrep.scan_text(vulnerable_code, filename="app.py")

    print(f"  Rules loaded: {len(semgrep.get_rules())}")
    print(f"  Findings: {len(semgrep_findings)}")
    for f in semgrep_findings:
        print(f"    [{f.severity}] {f.rule_id}: L{f.line_number} — {f.description}")

    # Direction A.3: SARIF report generation
    all_findings = findings + semgrep_findings
    print(f"\n[A.3] SARIF v2.1.0 Report Generation")
    reporter = CIReporter(tool_name="KiraCode-SAST", tool_version="0.2.0")
    sarif = reporter.generate_sarif(all_findings, repo_uri="file:///demo-project")

    sarif_json = json.loads(sarif.to_json())
    rules_count = len(sarif_json["runs"][0]["tool"]["driver"]["rules"])
    results_count = len(sarif_json["runs"][0]["results"])
    print(f"  SARIF rules: {rules_count}")
    print(f"  SARIF results: {results_count}")

    summary = reporter.generate_summary(all_findings)
    print(f"  Summary: {json.dumps(summary, indent=4)}")

    # Save SARIF to file
    sarif_path = "output_sarif.json"
    with open(sarif_path, "w", encoding="utf-8") as f:
        f.write(sarif.to_json(indent=2))
    print(f"  SARIF saved to: {sarif_path}")


def demo_direction_b():
    """Direction B: CVE Intelligence RAG."""
    print(f"\n{SEPARATOR}")
    print("Direction B: CVE Intelligence RAG")
    print(SEPARATOR)

    from kiracode.rag.cve_indexer import CVEIndexer
    from kiracode.rag.cve_retriever import CVERetriever

    indexer = CVEIndexer()
    retriever = CVERetriever(indexer)

    # B.1: CVE database summary
    print("\n[B.1] CVE Database Summary")
    summary = indexer.summary()
    print(f"  Total entries: {summary['total_entries']}")
    print(f"  By severity: {json.dumps(summary['by_severity'])}")
    print(f"  Average CVSS: {summary['avg_cvss']}")

    # B.2: Search by component
    print("\n[B.2] Search by component: 'flask'")
    flask_cves = indexer.search(components=["flask"])
    for cve in flask_cves:
        print(f"  {cve.cve_id} (CVSS {cve.cvss_score}) — {cve.description[:80]}...")

    # B.3: Search by tags
    print("\n[B.3] Search by tags: ['rce', 'command-injection']")
    rce_cves = indexer.search(tags=["rce", "command-injection"])
    for cve in rce_cves:
        print(f"  {cve.cve_id} (CVSS {cve.cvss_score}) — {cve.description[:80]}...")

    # B.4: Risk assessment for a real-world query
    queries = [
        "Build a Flask file upload feature with JWT authentication",
        "Deploy MinIO object storage with API endpoints",
        "Set up Nginx reverse proxy with HTTP/2 and WebSocket support",
    ]

    for query in queries:
        print(f"\n[B.4] Risk Assessment: \"{query}\"")
        risk = retriever.assess_risk(query)
        print(f"  Keywords: {risk.query_keywords}")
        print(f"  Risk Level: {risk.risk_level}")
        print(f"  Related CVEs: {len(risk.related_cves)}")
        for cve in risk.related_cves[:3]:
            print(f"    {cve.cve_id} (CVSS {cve.cvss_score}, {cve.severity})")
        if risk.warnings:
            print(f"  Warnings:")
            for w in risk.warnings:
                print(f"    ! {w}")
        if risk.mitigations:
            print(f"  Mitigations:")
            for m in risk.mitigations:
                print(f"    > {m}")


def demo_direction_c():
    """Direction C: PentestAgent — ATT&CK script generation."""
    print(f"\n{SEPARATOR}")
    print("Direction C: PentestAgent — MITRE ATT&CK Script Generation")
    print(SEPARATOR)

    import asyncio
    from kiracode.agents.pentest_generator import PentestAgent, ATTCK_TECHNIQUES
    from kiracode.agents.base import AgentContext, AgentState

    # C.1: Knowledge base overview
    print("\n[C.1] MITRE ATT&CK Knowledge Base")
    for tech in ATTCK_TECHNIQUES:
        print(f"  {tech.technique_id}: {tech.name}")
        print(f"    Tactics: {', '.join(tech.tactics)}")
        print(f"    Template: {tech.test_template}")

    # C.2: Plan phase — technique selection
    async def run_pentest_demo():
        agent = PentestAgent()

        scenarios = [
            ("Scan my web application running Flask and Django for vulnerabilities", {
                "target_host": "192.168.1.100",
                "target_ports": ["80", "443", "8080"],
            }),
            ("Test for default credentials and authentication bypass on admin panel", {
                "target_host": "10.0.0.50",
                "target_ports": ["80", "443"],
            }),
            ("Check if DNS exfiltration and data tunneling is possible", {
                "target_host": "172.16.0.10",
                "target_ports": ["53", "80"],
            }),
        ]

        for query, meta in scenarios:
            print(f"\n[C.2] Scenario: \"{query}\"")
            ctx = AgentContext(query=query, metadata=meta)
            result = await agent.run(ctx)

            if result.state == AgentState.DONE:
                techniques = result.output.get("selected_techniques", [])
                scripts = result.output.get("scripts", [])
                safe = result.output.get("safe_scripts", 0)
                review = result.output.get("review_passed", False)

                print(f"  Selected techniques: {len(techniques)}")
                for t in techniques:
                    print(f"    {t['technique_id']}: {t['name']}")
                print(f"  Scripts generated: {len(scripts)}")
                print(f"  Safe scripts: {safe}/{len(scripts)}")
                print(f"  Review passed: {review}")

                # Show first script snippet
                if scripts:
                    snippet = scripts[0]["script"][:300]
                    print(f"  Script preview ({scripts[0]['filename']}):")
                    for line in snippet.split("\n")[:8]:
                        print(f"    {line}")
                    print("    ...")
            else:
                print(f"  Agent state: {result.state}")

    asyncio.run(run_pentest_demo())


def main():
    print("KiraCode Security Deep Transformation Demo")
    print(f"Directions: DevSecOps SAST + PentestAgent\n")

    demo_direction_a()
    # Direction B (CVE RAG) skipped to avoid security software interception
    demo_direction_c()

    print(f"\n{SEPARATOR}")
    print("Security Deep Transformation Demo Complete!")
    print(SEPARATOR)


if __name__ == "__main__":
    main()
