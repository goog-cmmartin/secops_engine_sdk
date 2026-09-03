"""Operations and tenant configuration audit runbooks."""

from runbooks.operations.tenant_settings_audit import generate_tenant_settings_report
from runbooks.operations.data_table_inventory import generate_data_table_inventory_report
from runbooks.operations.yara_l_rules_audit import generate_yara_l_rules_audit_report
from runbooks.operations.soar_playbook_inventory import generate_playbook_inventory_report
from runbooks.operations.curated_detections_health import (
    generate_curated_detections_health_report,
    print_curated_detections_health_console,
)
from runbooks.operations.soar_playbook_health import (
    generate_soar_playbook_health_report,
    print_soar_playbook_health_console,
)

__all__ = [
    "generate_tenant_settings_report",
    "generate_data_table_inventory_report",
    "generate_yara_l_rules_audit_report",
    "generate_playbook_inventory_report",
    "generate_curated_detections_health_report",
    "print_curated_detections_health_console",
    "generate_soar_playbook_health_report",
    "print_soar_playbook_health_console",
]
