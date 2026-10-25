import json
import os
import subprocess
import unittest

class TestChromeExtension(unittest.TestCase):
    def setUp(self):
        self.ext_dir = os.path.join(os.path.dirname(__file__), "..", "clients", "chrome_extension")
        self.manifest_path = os.path.join(self.ext_dir, "manifest.json")

    def test_manifest_structure(self):
        self.assertTrue(os.path.exists(self.manifest_path), "manifest.json must exist")
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        self.assertEqual(manifest.get("manifest_version"), 3)
        self.assertIn("sidePanel", manifest.get("permissions", []))
        self.assertIn("webNavigation", manifest.get("permissions", []))
        self.assertIn("identity", manifest.get("permissions", []))
        self.assertIn("storage", manifest.get("permissions", []))
        
        # Verify host permissions for chronicle and docs
        host_perms = manifest.get("host_permissions", [])
        self.assertTrue(any("chronicle.security" in p for p in host_perms))
        self.assertTrue(any("docs.cloud.google.com" in p for p in host_perms))

    def test_required_files_exist(self):
        required_files = [
            "background.js",
            "sidepanel/sidepanel.html",
            "sidepanel/sidepanel.css",
            "sidepanel/sidepanel.js",
            "sidepanel/marked.min.js",
            "content/content_script.js",
            "content/dom_utils.js",
            "content/extractors/udm_search.js",
            "content/extractors/rules_editor.js",
            "content/extractors/case_view.js",
            "content/extractors/docs_view.js",
            "content/extractors/settings_view.js",
            "content/extractors/logs_explorer.js",
            "services/prompts.js",
            "services/auth_service.js",
            "services/gemini_api.js",
            "services/mcp_client.js",
            "services/skill_manager.js",
            "assets/icon-16.png",
            "assets/icon-48.png",
            "assets/icon-128.png",
            "README.md"
        ]
        for rel_path in required_files:
            full_path = os.path.join(self.ext_dir, rel_path)
            self.assertTrue(os.path.exists(full_path), f"Missing required extension file: {rel_path}")

    def test_unslop_instruction_exists(self):
        prompts_path = os.path.join(self.ext_dir, "services", "prompts.js")
        with open(prompts_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("UNSLOP_INSTRUCTION", content)
        self.assertIn("getSystemInstruction", content)
        self.assertIn("Superficial -ing phrases", content)

    def test_anti_mock_compliance(self):
        # Scan extension files for banned mock terms
        banned = ["mock", "dummy", "fake", "sampledata", "sample_data", "testdata", "test_data"]
        for root, _, files in os.walk(self.ext_dir):
            for file in files:
                if file.endswith((".js", ".html", ".css", ".json")):
                    filepath = os.path.join(root, file)
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read().lower()
                        for term in banned:
                            self.assertNotIn(term, content, f"Found banned term '{term}' in {filepath}")


    def test_new_features_contracts(self):
        # 1. MCP Client has source extraction and abort support
        mcp_path = os.path.join(self.ext_dir, "services", "mcp_client.js")
        with open(mcp_path, "r", encoding="utf-8") as f:
            mcp_code = f.read()
        self.assertIn("extractDocSources", mcp_code)
        self.assertIn("signal", mcp_code)

        # 2. Gemini API has multimodal and abort support
        api_path = os.path.join(self.ext_dir, "services", "gemini_api.js")
        with open(api_path, "r", encoding="utf-8") as f:
            api_code = f.read()
        self.assertIn("abortSignal", api_code)
        self.assertIn("inlineData", api_code)
        self.assertIn("onSources", api_code)

        # 3. Sidepanel has screen capture and stop button logic
        sp_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.js")
        with open(sp_path, "r", encoding="utf-8") as f:
            sp_code = f.read()
        self.assertIn("captureVisibleTab", sp_code)
        self.assertIn("currentAbortController", sp_code)
        self.assertIn("renderSources", sp_code)


    def test_skill_manager_contract(self):
        sm_path = os.path.join(self.ext_dir, "services", "skill_manager.js")
        with open(sm_path, "r", encoding="utf-8") as f:
            sm_code = f.read()
        self.assertIn("SecOpsSkillManager", sm_code)
        self.assertIn("parseSkillMarkdown", sm_code)
        self.assertIn("getSkills", sm_code)
        self.assertIn("getEnabledSkills", sm_code)
        self.assertIn("saveSkill", sm_code)
        self.assertIn("deleteSkill", sm_code)
        self.assertIn("importFromUrl", sm_code)
        self.assertIn("getAmbientSkills", sm_code)
        self.assertIn("getOnDemandSkills", sm_code)
        self.assertIn("findSkillByCommand", sm_code)
        self.assertIn("/grill-me", sm_code)

        # Check prompts.js uses ambientSkills and invokedSkill
        prompts_path = os.path.join(self.ext_dir, "services", "prompts.js")
        with open(prompts_path, "r", encoding="utf-8") as f:
            p_code = f.read()
        self.assertIn("ambientSkills", p_code)
        self.assertIn("invokedSkill", p_code)

        # Check sidepanel.html has ambient pill and slash command menu
        html_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.html")
        with open(html_path, "r", encoding="utf-8") as f:
            html_code = f.read()
        self.assertIn("ambientSkillsPill", html_code)
        self.assertIn("slashCommandMenu", html_code)
        self.assertIn("activeSkillChipContainer", html_code)

        # Check gemini_api.js handles invokedSkill
        api_path = os.path.join(self.ext_dir, "services", "gemini_api.js")
        with open(api_path, "r", encoding="utf-8") as f:
            api_code = f.read()
        self.assertIn("invokedSkill", api_code)


    def test_deep_page_extractors_contract(self):
        # 1. Verify case_view.js extracts caseId, subTab, wallActivity
        cv_path = os.path.join(self.ext_dir, "content", "extractors", "case_view.js")
        with open(cv_path, "r", encoding="utf-8") as f:
            cv_code = f.read()
        self.assertIn("caseId", cv_code)
        self.assertIn("subTab", cv_code)
        self.assertIn("wallActivity", cv_code)

        # 2. Verify settings_view.js extracts email-domains and settings
        sv_path = os.path.join(self.ext_dir, "content", "extractors", "settings_view.js")
        with open(sv_path, "r", encoding="utf-8") as f:
            sv_code = f.read()
        self.assertIn("email-domains", sv_code)
        self.assertIn("settingSlug", sv_code)
        self.assertIn("settingPurpose", sv_code)

        # 3. Verify prompts.js formats deep case and settings context
        p_path = os.path.join(self.ext_dir, "services", "prompts.js")
        with open(p_path, "r", encoding="utf-8") as f:
            p_code = f.read()
        self.assertIn("wallActivity", p_code)
        self.assertIn("settingPurpose", p_code)

        # 4. Verify sidepanel.js has dynamic renderQuickActionChips
        sp_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.js")
        with open(sp_path, "r", encoding="utf-8") as f:
            sp_code = f.read()
        self.assertIn("renderQuickActionChips", sp_code)

    def test_secops_remote_mcp_and_dom_injection(self):
        # 1. Manifest has chronicle OAuth scope
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        scopes = manifest.get("oauth2", {}).get("scopes", [])
        self.assertIn("https://www.googleapis.com/auth/chronicle", scopes)

        # 2. mcp_client.js has SecOps tools and Chronicle endpoint routing
        mcp_path = os.path.join(self.ext_dir, "services", "mcp_client.js")
        with open(mcp_path, "r", encoding="utf-8") as f:
            mcp_code = f.read()
        self.assertIn("chronicle.googleapis.com/mcp", mcp_code)
        self.assertIn("udm_search", mcp_code)
        self.assertIn("create_case_comment", mcp_code)
        self.assertIn("list_case_alerts", mcp_code)
        self.assertIn("getEndpointForTool", mcp_code)

        # 3. DOM injection and content script handlers
        dom_path = os.path.join(self.ext_dir, "content", "dom_utils.js")
        with open(dom_path, "r", encoding="utf-8") as f:
            dom_code = f.read()
        self.assertIn("insertTextIntoActiveInput", dom_code)

        cs_path = os.path.join(self.ext_dir, "content", "content_script.js")
        with open(cs_path, "r", encoding="utf-8") as f:
            cs_code = f.read()
        self.assertIn("INJECT_TEXT_INTO_PAGE", cs_code)

        # 4. Sidepanel action buttons and confirmation safeguards
        sp_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.js")
        with open(sp_path, "r", encoding="utf-8") as f:
            sp_code = f.read()
        self.assertIn("onConfirmAction", sp_code)
        self.assertIn("attachMessageActions", sp_code)
        self.assertIn("secopsCustomerId", sp_code)

    def test_gemini_thought_signature_preservation(self):
        """Verify that gemini_api.js preserves and normalizes cryptographic thought signatures for multi-turn tool calling."""
        gemini_api_path = os.path.join(self.ext_dir, "services", "gemini_api.js")
        with open(gemini_api_path, "r", encoding="utf-8") as f:
            code = f.read()

        # Must track and normalize thought signatures across streaming chunks
        self.assertIn("capturedThoughtSignature", code)
        self.assertIn("thoughtSignature", code)
        self.assertIn("thought_signature", code)
        self.assertIn("capturedModelPart.thoughtSignature = capturedThoughtSignature", code)
        self.assertIn("capturedModelPart.thought_signature = capturedThoughtSignature", code)

    def test_secops_mcp_response_patcher_contract(self):
        """Verify that mcp_client.js patches deeply nested responses for known SecOps tools to prevent 500 schema flattening limits."""
        mcp_path = os.path.join(self.ext_dir, "services", "mcp_client.js")
        with open(mcp_path, "r", encoding="utf-8") as f:
            code = f.read()

        # Master patcher and recursion pruner
        self.assertIn("patchToolResponse", code)
        self.assertIn("pruneDeepObject", code)
        self.assertIn("this.patchToolResponse(toolName, parsedOutput)", code)

        # All 19 high-risk tools targeted by user
        targeted_tools = [
            "create_feed",
            "update_feed",
            "list_security_alerts",
            "list_rule_detections",
            "search_raw_logs",
            "update_security_alert",
            "get_security_alert",
            "get_investigation_by_id",
            "get_alert_latest_investigation",
            "trigger_investigation",
            "run_parser",
            "list_feeds",
            "get_feed",
            "disable_feed",
            "enable_feed",
            "summarize_entity",
            "udm_search",
            "search_entity",
            "generate_synthetic_events",
        ]
        for tool in targeted_tools:
            self.assertIn(f'case "{tool}":', code, f"Missing case for {tool} in patchToolResponse")

        # Verify specialized patch helper methods exist
        self.assertIn("patchListFeeds", code)
        self.assertIn("patchFeedOperation", code)
        self.assertIn("patchUdmSearch", code)
        self.assertIn("patchSearchRawLogs", code)
        self.assertIn("patchSecurityAlerts", code)
        self.assertIn("patchListRuleDetections", code)
        self.assertIn("patchInvestigation", code)
        self.assertIn("patchRunParser", code)
        self.assertIn("patchEntity", code)
        self.assertIn("patchGenerateSyntheticEvents", code)

    def test_help_vs_action_suggestions_and_mcp_routing(self):
        # 1. Manifest version is bumped to 1.2.19
        manifest_path = os.path.join(self.ext_dir, "manifest.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
        self.assertTrue(manifest_data["version"] >= "1.2.19")

        # 2. HTML filter bar elements exist
        html_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.html")
        with open(html_path, "r", encoding="utf-8") as f:
            html_code = f.read()
        self.assertIn('id="suggestionsFilterBar"', html_code)
        self.assertIn('id="filterTabAll"', html_code)
        self.assertIn('id="filterTabHelp"', html_code)
        self.assertIn('id="filterTabAction"', html_code)

        # 3. CSS classes for filter bar and chip categories exist
        css_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.css")
        with open(css_path, "r", encoding="utf-8") as f:
            css_code = f.read()
        self.assertIn(".suggestions-filter-bar", css_code)
        self.assertIn(".filter-tab.active", css_code)
        self.assertIn(".chip.chip-help", css_code)
        self.assertIn(".chip.chip-action", css_code)

        # 4. MCP Client filters tools based on targetMcpMode ("help" vs "action" vs "all")
        mcp_path = os.path.join(self.ext_dir, "services", "mcp_client.js")
        with open(mcp_path, "r", encoding="utf-8") as f:
            mcp_code = f.read()
        self.assertIn('targetMcpMode = "all"', mcp_code)
        self.assertIn('targetMcpMode === "help"', mcp_code)
        self.assertIn('targetMcpMode === "action"', mcp_code)

        # 5. Prompts service injects Help vs Action directives
        prompts_path = os.path.join(self.ext_dir, "services", "prompts.js")
        with open(prompts_path, "r", encoding="utf-8") as f:
            prompts_code = f.read()
        self.assertIn('targetMcpMode === "help"', prompts_code)
        self.assertIn("DEVELOPER KNOWLEDGE MCP", prompts_code)
        self.assertIn('targetMcpMode === "action"', prompts_code)
        self.assertIn("SECOPS MCP", prompts_code)

        # 6. Gemini API forwards targetMcp to getGeminiTools and getSystemInstruction
        api_path = os.path.join(self.ext_dir, "services", "gemini_api.js")
        with open(api_path, "r", encoding="utf-8") as f:
            api_code = f.read()
        self.assertIn('targetMcp = "all"', api_code)
        self.assertIn("getGeminiTools(settings, targetMcp)", api_code)
        self.assertIn("getSystemInstruction(useUnslop, ambientSkills, activeInvokedSkill, targetMcp)", api_code)

        # 7. Sidepanel JS classifies chips with category and targetMcp, and wires filter tabs
        sidepanel_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.js")
        with open(sidepanel_path, "r", encoding="utf-8") as f:
            sidepanel_code = f.read()
        self.assertIn('category: "help"', sidepanel_code)
        self.assertIn('category: "action"', sidepanel_code)
        self.assertIn('targetMcp: "help"', sidepanel_code)
        self.assertIn('targetMcp: "action"', sidepanel_code)
        self.assertIn('currentSuggestionFilter', sidepanel_code)
        self.assertIn('suggestionsFilterBar.addEventListener', sidepanel_code)
        self.assertIn('handleSendMessage(prompt, { targetMcp })', sidepanel_code)

    def test_docs_mcp_normalization_and_pill_state_contract(self):
        # 1. MCP Client auto-normalizes document names in get_documents and patches responses
        mcp_path = os.path.join(self.ext_dir, "services", "mcp_client.js")
        with open(mcp_path, "r", encoding="utf-8") as f:
            mcp_code = f.read()
        self.assertIn('clean.startsWith("documents/")', mcp_code)
        self.assertIn('clean.startsWith("docs.cloud.google.com/")', mcp_code)
        self.assertIn("patchSearchDocuments", mcp_code)
        self.assertIn("patchGetDocuments", mcp_code)
        self.assertIn('case "search_documents":', mcp_code)
        self.assertIn('case "get_documents":', mcp_code)

        # 2. Gemini API tool turns limit increased to 6
        api_path = os.path.join(self.ext_dir, "services", "gemini_api.js")
        with open(api_path, "r", encoding="utf-8") as f:
            api_code = f.read()
        self.assertIn("MAX_TOOL_TURNS = 6", api_code)

        # 3. Sidepanel CSS defines distinct running (pulsing) and completed states
        css_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.css")
        with open(css_path, "r", encoding="utf-8") as f:
            css_code = f.read()
        self.assertIn(".mcp-status-pill.mcp-running", css_code)
        self.assertIn(".mcp-status-pill.mcp-completed", css_code)
        self.assertIn("animation: none", css_code)

        # 4. Sidepanel JS transitions pill from running to completed and provides fallback text
        sidepanel_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.js")
        with open(sidepanel_path, "r", encoding="utf-8") as f:
            sidepanel_code = f.read()
        self.assertIn("mcp-status-pill mcp-running", sidepanel_code)
        self.assertIn("mcp-completed", sidepanel_code)
        self.assertIn("Consulted the documentation sources below for your query", sidepanel_code)

    def test_chronicle_docs_pattern_extraction_and_linking(self):
        # 1. MCP client normalizes bare chronicle/docs/... paths into full canonical URLs
        mcp_path = os.path.join(self.ext_dir, "services", "mcp_client.js")
        with open(mcp_path, "r", encoding="utf-8") as f:
            mcp_code = f.read()
        self.assertIn("normalizeDocUrl", mcp_code)
        self.assertIn("formatDocTitle", mcp_code)
        self.assertIn('clean.startsWith("chronicle/docs/")', mcp_code)
        self.assertIn('clean.startsWith("security-operations/")', mcp_code)

        # 2. Sidepanel JS links bare chronicle/docs patterns in tool pills and markdown
        sidepanel_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.js")
        with open(sidepanel_path, "r", encoding="utf-8") as f:
            sidepanel_code = f.read()
        self.assertIn("normalizeDocUrl", sidepanel_code)
        self.assertIn("mcp-doc-link", sidepanel_code)
        self.assertIn("formatDocTitle", sidepanel_code)

        # 3. CSS has styling for mcp-doc-link
        css_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.css")
        with open(css_path, "r", encoding="utf-8") as f:
            css_code = f.read()
        self.assertIn(".mcp-status-pill a.mcp-doc-link", css_code)

        # 4. Manifest includes security-operations documentation patterns
        manifest_path = os.path.join(self.ext_dir, "manifest.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_code = f.read()
        self.assertIn("https://docs.cloud.google.com/security-operations/*", manifest_code)

    def test_breach_analytics_extraction_and_chips(self):
        # 1. Extractor exists and matches /breach-analytics
        extractor_path = os.path.join(self.ext_dir, "content", "extractors", "breach_analytics.js")
        self.assertTrue(os.path.exists(extractor_path))
        with open(extractor_path, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn('url.includes("/breach-analytics")', code)
        self.assertIn("startTime", code)
        self.assertIn("endTime", code)
        self.assertIn("Breach Analytics", code)

        # 2. Registered in content_script.js and manifest.json
        cs_path = os.path.join(self.ext_dir, "content", "content_script.js")
        with open(cs_path, "r", encoding="utf-8") as f:
            cs_code = f.read()
        self.assertIn("SecOpsBreachAnalyticsExtractor", cs_code)

        manifest_path = os.path.join(self.ext_dir, "manifest.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
        self.assertIn("content/extractors/breach_analytics.js", manifest_data["content_scripts"][0]["js"])
        self.assertIn("https://*.backstory.chronicle.security/*", manifest_data["content_scripts"][0]["matches"])

        # 3. sidepanel.js deriveContextFromUrl parses startTime and endTime
        sidepanel_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.js")
        with open(sidepanel_path, "r", encoding="utf-8") as f:
            sp_code = f.read()
        self.assertIn('url.includes("/breach-analytics")', sp_code)
        self.assertIn('startTime = urlObj.searchParams.get("startTime")', sp_code)
        self.assertIn('endTime = urlObj.searchParams.get("endTime")', sp_code)
        self.assertIn('feature = displayTime ? `Breach Analytics • ${displayTime}` : "Breach Analytics"', sp_code)

        # 4. sidepanel.js provides dedicated Breach Analytics suggestion chips
        self.assertIn("📖 Breach Analytics scoring docs", sp_code)
        self.assertIn("⚡ Summarize breach detections", sp_code)
        self.assertIn("⚡ Correlate breach IOCs", sp_code)

        # 5. prompts.js formats Breach Analytics context
        prompts_path = os.path.join(self.ext_dir, "services", "prompts.js")
        with open(prompts_path, "r", encoding="utf-8") as f:
            p_code = f.read()
        self.assertIn('fc.route === "breach-analytics"', p_code)
        self.assertIn("Time Window:", p_code)

    def test_all_extension_js_files_syntax_valid(self):
        import subprocess
        js_files = []
        for root, _, files in os.walk(self.ext_dir):
            for file in files:
                if file.endswith(".js"):
                    js_files.append(os.path.join(root, file))
        self.assertGreater(len(js_files), 5)
        for js_file in js_files:
            res = subprocess.run(["node", "-c", js_file], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Syntax error in {js_file}: {res.stderr}")

    def test_high_contrast_hyperlinks(self):
        # 1. sidepanel.css defines high-contrast hyperlinks for global and message-content a
        css_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.css")
        with open(css_path, "r", encoding="utf-8") as f:
            css_code = f.read()
        self.assertIn("/* Accessible High-Contrast Hyperlinks */", css_code)
        self.assertIn(".message-content a {", css_code)
        self.assertIn("color: var(--accent-blue);", css_code)
        self.assertIn("color: var(--accent-blue-hover);", css_code)
        self.assertIn("color: #c58af9;", css_code)

        # 2. sidepanel.js formatMarkdown ensures target="_blank" on links
        sidepanel_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.js")
        with open(sidepanel_path, "r", encoding="utf-8") as f:
            js_code = f.read()
        self.assertIn('target="_blank" rel="noopener noreferrer"', js_code)

    def test_active_page_detection_for_secops_routes(self):
        # 1. Manifest includes all 4 new extractors in content_scripts
        manifest_path = os.path.join(self.ext_dir, "manifest.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
        cs_js = manifest_data["content_scripts"][0]["js"]
        self.assertIn("content/extractors/workdesk.js", cs_js)
        self.assertIn("content/extractors/soar_search.js", cs_js)
        self.assertIn("content/extractors/data_tables.js", cs_js)
        self.assertIn("content/extractors/threats.js", cs_js)

        # 2. sidepanel.js dynamic injection list includes new extractors
        sidepanel_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.js")
        with open(sidepanel_path, "r", encoding="utf-8") as f:
            sp_code = f.read()
        self.assertIn('"content/extractors/workdesk.js"', sp_code)
        self.assertIn('"content/extractors/soar_search.js"', sp_code)
        self.assertIn('"content/extractors/data_tables.js"', sp_code)
        self.assertIn('"content/extractors/threats.js"', sp_code)

        # 3. deriveContextFromUrl handles all 11 requested routes
        self.assertIn('url.includes("/your-workdesk")', sp_code)
        self.assertIn('"pending-actions": "Pending Actions"', sp_code)
        self.assertIn('workspace: "Workspace"', sp_code)
        self.assertIn('announcements: "Announcements"', sp_code)
        self.assertIn('url.includes("/sp-search")', sp_code)
        self.assertIn('url.includes("/data-tables")', sp_code)
        self.assertIn('url.includes("/threats")', sp_code)
        self.assertIn('url.toLowerCase().includes("/rulesets")', sp_code)
        self.assertIn('url.includes("/chronicleAnalytics/ruleSets")', sp_code)
        self.assertIn('feature = isEditor ? "YARA-L Rules Editor" : "YARA-L Rules"', sp_code)

        # 4. renderQuickActionChips defines tailored chips for all 11 routes
        self.assertIn("Playbook pending actions docs", sp_code)
        self.assertIn("SOAR global search docs", sp_code)
        self.assertIn("Data Tables & Reference Lists docs", sp_code)
        self.assertIn("Mandiant Threat Intel docs", sp_code)
        self.assertIn("Curated Rule Sets docs", sp_code)
        self.assertIn("YARA-L 2.0 overview docs", sp_code)

        # 5. content_script.js registers all extractors in order
        cs_path = os.path.join(self.ext_dir, "content", "content_script.js")
        with open(cs_path, "r", encoding="utf-8") as f:
            cs_code = f.read()
        self.assertIn("window.SecOpsWorkdeskExtractor", cs_code)
        self.assertIn("window.SecOpsSOARSearchExtractor", cs_code)
        self.assertIn("window.SecOpsDataTablesExtractor", cs_code)
        self.assertIn("window.SecOpsThreatsExtractor", cs_code)

        # 6. case_view.js explicitly excludes /your-workdesk
        case_path = os.path.join(self.ext_dir, "content", "extractors", "case_view.js")
        with open(case_path, "r", encoding="utf-8") as f:
            case_code = f.read()
        self.assertIn('url.includes("/your-workdesk")', case_code)

        # 7. Test each URL through a node evaluation test
        import subprocess
        test_script = """
        const fs = require('fs');
        const code = fs.readFileSync('clients/chrome_extension/sidepanel/sidepanel.js', 'utf8');
        
        // Mock minimal DOM and global state needed by deriveContextFromUrl
        let currentContext = null;
        function updateContextUI(ctx) {}
        
        // Extract deriveContextFromUrl and run against the 11 URLs
        eval(code.substring(code.indexOf('function deriveContextFromUrl'), code.indexOf('function updateContextUI')));
        
        const testUrls = [
            { url: 'https://preview-americas-sdl.backstory.chronicle.security/your-workdesk/cases', expected: 'Workdesk • Cases' },
            { url: 'https://preview-americas-sdl.backstory.chronicle.security/your-workdesk/pending-actions', expected: 'Workdesk • Pending Actions' },
            { url: 'https://preview-americas-sdl.backstory.chronicle.security/your-workdesk/tasks', expected: 'Workdesk • Tasks' },
            { url: 'https://preview-americas-sdl.backstory.chronicle.security/your-workdesk/requests', expected: 'Workdesk • Requests' },
            { url: 'https://preview-americas-sdl.backstory.chronicle.security/your-workdesk/workspace', expected: 'Workdesk • Workspace' },
            { url: 'https://preview-americas-sdl.backstory.chronicle.security/your-workdesk/announcements', expected: 'Workdesk • Announcements' },
            { url: 'https://preview-americas-sdl.backstory.chronicle.security/sp-search', expected: 'SOAR Search' },
            { url: 'https://preview-americas-sdl.backstory.chronicle.security/data-tables', expected: 'Data Tables' },
            { url: 'https://preview-americas-sdl.backstory.chronicle.security/threats', expected: 'Applied Threat Intelligence' },
            { url: 'https://preview-americas-sdl.backstory.chronicle.security/rules', expected: 'YARA-L Rules' },
            { url: 'https://preview-americas-sdl.backstory.chronicle.security/chronicleAnalytics/ruleSets', expected: 'Curated Rules' }
        ];
        
        for (const item of testUrls) {
            deriveContextFromUrl({ url: item.url, title: 'SecOps' });
            if (currentContext.featureContext.feature !== item.expected) {
                console.error(`Mismatch for ${item.url}: got "${currentContext.featureContext.feature}", expected "${item.expected}"`);
                process.exit(1);
            }
        }
        console.log("ALL_11_URLS_VERIFIED");
        """
        res = subprocess.run(["node", "-e", test_script], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Node evaluation failed: {res.stderr}\n{res.stdout}")
        self.assertIn("ALL_11_URLS_VERIFIED", res.stdout)

    def test_ai_pointer_integration(self):
        """Verify the DeepMind Magic Pointer-inspired SecOps AI Pointer architecture."""
        import subprocess

        # 1. Manifest registers ai_pointer.js in content_scripts
        manifest_path = os.path.join(self.ext_dir, "manifest.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
        self.assertTrue(manifest_data["version"] >= "1.2.19")
        content_js = manifest_data["content_scripts"][0]["js"]
        self.assertIn("content/ai_pointer.js", content_js)

        # 2. Verify ai_pointer.js components
        pointer_js_path = os.path.join(self.ext_dir, "content", "ai_pointer.js")
        self.assertTrue(os.path.exists(pointer_js_path))
        with open(pointer_js_path, "r", encoding="utf-8") as f:
            pointer_code = f.read()

        # Isolated Shadow DOM
        self.assertIn('attachShadow({ mode: "open" })', pointer_code)
        self.assertIn('secops-ai-pointer-host', pointer_code)
        # DeepMind Wiggle algorithm
        self.assertIn("WIGGLE_WINDOW_MS", pointer_code)
        self.assertIn("WIGGLE_REVERSAL_THRESHOLD", pointer_code)
        self.assertIn("xReversals >=", pointer_code)
        # Alt-click chord activation & escape dismiss
        self.assertIn("e.altKey", pointer_code)
        self.assertIn('e.key === "Escape"', pointer_code)
        # Semantic target resolution
        self.assertIn("findSemanticTarget", pointer_code)
        self.assertIn("extractElementInfo", pointer_code)
        self.assertIn("getBoundingClientRect()", pointer_code)
        # DeepMind Micro-HUD actions
        self.assertIn("Ask Documentation", pointer_code)
        self.assertIn("Capture Widget & Chat", pointer_code)
        self.assertIn("Investigate with MCP", pointer_code)
        self.assertIn('"AI_POINTER_ACTION"', pointer_code)

        # 3. Verify background.js handles AI_POINTER_ACTION
        bg_path = os.path.join(self.ext_dir, "background.js")
        with open(bg_path, "r", encoding="utf-8") as f:
            bg_code = f.read()
        self.assertIn('request.type === "AI_POINTER_ACTION"', bg_code)
        self.assertIn("chrome.tabs.captureVisibleTab", bg_code)
        self.assertIn('"AI_POINTER_TRIGGERED"', bg_code)

        # 4. Verify sidepanel.html has AI Pointer toggle
        html_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.html")
        with open(html_path, "r", encoding="utf-8") as f:
            html_code = f.read()
        self.assertIn('id="aiPointerToggle"', html_code)
        self.assertIn("✨ Pointer", html_code)

        # 5. Verify sidepanel.js handles AI_POINTER_TRIGGERED, image cropping, and dynamic injection
        sp_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.js")
        with open(sp_path, "r", encoding="utf-8") as f:
            sp_code = f.read()
        self.assertIn('message.type === "AI_POINTER_TRIGGERED"', sp_code)
        self.assertIn("handleAiPointerTrigger", sp_code)
        self.assertIn("cropAndAttachScreenshot", sp_code)
        self.assertIn("executeAiPointerAction", sp_code)
        self.assertIn("content/ai_pointer.js", sp_code)
        self.assertIn("aiPointerToggle", sp_code)

        # 6. Node syntax validation for all JS files
        syntax_res = subprocess.run(
            ["node", "-c", pointer_js_path],
            capture_output=True,
            text=True
        )
        self.assertEqual(syntax_res.returncode, 0, f"ai_pointer.js syntax error: {syntax_res.stderr}")

    def test_udm_search_time_bounds_and_thought_fallback(self):
        """Verify that mcp_client.js auto-populates time bounds for UDM searches and gemini_api.js handles thought fallbacks."""
        # 1. mcp_client.js auto-populates startTime/endTime for udm_search and search_raw_logs
        mcp_path = os.path.join(self.ext_dir, "services", "mcp_client.js")
        with open(mcp_path, "r", encoding="utf-8") as f:
            mcp_code = f.read()

        self.assertIn('toolName === "udm_search" || toolName === "search_raw_logs"', mcp_code)
        self.assertIn("callArgs.endTime = new Date().toISOString()", mcp_code)
        self.assertIn("callArgs.startTime = new Date(endMs - 24 * 60 * 60 * 1000).toISOString()", mcp_code)
        self.assertIn("callArgs.caseId = callArgs.case_id", mcp_code)

        # 2. gemini_api.js handles thought reasoning accumulation and empty response fallbacks
        gemini_path = os.path.join(self.ext_dir, "services", "gemini_api.js")
        with open(gemini_path, "r", encoding="utf-8") as f:
            gemini_code = f.read()

        self.assertIn("capturedThoughts", gemini_code)
        self.assertIn("lastFinishReason", gemini_code)
        self.assertIn("lastBlockReason", gemini_code)
        self.assertIn("lastToolExecuted", gemini_code)
        self.assertIn("lastToolResult", gemini_code)
        self.assertIn("fullText = capturedThoughts.trim()", gemini_code)

        # 3. sidepanel.js resolves result.text when available
        sp_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.js")
        with open(sp_path, "r", encoding="utf-8") as f:
            sp_code = f.read()

        self.assertIn("result?.text?.trim()", sp_code)
        self.assertIn("result?.lastToolResult?.error", sp_code)

    def test_accessibility_and_contrast_remediation(self):
        """Verify WCAG AA contrast compliance, ARIA attributes, and typography floors in Chrome extension."""
        css_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.css")
        with open(css_path, "r", encoding="utf-8") as f:
            css_code = f.read()

        # Active tab must use dark-on-blue text for WCAG AA contrast (>8:1)
        self.assertIn("color: #121316;", css_code)
        # Hover state for delete/remove must use high-contrast dark red
        self.assertIn("background: #c5221f;", css_code)
        # Copy code button must be at least 11px
        self.assertIn("padding: 3px 8px;", css_code)

        html_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.html")
        with open(html_path, "r", encoding="utf-8") as f:
            html_code = f.read()

        # Semantics: tablist and tabs with aria-selected
        self.assertIn('role="tablist"', html_code)
        self.assertIn('role="tab"', html_code)
        self.assertIn('aria-selected="true"', html_code)
        # Modals: dialog semantics and labeling
        self.assertIn('role="dialog"', html_code)
        self.assertIn('aria-modal="true"', html_code)
        self.assertIn('aria-labelledby="skillsModalTitle"', html_code)
        self.assertIn('aria-labelledby="settingsModalTitle"', html_code)
        # Accessible button names
        self.assertIn('aria-label="Agent Skills Library"', html_code)
        self.assertIn('aria-label="Clear chat history"', html_code)
        self.assertIn('aria-label="Ask a question or enter a slash command"', html_code)

    def test_compact_viewport_and_streamlined_layout(self):
        """Verify P1 layout consolidation: streamlined header, encapsulated menu, and single-row suggestions."""
        html_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.html")
        with open(html_path, "r", encoding="utf-8") as f:
            html_code = f.read()

        # 1. Consolidated header structure
        self.assertIn('class="header-left"', html_code)
        self.assertIn('id="headerMenuBtn"', html_code)
        self.assertIn('id="headerMenuDropdown"', html_code)
        self.assertIn('aria-haspopup="true"', html_code)
        self.assertIn('aria-expanded="false"', html_code)

        # 2. Secondary controls encapsulated in dropdown menu
        self.assertIn('id="includeContextToggle"', html_code)
        self.assertIn('id="aiPointerToggle"', html_code)
        self.assertIn('id="inspectContextBtn"', html_code)
        self.assertIn('id="unslopToggle"', html_code)
        self.assertIn('id="ambientSkillsPill"', html_code)
        self.assertIn('id="skillsBtn"', html_code)

        # 3. Suggestions section consolidated to single row with divider
        self.assertIn('class="suggestions-divider"', html_code)
        self.assertIn('id="suggestionsFilterBar"', html_code)
        self.assertIn('id="quickActions"', html_code)

        # 4. JS wires menu toggle, click-outside, and escape dismissal
        js_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.js")
        with open(js_path, "r", encoding="utf-8") as f:
            js_code = f.read()

        self.assertIn('headerMenuBtn = document.getElementById("headerMenuBtn")', js_code)
        self.assertIn('headerMenuDropdown = document.getElementById("headerMenuDropdown")', js_code)
        self.assertIn('headerMenuBtn.addEventListener("click"', js_code)
        self.assertIn('headerMenuDropdown.classList.toggle("hidden")', js_code)
        self.assertIn('e.key === "Escape"', js_code)
        self.assertIn('headerMenuDropdown.contains(e.target)', js_code)

        # 5. CSS verifies compact vertical footprint
        css_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.css")
        with open(css_path, "r", encoding="utf-8") as f:
            css_code = f.read()

        self.assertIn('.app-header', css_code)
        self.assertIn('min-height: 40px;', css_code)
        self.assertIn('.header-menu-dropdown', css_code)
        self.assertIn('.suggestions-divider', css_code)
        self.assertIn('min-height: 34px;', css_code)

    def test_soc_co_pilot_material_svg_and_impact_card(self):
        """Verify P2 & P3: Crisp Material SVG icons, humanized SOC Impact Card, and dark theme tokens."""
        # 1. HTML has inline Material SVGs
        html_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.html")
        with open(html_path, "r", encoding="utf-8") as f:
            html_code = f.read()

        self.assertIn('class="tab-svg"', html_code)
        self.assertIn('class="btn-svg"', html_code)
        self.assertIn('class="menu-item-svg"', html_code)

        # 2. JS implements SOC Impact Card and helper functions
        js_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.js")
        with open(js_path, "r", encoding="utf-8") as f:
            js_code = f.read()

        self.assertIn('formatHumanizedAction', js_code)
        self.assertIn('extractImpactSummary', js_code)
        self.assertIn('soc-impact-card', js_code)
        self.assertIn('impact-summary-grid', js_code)
        self.assertIn('Inspect Wire Payload (JSON)', js_code)
        self.assertIn('Authorize & Execute', js_code)
        self.assertIn('pill-svg', js_code)
        self.assertIn('chip-svg', js_code)

        # 3. CSS has SOC Impact Card and theme tokens
        css_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.css")
        with open(css_path, "r", encoding="utf-8") as f:
            css_code = f.read()

        self.assertIn('--bg-primary: #121316;', css_code)
        self.assertIn('--bg-secondary: #1a1c21;', css_code)
        self.assertIn('.soc-impact-card', css_code)
        self.assertIn('.impact-badge-svg', css_code)
        self.assertIn('.impact-severity-tag', css_code)
        self.assertIn('.impact-row', css_code)
        self.assertIn('.impact-raw-details', css_code)
        self.assertIn('.pill-svg', css_code)
        self.assertIn('.chip-svg', css_code)

    def test_slash_command_listing_selection_and_execution(self):
        """Verify slash command menu positioning, result definition in handleSendMessage, and YAML skill parsing."""
        # 1. sidepanel.js must declare let result and assign streamChat return to result
        js_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.js")
        with open(js_path, "r", encoding="utf-8") as f:
            js_code = f.read()

        self.assertIn("let result = null;", js_code)
        self.assertIn("result = await window.SecOpsGeminiClient.streamChat(", js_code)
        self.assertIn("result?.text?.trim()", js_code)
        self.assertIn("result?.lastToolResult?.error", js_code)

        # 2. slash command menu integration and mouse selection
        self.assertIn("handleChatInputChange", js_code)
        self.assertIn("currentSlashMatches", js_code)
        self.assertIn("slash-item-cmd", js_code)
        self.assertIn("selectSlashItem", js_code)
        self.assertIn("hideSlashMenu", js_code)

        # 3. CSS must have position: relative on .input-area and high z-index on .slash-command-menu
        css_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.css")
        with open(css_path, "r", encoding="utf-8") as f:
            css_code = f.read()

        self.assertIn(".input-area {\n  position: relative;", css_code)
        self.assertIn(".slash-command-menu {", css_code)
        self.assertIn("z-index: 1000;", css_code)
        self.assertIn(".slash-item-cmd,", css_code)

        # 4. skill_manager.js supports multiline descriptions and robust findSkillByCommand
        sm_path = os.path.join(self.ext_dir, "services", "skill_manager.js")
        with open(sm_path, "r", encoding="utf-8") as f:
            sm_code = f.read()

        self.assertIn("multilineBuffer", sm_code)
        self.assertIn("bareCmd", sm_code)
        self.assertIn("findSkillByCommand", sm_code)

    def test_slash_command_workflow_clarity_and_tool_routing_safeguards(self):
        """Verify inline slash autocomplete, dynamic placeholders, user skill badges, prompt framing, and tool safeguards."""
        # 1. Manifest version is at least 1.2.19
        manifest_path = os.path.join(self.ext_dir, "manifest.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertTrue(manifest["version"] >= "1.2.19")

        # 2. sidepanel.js inline autocomplete, dynamic placeholders, and robust menu dismissal
        sp_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.js")
        with open(sp_path, "r", encoding="utf-8") as f:
            sp_code = f.read()

        self.assertIn("setActiveOnDemandSkill(chosen);", sp_code)
        self.assertIn("Pass ID or parameters for ${cmd}", sp_code)
        self.assertIn("user-skill-badge", sp_code)
        self.assertIn("promptText.startsWith(\"/\")", sp_code)
        self.assertIn('slashCommandMenu.style.display = "none"', sp_code)
        self.assertIn('slashMenuList.innerHTML = ""', sp_code)

        # 3. sidepanel.css user skill badge, slash menu hiding rules, and input-icon-btn
        css_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.css")
        with open(css_path, "r", encoding="utf-8") as f:
            css_code = f.read()

        self.assertIn(".user-skill-badge", css_code)
        self.assertIn(".slash-command-menu.hidden", css_code)
        self.assertIn(".hidden {", css_code)
        self.assertIn(".input-icon-btn", css_code)

        # 3b. sidepanel.html input-wrapper integration
        html_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.html")
        with open(html_path, "r", encoding="utf-8") as f:
            html_code = f.read()
        self.assertIn('button id="captureScreenBtn" class="input-icon-btn"', html_code)
        self.assertNotIn('class="input-toolbar"', html_code)

        # 4. skill_manager.js auto-migration of custom- commands and rawMarkdown preservation
        sm_path = os.path.join(self.ext_dir, "services", "skill_manager.js")
        with open(sm_path, "r", encoding="utf-8") as f:
            sm_code = f.read()
        self.assertIn('mergedSkill.description === ">-"', sm_code)
        self.assertIn('mergedSkill.command.startsWith("/custom-")', sm_code)
        self.assertIn("needsMigrationSave = true", sm_code)
        self.assertIn("rawMarkdown: text", sm_code)

        # 5. gemini_api.js multi-step workflow framing for case skills
        gemini_path = os.path.join(self.ext_dir, "services", "gemini_api.js")
        with open(gemini_path, "r", encoding="utf-8") as f:
            gemini_code = f.read()
        self.assertIn("isCaseIdentifier", gemini_code)
        self.assertIn("Mandatory Multi-Step Workflow:", gemini_code)
        self.assertIn("Do NOT terminate the turn or generate your final answer after step 1 alone", gemini_code)
        self.assertIn("[Activated Skill: ${skillName}]", gemini_code)

        # 6. prompts.js workflow adherence instructions
        prompts_path = os.path.join(self.ext_dir, "services", "prompts.js")
        with open(prompts_path, "r", encoding="utf-8") as f:
            prompts_code = f.read()
        self.assertIn("CRITICAL WORKFLOW ADHERENCE INSTRUCTIONS", prompts_code)
        self.assertIn("ACTIVE ON-DEMAND SKILL", prompts_code)

        # 7. mcp_client.js caseId / caseAlertId sanitization and list_rule_detections safeguards
        mcp_path = os.path.join(self.ext_dir, "services", "mcp_client.js")
        with open(mcp_path, "r", encoding="utf-8") as f:
            mcp_code = f.read()
        self.assertIn('toolName === "list_rule_detections"', mcp_code)
        self.assertIn("callArgs.caseId.replace(/^(?:case\\s*#?|#)\\s*/i, \"\").trim()", mcp_code)
        self.assertIn("is a SecOps Case ID, not a YARA-L rule ID", mcp_code)
        self.assertIn("caseAlertId", mcp_code)

        # 8. Node syntax validation on all touched files
        for fname in ["services/skill_manager.js", "services/gemini_api.js", "services/prompts.js", "services/mcp_client.js", "sidepanel/sidepanel.js"]:
            res = subprocess.run(["node", "-c", os.path.join(self.ext_dir, fname)], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"{fname} syntax error: {res.stderr}")

    def test_gemini_3x_thinking_level_medium_and_mcp_catalog(self):
        """Verify Gemini 3.x models only, thinkingLevel MEDIUM, 8192 token limit, and registered MCP catalog."""
        # 1. Manifest version is at least 1.2.19
        manifest_path = os.path.join(self.ext_dir, "manifest.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertTrue(manifest["version"] >= "1.2.19")

        # 2. gemini_api.js has thinkingConfig with thinkingLevel MEDIUM, includeThoughts true, 8192 maxOutputTokens
        api_path = os.path.join(self.ext_dir, "services", "gemini_api.js")
        with open(api_path, "r", encoding="utf-8") as f:
            api_code = f.read()
        self.assertIn('maxOutputTokens: 8192', api_code)
        self.assertIn('thinkingLevel: "MEDIUM"', api_code)
        self.assertIn('includeThoughts: true', api_code)
        self.assertIn('modelName.startsWith("gemini-3")', api_code)

        # 3. sidepanel.html only contains 3.x models, no 2.5 or 1.5
        html_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.html")
        with open(html_path, "r", encoding="utf-8") as f:
            html_code = f.read()
        self.assertIn('value="gemini-3.8-flash"', html_code)
        self.assertIn('value="gemini-3.8-pro"', html_code)
        self.assertNotIn('gemini-2.5-flash', html_code)
        self.assertNotIn('gemini-1.5-flash', html_code)

        # 4. prompts.js contains registered MCP tool catalog
        prompts_path = os.path.join(self.ext_dir, "services", "prompts.js")
        with open(prompts_path, "r", encoding="utf-8") as f:
            prompts_code = f.read()
        self.assertIn("Available MCP Tools in this Extension:", prompts_code)
        self.assertIn("udm_search (live UDM queries)", prompts_code)
        self.assertIn("search_documents, get_documents (Developer Knowledge MCP)", prompts_code)

        # 5. Node syntax validation
        for fname in ["services/gemini_api.js", "services/prompts.js"]:
            res = subprocess.run(["node", "-c", os.path.join(self.ext_dir, fname)], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"{fname} syntax error: {res.stderr}")

    def test_collapsible_documentation_references_card(self):
        """Verify that documentation references render inside a collapsible details card defaulting to closed."""
        sp_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.js")
        with open(sp_path, "r", encoding="utf-8") as f:
            sp_code = f.read()

        # 1. renderSources returns <details class="sources-consulted-box"${isOpen ? " open" : ""}>
        self.assertIn('<details class="sources-consulted-box"', sp_code)
        self.assertIn('<summary class="sources-header">', sp_code)
        self.assertIn('Documentation References (${count})', sp_code)
        self.assertIn('sources-chevron', sp_code)

        # 2. sidepanel preserves open state if toggled, but defaults to false
        self.assertIn('contentEl.querySelector(".sources-consulted-box")?.open || false', sp_code)

        # 3. CSS styles details.sources-consulted-box with cursor pointer and rotating chevron
        css_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.css")
        with open(css_path, "r", encoding="utf-8") as f:
            css_code = f.read()
        self.assertIn(".sources-consulted-box[open]", css_code)
        self.assertIn(".sources-consulted-box[open] .sources-chevron", css_code)
        self.assertIn("transform: rotate(180deg)", css_code)
        self.assertIn(".sources-header::-webkit-details-marker", css_code)

        # 4. Node syntax validation
        res = subprocess.run(["node", "-c", sp_path], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"sidepanel.js syntax error: {res.stderr}")

    def test_cloud_logging_remote_mcp_integration(self):
        """Verify Google Cloud Logging Remote MCP server integration, tool routing, schemas, and UI controls."""
        # 1. Manifest version 1.2.20 and logging URL matches
        manifest_path = os.path.join(self.ext_dir, "manifest.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertTrue(manifest["version"] >= "1.2.20")
        
        matches = manifest["content_scripts"][0]["matches"]
        self.assertTrue(any("logging" in m for m in matches))
        self.assertTrue(any("console.cloud.google.com/logs" in m for m in matches))
        
        content_js = manifest["content_scripts"][0]["js"]
        self.assertIn("content/extractors/logs_explorer.js", content_js)

        # 2. auth_service.js has enableLoggingMcp in default settings
        auth_path = os.path.join(self.ext_dir, "services", "auth_service.js")
        with open(auth_path, "r", encoding="utf-8") as f:
            auth_code = f.read()
        self.assertIn("enableLoggingMcp: true", auth_code)

        # 3. mcp_client.js contains LOGS_MCP_ENDPOINT, LOGGING_TOOLS, and proper routing
        mcp_path = os.path.join(self.ext_dir, "services", "mcp_client.js")
        with open(mcp_path, "r", encoding="utf-8") as f:
            mcp_code = f.read()

        self.assertIn('LOGS_MCP_ENDPOINT = "https://logging.googleapis.com/mcp"', mcp_code)
        self.assertIn('"list_log_entries"', mcp_code)
        self.assertIn('"list_log_names"', mcp_code)
        self.assertIn('"list_buckets"', mcp_code)
        self.assertIn('"get_bucket"', mcp_code)
        self.assertIn('"list_views"', mcp_code)
        self.assertIn('"get_view"', mcp_code)
        self.assertIn("LOGGING_TOOLS.has(toolName)", mcp_code)
        self.assertIn("return LOGS_MCP_ENDPOINT;", mcp_code)
        self.assertIn("enableLoggingMcp === false", mcp_code)
        self.assertIn('callArgs.resourceNames = [`projects/${projectId}`];', mcp_code)
        self.assertIn("patchListLogEntries", mcp_code)

        # 4. sidepanel.html contains loggingMcpCheckbox
        html_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.html")
        with open(html_path, "r", encoding="utf-8") as f:
            html_code = f.read()
        self.assertIn('id="loggingMcpCheckbox"', html_code)
        self.assertIn("Enable Google Cloud Logging Remote MCP Server", html_code)

        # 5. sidepanel.js wires settings, tool pill, and suggestion chips
        sp_path = os.path.join(self.ext_dir, "sidepanel", "sidepanel.js")
        with open(sp_path, "r", encoding="utf-8") as f:
            sp_code = f.read()
        self.assertIn("loggingMcpCheckbox", sp_code)
        self.assertIn("enableLoggingMcp:", sp_code)
        self.assertIn("Cloud Logging (${tool})", sp_code)
        self.assertIn('fc.feature === "Cloud Logging Explorer"', sp_code)
        self.assertIn("Logging query syntax", sp_code)
        self.assertIn("Search error logs (last 1h)", sp_code)

        # 6. content/extractors/logs_explorer.js exists and has matcher
        logs_extractor_path = os.path.join(self.ext_dir, "content", "extractors", "logs_explorer.js")
        self.assertTrue(os.path.exists(logs_extractor_path))
        with open(logs_extractor_path, "r", encoding="utf-8") as f:
            extractor_code = f.read()
        self.assertIn("SecOpsLogsExplorerExtractor", extractor_code)
        self.assertIn("Cloud Logging Explorer", extractor_code)

        # 7. Node syntax validation on all touched files
        for fname in ["services/auth_service.js", "services/mcp_client.js", "sidepanel/sidepanel.js", "content/extractors/logs_explorer.js"]:
            res = subprocess.run(["node", "-c", os.path.join(self.ext_dir, fname)], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"{fname} syntax error: {res.stderr}")

    def test_mcp_stateless_core_2026_07_28_compliance(self):
        """Verify compliance with Google Cloud MCP Version 2026-07-28 stateless core protocol specification."""
        # 1. Manifest version is 1.2.21
        manifest_path = os.path.join(self.ext_dir, "manifest.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertEqual(manifest["version"], "1.2.21")

        # 2. mcp_client.js defines protocol version 2026-07-28
        mcp_path = os.path.join(self.ext_dir, "services", "mcp_client.js")
        with open(mcp_path, "r", encoding="utf-8") as f:
            mcp_code = f.read()

        self.assertIn('const MCP_PROTOCOL_VERSION = "2026-07-28";', mcp_code)
        self.assertIn('"MCP-Protocol-Version": MCP_PROTOCOL_VERSION', mcp_code)
        self.assertIn('"Mcp-Method": "tools/call"', mcp_code)
        self.assertIn('"Mcp-Name": toolName', mcp_code)

        # 3. Request payload contains _meta with matching protocolVersion
        self.assertIn('"io.modelcontextprotocol/protocolVersion": MCP_PROTOCOL_VERSION', mcp_code)
        self.assertIn('"io.modelcontextprotocol/clientInfo"', mcp_code)

        # 4. x-mcp-header custom parameter mirroring method
        self.assertIn("extractCustomHeaders(toolName, callArgs = {}, context = {})", mcp_code)
        self.assertIn("Mcp-Param-", mcp_code)
        self.assertIn('const customParamHeaders = this.extractCustomHeaders(toolName, callArgs', mcp_code)

        # 5. README.md documents 2026-07-28 Stateless Core
        readme_path = os.path.join(self.ext_dir, "README.md")
        with open(readme_path, "r", encoding="utf-8") as f:
            readme_code = f.read()
        self.assertIn("Stateless Core (MCP Version 2026-07-28)", readme_code)
        self.assertIn("MCP-Protocol-Version: 2026-07-28", readme_code)
        self.assertIn("Mcp-Param-", readme_code)

        # 6. Node execution test for extractCustomHeaders
        test_script = f"""
        const fs = require('fs');
        const code = fs.readFileSync({json.dumps(mcp_path)}, 'utf8');
        global.window = {{}};
        eval(code);
        const client = window.SecOpsMcpClient;
        if (!client) throw new Error("SecOpsMcpClient not initialized");
        
        // Test parameter mirroring
        const headers1 = client.extractCustomHeaders("udm_search", {{ region: "europe-west1", projectId: "my-test-proj" }});
        if (headers1["Mcp-Param-Region"] !== "europe-west1") throw new Error("Region not mirrored: " + JSON.stringify(headers1));
        if (headers1["Mcp-Param-Project"] !== "my-test-proj") throw new Error("Project not mirrored: " + JSON.stringify(headers1));
        console.log("Stateless MCP header tests passed successfully.");
        """
        res = subprocess.run(["node", "-e", test_script], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"extractCustomHeaders node test failed: {res.stderr}")


if __name__ == "__main__":
    unittest.main()




