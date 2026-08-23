#!/usr/bin/env python3
"""
Verify proto schema availability and query capability mappings.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.query_capabilities import (
    UDM_SEARCH_TABLES,
    DASHBOARD_QUERY_PROTOS,
    UDM_TO_PROTO_MAP,
    DASHBOARD_TO_PROTO_MAP,
    get_query_capabilities,
    get_proto_file,
    format_capability_help,
)


def main():
    print("=" * 70)
    print("Proto Schema Verification")
    print("=" * 70)
    
    # Check proto directory exists
    proto_dir = Path(__file__).parent.parent / "protos" / "secops_protos" / "protos"
    if not proto_dir.exists():
        print(f"\n❌ ERROR: Proto directory not found: {proto_dir}")
        print("\nRun: git submodule update --init --recursive")
        return 1
    
    print(f"\n✓ Proto directory: {proto_dir}")
    
    # List available protos
    available_protos = set()
    for proto_file in proto_dir.glob("*.proto"):
        available_protos.add(proto_file.name)
    
    print(f"\n✓ Found {len(available_protos)} proto files:")
    for proto in sorted(available_protos):
        print(f"  • {proto}")
    
    # Verify UDM Search mappings
    print("\n" + "=" * 70)
    print("UDM Search Capabilities")
    print("=" * 70)
    print(format_capability_help("udm_search"))
    
    print("\n\nProto File Mappings:")
    missing = []
    for table in sorted(UDM_SEARCH_TABLES):
        proto_file = UDM_TO_PROTO_MAP[table]
        status = "✓" if proto_file in available_protos else "✗"
        print(f"  {status} {table:15} → {proto_file}")
        if proto_file not in available_protos:
            missing.append((table, proto_file))
    
    # Verify Dashboard Query mappings
    print("\n" + "=" * 70)
    print("Dashboard Query Capabilities")
    print("=" * 70)
    print(format_capability_help("dashboard_query"))
    
    print("\n\nProto File Mappings:")
    for proto in sorted(DASHBOARD_QUERY_PROTOS):
        proto_file = DASHBOARD_TO_PROTO_MAP[proto]
        status = "✓" if proto_file in available_protos else "✗"
        print(f"  {status} {proto:20} → {proto_file}")
        if proto_file not in available_protos:
            missing.append((proto, proto_file))
    
    # Summary
    print("\n" + "=" * 70)
    if missing:
        print(f"❌ FAILED: {len(missing)} missing proto files:")
        for name, proto_file in missing:
            print(f"  • {name} requires {proto_file}")
        return 1
    else:
        print("✓ SUCCESS: All proto schema mappings verified")
        return 0


if __name__ == "__main__":
    sys.exit(main())
