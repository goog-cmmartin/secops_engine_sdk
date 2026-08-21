"""Desktop UI Widgets for SecOps Client."""

from clients.desktop.widgets.event_investigation_widget import EventInvestigationWidget
from clients.desktop.widgets.udm_search_widget import UdmSearchWidget
from clients.desktop.widgets.cases_widget import CasesWidget
from clients.desktop.widgets.playbooks_widget import PlaybooksWidget
from clients.desktop.widgets.integrations_jobs_widget import IntegrationsJobsWidget
from clients.desktop.widgets.detections_widget import DetectionsWidget
from clients.desktop.widgets.feeds_parsers_widget import FeedsParsersWidget
from clients.desktop.widgets.dashboards_widget import DashboardsWidget
from clients.desktop.widgets.settings_widget import SettingsWidget

__all__ = [
    "EventInvestigationWidget",
    "UdmSearchWidget",
    "CasesWidget",
    "PlaybooksWidget",
    "IntegrationsJobsWidget",
    "DetectionsWidget",
    "FeedsParsersWidget",
    "DashboardsWidget",
    "SettingsWidget",
]
