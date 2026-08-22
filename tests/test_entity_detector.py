"""Unit tests for Entity Detector and Classifier."""

import unittest
from engine.domain import EntityType
from engine.entity_detector import EntityCategory, detect_entity


class TestEntityDetector(unittest.TestCase):
    """Verifies regex and IP detection for untyped entity indicator strings."""

    def test_ip_detection(self):
        # IPv4
        res = detect_entity("192.168.1.1")
        self.assertEqual(res.entity_type, EntityType.IP)
        self.assertEqual(res.category, EntityCategory.ASSET)
        self.assertEqual(res.graph_query, 'graph.entity.ip = "192.168.1.1"')
        self.assertEqual(res.ioc_value_type, "IP_ADDRESS")

        # IPv6
        res6 = detect_entity("2001:0db8:85a3:0000:0000:8a2e:0370:7334")
        self.assertEqual(res6.entity_type, EntityType.IP)
        self.assertEqual(res6.category, EntityCategory.ASSET)

    def test_hash_detection(self):
        # MD5
        md5_val = "f01a9a2d1e31332ed36c1a4d2839f412"
        res_md5 = detect_entity(md5_val)
        self.assertEqual(res_md5.entity_type, EntityType.MD5)
        self.assertEqual(res_md5.category, EntityCategory.FILE)
        self.assertEqual(res_md5.graph_query, f'graph.entity.file.md5 = "{md5_val.lower()}"')
        self.assertEqual(res_md5.ioc_value_type, "HASH_MD5")

        # SHA1
        sha1_val = "da39a3ee5e6b4b0d3255bfef95601890afd80709"
        res_sha1 = detect_entity(sha1_val)
        self.assertEqual(res_sha1.entity_type, EntityType.SHA1)
        self.assertEqual(res_sha1.category, EntityCategory.FILE)
        self.assertEqual(res_sha1.graph_query, f'graph.entity.file.sha1 = "{sha1_val.lower()}"')
        self.assertEqual(res_sha1.ioc_value_type, "HASH_SHA1")

        # SHA256
        sha256_val = "C9D5DC956841E000BFD8762E2F0B48B66C79B79500E894B4EFA7FB9BA17E4E9E"
        res_sha256 = detect_entity(sha256_val)
        self.assertEqual(res_sha256.entity_type, EntityType.SHA256)
        self.assertEqual(res_sha256.category, EntityCategory.FILE)
        self.assertEqual(res_sha256.graph_query, f'graph.entity.file.sha256 = "{sha256_val.lower()}"')
        self.assertEqual(res_sha256.ioc_value_type, "HASH_SHA256")

    def test_email_detection(self):
        email = "analyst@example.com"
        res = detect_entity(email)
        self.assertEqual(res.entity_type, EntityType.EMAIL)
        self.assertEqual(res.category, EntityCategory.USER)
        self.assertEqual(res.graph_query, f'graph.entity.user.email_addresses = "{email}" nocase')
        self.assertEqual(res.ioc_value_type, "EMAIL_ADDRESS")

    def test_domain_detection(self):
        dom = "evil-domain.com"
        res = detect_entity(dom)
        self.assertEqual(res.entity_type, EntityType.DOMAIN)
        self.assertEqual(res.category, EntityCategory.DOMAIN_NAME)
        self.assertEqual(res.graph_query, f'graph.entity.domain.name = "{dom}"')
        self.assertEqual(res.ioc_value_type, "DOMAIN_NAME")

    def test_url_detection(self):
        url = "https://malicious-site.net/payload.exe"
        res = detect_entity(url)
        self.assertEqual(res.entity_type, EntityType.URL)
        self.assertEqual(res.category, EntityCategory.URL)
        self.assertEqual(res.graph_query, f'graph.entity.url = "{url}"')

    def test_mac_detection(self):
        mac = "00:1A:2B:3C:4D:5E"
        res = detect_entity(mac)
        self.assertEqual(res.entity_type, EntityType.MAC)
        self.assertEqual(res.category, EntityCategory.ASSET)
        self.assertEqual(res.graph_query, f'graph.entity.mac = "{mac.lower()}"')
        self.assertEqual(res.ioc_value_type, "MAC_ADDRESS")

    def test_windows_sid_detection(self):
        sid = "S-1-5-21-3623811015-3361044348-30300820-1013"
        res = detect_entity(sid)
        self.assertEqual(res.entity_type, EntityType.WINDOWS_SID)
        self.assertEqual(res.category, EntityCategory.USER)
        self.assertEqual(res.graph_query, f'graph.entity.user.windows_sid = "{sid}"')

    def test_user_and_hostname_heuristics(self):
        # User with backslash domain
        user_domain = r"CORP\john.doe"
        res_user = detect_entity(user_domain)
        self.assertEqual(res_user.entity_type, EntityType.USER)
        self.assertEqual(res_user.category, EntityCategory.USER)

        # Hostname with trailing $
        host_srv = "SRV-DC-01$"
        res_host = detect_entity(host_srv)
        self.assertEqual(res_host.entity_type, EntityType.HOSTNAME)
        self.assertEqual(res_host.category, EntityCategory.ASSET)
        self.assertEqual(res_host.ioc_value_type, "HOSTNAME")


if __name__ == "__main__":
    unittest.main()
