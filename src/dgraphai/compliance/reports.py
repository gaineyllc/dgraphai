"""
Compliance report generator.
Produces pre-built reports that satisfy auditor requirements for
GDPR, HIPAA, SOC2, and general security posture.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID


REPORT_DEFINITIONS = {
    "gdpr_data_inventory": {
        "title":       "GDPR Personal Data Inventory",
        "description": "Inventory of all files containing personal data, classified by type and location",
        "queries": {
            "pii_files": """
                MATCH (f:File)
                WHERE f.pii_detected = true AND f.tenant_id = $__tid
                RETURN f.path, f.pii_types, f.size_bytes, f.modified,
                       f.sensitivity_level, f.file_category
                ORDER BY f.sensitivity_level DESC, f.modified DESC
            """,
            "pii_by_type": """
                MATCH (f:File)
                WHERE f.pii_detected = true AND f.tenant_id = $__tid
                UNWIND split(coalesce(f.pii_types,''), ',') AS pii_type
                WITH trim(pii_type) AS pt WHERE pt <> ''
                RETURN pt AS pii_type, count(*) AS file_count
                ORDER BY file_count DESC
            """,
            "pii_by_location": """
                MATCH (f:File)
                WHERE f.pii_detected = true AND f.tenant_id = $__tid
                RETURN f.share AS location, count(*) AS file_count,
                       sum(f.size_bytes) AS total_bytes
                ORDER BY file_count DESC
            """,
        },
    },
    "hipaa_phi_inventory": {
        "title":       "HIPAA PHI Data Inventory",
        "description": "Inventory of files potentially containing Protected Health Information",
        "queries": {
            "phi_files": """
                MATCH (f:File)
                WHERE f.pii_detected = true
                  AND (f.pii_types CONTAINS 'ssn' OR f.pii_types CONTAINS 'medical'
                       OR f.pii_types CONTAINS 'phone' OR f.sensitivity_level = 'high')
                  AND f.tenant_id = $__tid
                RETURN f.path, f.pii_types, f.sensitivity_level, f.modified
                ORDER BY f.modified DESC LIMIT 1000
            """,
        },
    },
    "soc2_evidence": {
        "title":       "SOC2 Security Evidence Pack",
        "description": "Evidence for SOC2 Type II audit — access controls, encryption, monitoring",
        "queries": {
            "eol_software": """
                MATCH (f:File)
                WHERE f.eol_status = 'eol' AND f.tenant_id = $__tid
                RETURN f.name, f.file_version, f.company_name, f.path
                ORDER BY f.name
            """,
            "unsigned_executables": """
                MATCH (f:File)
                WHERE f.file_category = 'executable'
                  AND f.signed = false AND f.tenant_id = $__tid
                RETURN f.name, f.path, f.company_name
            """,
            "secrets_in_code": """
                MATCH (f:File)
                WHERE f.contains_secrets = true AND f.tenant_id = $__tid
                RETURN f.path, f.secret_types, f.code_language
            """,
            "expiring_certs": """
                MATCH (f:File)
                WHERE f.file_category = 'certificate'
                  AND f.days_until_expiry < 90 AND f.tenant_id = $__tid
                RETURN f.cert_subject, f.cert_issuer, f.days_until_expiry, f.path
                ORDER BY f.days_until_expiry
            """,
            "critical_cves": """
                MATCH (f:File)-[:HAS_VULNERABILITY]->(v:Vulnerability)
                WHERE v.cvss_severity IN ['critical','high']
                  AND f.tenant_id = $__tid
                RETURN f.name AS app, v.cve_id, v.cvss_score, v.cvss_severity,
                       v.exploit_available, v.actively_exploited
                ORDER BY v.cvss_score DESC
            """,
        },
    },
    "pii_exposure": {
        "title":       "PII Exposure Assessment",
        "description": "Assessment of PII exposure risk across all file shares",
        "queries": {
            "high_risk":   "MATCH (f:File) WHERE f.sensitivity_level = 'high' AND f.pii_detected = true AND f.tenant_id = $__tid RETURN f.path, f.pii_types LIMIT 500",
            "by_category": "MATCH (f:File) WHERE f.pii_detected = true AND f.tenant_id = $__tid RETURN f.file_category AS category, count(*) AS count ORDER BY count DESC",
        },
    },
    "certificate_expiry": {
        "title":       "Certificate Expiry Report",
        "description": "All certificates with expiry status",
        "queries": {
            "expiring_30d": "MATCH (f:File) WHERE f.file_category = 'certificate' AND f.days_until_expiry < 30 AND f.tenant_id = $__tid RETURN f.cert_subject, f.cert_issuer, f.days_until_expiry, f.cert_fingerprint ORDER BY f.days_until_expiry",
            "already_expired": "MATCH (f:File) WHERE f.file_category = 'certificate' AND f.cert_is_expired = true AND f.tenant_id = $__tid RETURN f.cert_subject, f.cert_issuer, f.cert_valid_to, f.path",
        },
    },
    "secrets_exposure": {
        "title":       "Secrets Exposure Report",
        "description": "Files containing API keys, passwords, tokens, or certificates",
        "queries": {
            "secrets": "MATCH (f:File) WHERE f.contains_secrets = true AND f.tenant_id = $__tid RETURN f.path, f.secret_types, f.file_category, f.modified ORDER BY f.modified DESC LIMIT 500",
        },
    },
}


class ReportGenerator:
    """Generates compliance reports from the graph database."""

    async def generate(
        self,
        report_type: str,
        tenant_id: UUID,
        backend: Any,
        output_format: str = "json",
    ) -> dict[str, Any]:
        """
        Generate a compliance report.
        Returns a dict with findings, summary counts, and formatted output.
        """
        definition = REPORT_DEFINITIONS.get(report_type)
        if not definition:
            raise ValueError(f"Unknown report type: {report_type!r}")

        findings:     dict[str, list] = {}
        summary:      dict[str, int]  = {}
        total_findings = 0

        async with backend:
            for section, cypher in definition["queries"].items():
                try:
                    rows = await backend.query(cypher, {}, tenant_id)
                    findings[section] = rows
                    summary[section]  = len(rows)
                    total_findings   += len(rows)
                except Exception as e:
                    findings[section] = []
                    summary[f"{section}_error"] = str(e)

        report = {
            "report_type":   report_type,
            "title":         definition["title"],
            "description":   definition["description"],
            "tenant_id":     str(tenant_id),
            "generated_at":  datetime.now(timezone.utc).isoformat(),
            "total_findings": total_findings,
            "summary":       summary,
            "findings":      findings,
        }

        if output_format == "json":
            return report
        elif output_format == "csv":
            return {"csv": _to_csv(findings), **report}
        else:
            return report


def _to_csv(findings: dict[str, list]) -> dict[str, str]:
    """Convert findings sections to CSV strings."""
    import csv, io
    result = {}
    for section, rows in findings.items():
        if not rows:
            continue
        buf    = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        result[section] = buf.getvalue()
    return result
