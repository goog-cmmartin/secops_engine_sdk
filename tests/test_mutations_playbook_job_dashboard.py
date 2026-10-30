"""Unit tests for Playbook, Job, and Native Dashboard mutation workflows & adapter methods."""

import json
from unittest.mock import MagicMock

from adapters.google_secops import GoogleSecOpsAdapter
from engine.facade import SecOpsEngine


def _make_engine():
    adapter = MagicMock(spec=GoogleSecOpsAdapter)
    engine = SecOpsEngine(adapter=adapter)
    return engine, adapter


def test_save_playbook_syncs_category_name_and_id():
    engine, adapter = _make_engine()
    adapter.get_playbook_categories.return_value = [
        {"id": 9, "name": "GSA"},
        {"id": 1, "name": "Default"},
    ]
    adapter.save_playbook.side_effect = lambda p: p

    # Case 1: categoryId=9 provided, categoryName is None -> auto-populates categoryName="GSA"
    saved1 = engine.save_playbook({"name": "PB1", "categoryId": 9, "categoryName": None})
    assert saved1["categoryName"] == "GSA"
    assert saved1["categoryId"] == 9

    # Case 2: category_name override passed -> auto-populates both categoryId and categoryName
    saved2 = engine.save_playbook({"name": "PB2"}, category_name="GSA", is_enabled=True)
    assert saved2["categoryName"] == "GSA"
    assert saved2["categoryId"] == 9
    assert saved2["isEnabled"] is True


def test_update_playbook_widget_updates_html_and_step_param():
    engine, adapter = _make_engine()
    adapter.get_playbook_categories.return_value = [{"id": 9, "name": "GSA"}]
    adapter.save_playbook.side_effect = lambda p: p
    adapter.get_playbook_full_info.return_value = {
        "id": 3109,
        "identifier": "8dc6a7bd-4316-4891-834a-740823ebb428",
        "name": "Case Correlate Case Entities",
        "categoryId": 9,
        "categoryName": None,
        "steps": [
            {
                "identifier": "step-1",
                "name": "Logic Analyst Agent",
                "parameters": [{"name": "User Prompt", "value": "old_prompt"}],
            }
        ],
        "viewsTemplates": [
            {
                "cards": [
                    {
                        "title": "Logic Analyst Agent",
                        "stepIdentifier": "step-1",
                        "type": 3,
                        "widgetDefinition": json.dumps(
                            {"title": "Logic Analyst Agent", "htmlContent": "<div>old</div>"}
                        ),
                    }
                ]
            }
        ],
    }

    res = engine.update_playbook_widget(
        identifier_or_id="8dc6a7bd-4316-4891-834a-740823ebb428",
        html_content="<div>new-widget</div>",
        step_name_or_id="Logic Analyst Agent",
        update_step_parameter="User Prompt",
        update_step_parameter_value="new_prompt",
    )

    assert res["updated_widgets_count"] == 1
    saved = res["saved_playbook"]
    assert saved["categoryName"] == "GSA"
    assert saved["steps"][0]["parameters"][0]["value"] == "new_prompt"
    wdef = json.loads(saved["viewsTemplates"][0]["cards"][0]["widgetDefinition"])
    assert wdef["htmlContent"] == "<div>new-widget</div>"


def test_delete_export_import_playbooks():
    engine, adapter = _make_engine()
    adapter.get_playbook_menu_cards.return_value = [
        {"id": 3109, "identifier": "uuid-3109", "name": "My Playbook"}
    ]
    adapter.delete_playbooks.return_value = {"status": "OK"}
    adapter.export_playbooks.return_value = {"blob": "YmFzZTY0"}
    adapter.import_playbooks.return_value = {"imported": ["uuid-3109"]}

    del_res = engine.delete_playbooks("3109")
    assert del_res["deleted_identifiers"] == ["uuid-3109"]
    adapter.delete_playbooks.assert_called_once_with(["uuid-3109"])

    exp_res = engine.export_playbooks("uuid-3109")
    assert exp_res["blob"] == "YmFzZTY0"

    imp_res = engine.import_playbooks("YmFzZTY0", import_as_duplicates=True)
    assert imp_res["imported"] == ["uuid-3109"]


