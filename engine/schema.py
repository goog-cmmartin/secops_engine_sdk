"""SecOps Schema & Field Canonicalizer.

Provides explicit, schema-backed UDM field resolution and validation.
Avoids naive arbitrary string transformations by maintaining verified canonical mappings.
"""

from typing import Dict, Optional, Set

# Known canonical UDM query dialect fields
CANONICAL_UDM_FIELDS: Set[str] = {
    # Metadata
    "metadata.event_type",
    "metadata.event_timestamp",
    "metadata.ingested_timestamp",
    "metadata.vendor_name",
    "metadata.product_name",
    "metadata.product_event_type",
    "metadata.product_version",
    "metadata.description",
    "metadata.log_type",
    "metadata.product_deployment_id",
    "metadata.id",
    "metadata.enrichment_state",
    # Principal
    "principal.hostname",
    "principal.ip",
    "principal.port",
    "principal.mac",
    "principal.asset_id",
    "principal.location.country_or_region",
    "principal.user.userid",
    "principal.user.user_display_name",
    "principal.user.email_addresses",
    "principal.process.file.sha256",
    "principal.process.file.md5",
    "principal.process.file.full_path",
    "principal.process.command_line",
    "principal.process.pid",
    # Target
    "target.hostname",
    "target.ip",
    "target.port",
    "target.mac",
    "target.asset_id",
    "target.location.country_or_region",
    "target.user.userid",
    "target.user.user_display_name",
    "target.user.email_addresses",
    "target.process.file.sha256",
    "target.process.file.md5",
    "target.process.file.full_path",
    "target.process.command_line",
    "target.process.pid",
    "target.file.sha256",
    "target.file.md5",
    "target.file.full_path",
    # Src & About
    "src.ip",
    "src.port",
    "src.hostname",
    "src.user.userid",
    "observer.ip",
    "observer.hostname",
    "intermediary.ip",
    "intermediary.hostname",
    "about.ip",
    "about.hostname",
    "about.user.userid",
    # Network
    "network.dns.questions.name",
    "network.http.response.response_code",
    "network.http.request_url",
    "network.http.method",
    "network.application_protocol",
    "network.ip_protocol",
    # Security Result
    "security_result.action",
    "security_result.severity",
    "security_result.category",
    "security_result.summary",
    "security_result.rule_name",
    "security_result.rule_id",
}

# Verified mappings from JSON camelCase attributes or shorthand aliases to canonical UDM query fields
CAMEL_TO_CANONICAL_UDM: Dict[str, str] = {
    # Metadata aliases
    "metadata.eventType": "metadata.event_type",
    "metadata.eventTimestamp": "metadata.event_timestamp",
    "metadata.ingestedTimestamp": "metadata.ingested_timestamp",
    "metadata.vendorName": "metadata.vendor_name",
    "metadata.productName": "metadata.product_name",
    "metadata.productEventType": "metadata.product_event_type",
    "metadata.productVersion": "metadata.product_version",
    "metadata.logType": "metadata.log_type",
    "metadata.productDeploymentId": "metadata.product_deployment_id",
    "metadata.enrichmentState": "metadata.enrichment_state",
    # Principal aliases
    "principal.assetId": "principal.asset_id",
    "principal.user.userDisplayName": "principal.user.user_display_name",
    "principal.user.emailAddresses": "principal.user.email_addresses",
    "principal.process.file.fullPath": "principal.process.file.full_path",
    "principal.process.commandLine": "principal.process.command_line",
    # Target aliases
    "target.assetId": "target.asset_id",
    "target.user.userDisplayName": "target.user.user_display_name",
    "target.user.emailAddresses": "target.user.email_addresses",
    "target.process.file.fullPath": "target.process.file.full_path",
    "target.process.commandLine": "target.process.command_line",
    "target.file.fullPath": "target.file.full_path",
    # Network aliases
    "network.http.response.responseCode": "network.http.response.response_code",
    "network.httpRequestUrl": "network.http.request_url",
    "network.http.requestUrl": "network.http.request_url",
    "network.applicationProtocol": "network.application_protocol",
    "network.ipProtocol": "network.ip_protocol",
    # Security Result aliases
    "security_result.ruleName": "security_result.rule_name",
    "security_result.ruleId": "security_result.rule_id",
    "securityResult.action": "security_result.action",
    "securityResult.severity": "security_result.severity",
    "securityResult.category": "security_result.category",
}


def canonicalize_udm_field(field_path: str) -> str:
    """Resolves a field path into canonical UDM query dialect format using explicit schema knowledge.

    If the field is already canonical, it is returned directly.
    If it is a known camelCase or alias path, the canonical mapping is returned.
    If unknown, converts camelCase segments to snake_case while preserving path structure.
    """
    cleaned = field_path.strip()

    # 1. Direct canonical match
    if cleaned in CANONICAL_UDM_FIELDS:
        return cleaned

    # 2. Known mapping lookup
    if cleaned in CAMEL_TO_CANONICAL_UDM:
        return CAMEL_TO_CANONICAL_UDM[cleaned]

    # 3. Fallback segment normalization with structural preservation
    import re
    parts = cleaned.split(".")
    normalized_parts = [re.sub(r"(?<!^)(?=[A-Z])", "_", p).lower() for p in parts]
    candidate = ".".join(normalized_parts)

    return candidate
