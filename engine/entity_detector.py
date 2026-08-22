"""Automatic indicator detection and UDM / Graph / IoC query mapping.

Parses untyped strings (IPs, hashes, emails, hostnames, URLs, MACs, domains, usernames)
and returns structured query fragments for UDM Event Search, UDM Entity Graph Search,
and Enterprise IoC Intelligence searches.
"""

from dataclasses import dataclass
from enum import Enum
import ipaddress
import re
from typing import Optional

from engine.domain import EntityType


class EntityCategory(str, Enum):
    FILE = "FILE"
    ASSET = "ASSET"
    USER = "USER"
    DOMAIN_NAME = "DOMAIN_NAME"
    NETWORK = "NETWORK"
    RESOURCE = "RESOURCE"
    URL = "URL"


@dataclass(frozen=True)
class DetectedEntity:
    """Represents a detected indicator and its canonical search representations."""

    raw_value: str
    entity_type: EntityType
    category: EntityCategory
    graph_field: str
    graph_query: str
    event_query: str
    ioc_value_type: Optional[str] = None


def detect_entity(value: str) -> DetectedEntity:
    """Detects indicator type from an untyped string and produces canonical graph & event queries.

    Args:
        value: Untyped string identifier (e.g. IP, file hash, email, hostname, domain, username).

    Returns:
        DetectedEntity containing the typed entity, graph query, event query, and IoC valueType.
    """
    val = value.strip()
    if not val:
        raise ValueError("Cannot detect entity type from an empty string.")

    # 1. IP Address (IPv4 or IPv6)
    try:
        ipaddress.ip_address(val)
        return DetectedEntity(
            raw_value=val,
            entity_type=EntityType.IP,
            category=EntityCategory.ASSET,
            graph_field="graph.entity.ip",
            graph_query=f'graph.entity.ip = "{val}"',
            event_query=f'principal.ip = "{val}" OR target.ip = "{val}" OR src.ip = "{val}"',
            ioc_value_type="IP_ADDRESS",
        )
    except ValueError:
        pass

    # 2. File Hashes (MD5: 32, SHA1: 40, SHA256: 64)
    if re.fullmatch(r"[a-fA-F0-9]{32}", val):
        val_lower = val.lower()
        return DetectedEntity(
            raw_value=val,
            entity_type=EntityType.MD5,
            category=EntityCategory.FILE,
            graph_field="graph.entity.file.md5",
            graph_query=f'graph.entity.file.md5 = "{val_lower}"',
            event_query=f'target.file.md5 = "{val_lower}" OR principal.process.file.md5 = "{val_lower}"',
            ioc_value_type="HASH_MD5",
        )
    if re.fullmatch(r"[a-fA-F0-9]{40}", val):
        val_lower = val.lower()
        return DetectedEntity(
            raw_value=val,
            entity_type=EntityType.SHA1,
            category=EntityCategory.FILE,
            graph_field="graph.entity.file.sha1",
            graph_query=f'graph.entity.file.sha1 = "{val_lower}"',
            event_query=f'target.file.sha1 = "{val_lower}" OR principal.process.file.sha1 = "{val_lower}"',
            ioc_value_type="HASH_SHA1",
        )
    if re.fullmatch(r"[a-fA-F0-9]{64}", val):
        val_lower = val.lower()
        return DetectedEntity(
            raw_value=val,
            entity_type=EntityType.SHA256,
            category=EntityCategory.FILE,
            graph_field="graph.entity.file.sha256",
            graph_query=f'graph.entity.file.sha256 = "{val_lower}"',
            event_query=f'target.file.sha256 = "{val_lower}" OR principal.process.file.sha256 = "{val_lower}"',
            ioc_value_type="HASH_SHA256",
        )

    # 3. MAC Address (e.g. 00:1A:2B:3C:4D:5E or 00-1A-2B-3C-4D-5E)
    if re.fullmatch(r"([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})", val):
        val_lower = val.lower()
        return DetectedEntity(
            raw_value=val,
            entity_type=EntityType.MAC,
            category=EntityCategory.ASSET,
            graph_field="graph.entity.mac",
            graph_query=f'graph.entity.mac = "{val_lower}"',
            event_query=f'principal.mac = "{val_lower}" OR target.mac = "{val_lower}" OR src.mac = "{val_lower}"',
            ioc_value_type="MAC_ADDRESS",
        )

    # 4. Email Address (e.g. user@domain.com)
    if re.fullmatch(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", val):
        val_lower = val.lower()
        return DetectedEntity(
            raw_value=val,
            entity_type=EntityType.EMAIL,
            category=EntityCategory.USER,
            graph_field="graph.entity.user.email_addresses",
            graph_query=f'graph.entity.user.email_addresses = "{val_lower}" nocase',
            event_query=f'principal.user.email_addresses = "{val_lower}" OR target.user.email_addresses = "{val_lower}"',
            ioc_value_type="EMAIL_ADDRESS",
        )

    # 5. URL / Web Resource (e.g. http://... or https://...)
    if val.startswith("http://") or val.startswith("https://"):
        return DetectedEntity(
            raw_value=val,
            entity_type=EntityType.URL,
            category=EntityCategory.URL,
            graph_field="graph.entity.url",
            graph_query=f'graph.entity.url = "{val}"',
            event_query=f'target.url = "{val}" OR network.http.referral_url = "{val}"',
            ioc_value_type="URL",
        )

    # 6. Windows Security Identifier (SID) (e.g. S-1-5-21-...)
    if re.fullmatch(r"S-1-[0-59]-\d{2}-\d{8,10}-\d{8,10}-\d{8,10}-\d{3,5}", val, re.IGNORECASE):
        return DetectedEntity(
            raw_value=val,
            entity_type=EntityType.WINDOWS_SID,
            category=EntityCategory.USER,
            graph_field="graph.entity.user.windows_sid",
            graph_query=f'graph.entity.user.windows_sid = "{val}"',
            event_query=f'principal.user.windows_sid = "{val}" OR target.user.windows_sid = "{val}"',
            ioc_value_type=None,
        )

    # 7. Cloud Resource Name (e.g. //compute.googleapis.com/... or projects/...)
    if val.startswith("//") or val.startswith("projects/"):
        return DetectedEntity(
            raw_value=val,
            entity_type=EntityType.RESOURCE,
            category=EntityCategory.RESOURCE,
            graph_field="graph.entity.resource.name",
            graph_query=f'graph.entity.resource.name = "{val}"',
            event_query=f'target.resource.name = "{val}"',
            ioc_value_type=None,
        )

    # 8. Domain Name (FQDN) (e.g. evil.example.com)
    if re.fullmatch(r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)+$", val):
        val_lower = val.lower()
        return DetectedEntity(
            raw_value=val,
            entity_type=EntityType.DOMAIN,
            category=EntityCategory.DOMAIN_NAME,
            graph_field="graph.entity.domain.name",
            graph_query=f'graph.entity.domain.name = "{val_lower}"',
            event_query=f'network.dns.questions.name = "{val_lower}" OR target.hostname = "{val_lower}"',
            ioc_value_type="DOMAIN_NAME",
        )

    # 9. Hostname / Asset Name (e.g. WIN-DESKTOP-01, server02, SRV-DC-01$)
    if re.fullmatch(r"^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?\$?$", val):
        return DetectedEntity(
            raw_value=val,
            entity_type=EntityType.HOSTNAME,
            category=EntityCategory.ASSET,
            graph_field="graph.entity.hostname",
            graph_query=f'graph.entity.hostname = "{val}" nocase',
            event_query=f'principal.hostname = "{val}" nocase OR target.hostname = "{val}" nocase',
            ioc_value_type="HOSTNAME",
        )

    # 10. Fallback: User ID / Username (e.g. jdoe, admin_user)
    return DetectedEntity(
        raw_value=val,
        entity_type=EntityType.USER,
        category=EntityCategory.USER,
        graph_field="graph.entity.user.userid",
        graph_query=f'graph.entity.user.userid = "{val}" nocase',
        event_query=f'principal.user.userid = "{val}" nocase OR target.user.userid = "{val}" nocase',
        ioc_value_type="USER_ID",
    )