def test_update_job_and_sync_instances():
    engine, adapter = _make_engine()
    adapter.update_job.return_value = {"name": "jobs/675", "script": "updated_code"}
    adapter.list_job_instances.return_value = [
        {
            "id": 74,
            "name": "projects/p/locations/us/instances/c/integrations/Demoverse/jobs/675/jobInstances/74",
        }
    ]
    adapter.update_job_instance.return_value = {"id": 74, "script": "updated_code"}
    adapter.create_job_instance.return_value = {"id": 75, "displayName": "New Instance"}

    res = engine.update_job(
        integration="Demoverse",
        job_id="675",
        script="updated_code",
        sync_instances=True,
    )
    assert res["synced_instance_count"] == 1
    adapter.update_job.assert_called_once()
    adapter.update_job_instance.assert_called_once()

    created = engine.create_job_instance(
        integration="Demoverse",
        job_id="675",
        instance_payload={"displayName": "New Instance", "enabled": True},
    )
    assert created["id"] == 75


def test_dashboard_and_chart_crud():
    engine, adapter = _make_engine()
    adapter.create_native_dashboard.return_value = {
        "name": "projects/p/locations/us/instances/c/nativeDashboards/nd_100",
        "displayName": "Exec SOC Dashboard",
        "type": "CUSTOM",
    }
    adapter.patch_native_dashboard.return_value = {
        "name": "projects/p/locations/us/instances/c/nativeDashboards/nd_100",
        "displayName": "Exec SOC Dashboard v2",
        "type": "CUSTOM",
    }
    adapter.duplicate_native_dashboard.return_value = {
        "name": "projects/p/locations/us/instances/c/nativeDashboards/nd_101",
        "displayName": "Exec SOC Dashboard Copy",
        "type": "CUSTOM",
    }
    adapter.delete_native_dashboard.return_value = {}
    adapter.add_dashboard_chart.return_value = {
        "dashboardChart": {"name": "projects/p/locations/us/instances/c/dashboardCharts/ch_1"}
    }
    adapter.patch_dashboard_chart.return_value = {"displayName": "Updated Chart"}
    adapter.patch_dashboard_query.return_value = {"query": "metadata.event_type = \"NETWORK_CONNECTION\""}
    adapter.remove_dashboard_chart.return_value = {}

    created = engine.create_dashboard(display_name="Exec SOC Dashboard", description="Initial")
    assert created.id == "nd_100"

    updated = engine.update_dashboard(dashboard_id="nd_100", display_name="Exec SOC Dashboard v2")
    assert updated.display_name == "Exec SOC Dashboard v2"

    dup = engine.duplicate_dashboard(dashboard_id="nd_100", display_name="Exec SOC Dashboard Copy")
    assert dup.id == "nd_101"

    added_chart = engine.add_dashboard_chart(
        dashboard_id="nd_100",
        display_name="Logins",
        query='metadata.event_type = "USER_LOGIN"',
    )
    assert "dashboardChart" in added_chart

    upd_chart = engine.update_dashboard_chart(
        chart_id="ch_1",
        display_name="Updated Chart",
        query_id="q_1",
        query='metadata.event_type = "NETWORK_CONNECTION"',
    )
    assert "updated_chart" in upd_chart
    assert "updated_query" in upd_chart

    engine.remove_dashboard_chart(dashboard_id="nd_100", chart_id="ch_1")
    adapter.remove_dashboard_chart.assert_called_once_with(dashboard_id="nd_100", chart_id="ch_1")

    del_dash = engine.delete_dashboard(dashboard_id="nd_100")
    assert del_dash["deleted_dashboard_id"] == "nd_100"
