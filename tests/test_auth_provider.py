"""Unit tests for engine.auth.CredentialProvider.

Offline by design: every strategy is exercised via mocks/env, so these run on
bare CI runners without Google Cloud credentials.
"""

import os
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from engine.auth import CredentialProvider, AUTH_SCOPES
from engine.config import SecOpsConfigurationError


class TestCredentialProvider(unittest.TestCase):
    # ---- static / override ------------------------------------------------

    def test_static_token_explicit_short_circuits(self):
        prov = CredentialProvider(static_token="tok-explicit")
        with patch.object(prov, "_from_library_adc") as adc, \
             patch.object(prov, "_from_gcloud_adc") as gc:
            self.assertEqual(prov.get_token(), "tok-explicit")
            adc.assert_not_called()
            gc.assert_not_called()

    def test_static_token_from_env(self):
        with patch.dict(os.environ, {"SECOPS_AUTH_TOKEN": "tok-env"}, clear=True):
            prov = CredentialProvider()
            self.assertEqual(prov.get_token(), "tok-env")

    def test_mode_static_without_token_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            prov = CredentialProvider(mode="static")
            with self.assertRaises(SecOpsConfigurationError):
                prov.get_token()

    def test_invalid_mode_raises(self):
        with self.assertRaises(SecOpsConfigurationError):
            CredentialProvider(mode="bogus")

    # ---- library ADC ------------------------------------------------------

    def test_library_adc_returns_token_and_refreshes(self):
        fake_creds = MagicMock()
        fake_creds.valid = False
        fake_creds.token = "adc-token"
        fake_default = MagicMock(return_value=(fake_creds, "proj"))

        with patch.dict(os.environ, {}, clear=True):
            prov = CredentialProvider(mode="adc")
            with patch("google.auth.default", fake_default), \
                 patch("google.auth.transport.requests.Request", MagicMock()):
                self.assertEqual(prov.get_token(), "adc-token")
                fake_creds.refresh.assert_called_once()
                # scope must be the SecOps-required cloud-platform scope
                _, kwargs = fake_default.call_args
                self.assertEqual(kwargs.get("scopes"), AUTH_SCOPES)

    def test_library_adc_no_refresh_when_valid(self):
        fake_creds = MagicMock()
        fake_creds.valid = True
        fake_creds.token = "adc-valid"
        with patch.dict(os.environ, {}, clear=True):
            prov = CredentialProvider(mode="adc")
            with patch("google.auth.default", MagicMock(return_value=(fake_creds, "p"))):
                self.assertEqual(prov.get_token(), "adc-valid")
                fake_creds.refresh.assert_not_called()

    # ---- gcloud subprocess fallback --------------------------------------

    def test_gcloud_uses_application_default_command(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="gcloud-token\n", stderr=""
        )
        with patch.dict(os.environ, {}, clear=True):
            prov = CredentialProvider(mode="gcloud")
            with patch("subprocess.run", return_value=completed) as run:
                self.assertEqual(prov.get_token(), "gcloud-token")
                cmd = run.call_args.args[0]
                # Must be the SCOPED application-default variant, not bare print-access-token.
                self.assertEqual(
                    cmd,
                    ["gcloud", "auth", "application-default", "print-access-token"],
                )

    def test_gcloud_missing_binary_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            prov = CredentialProvider(mode="gcloud")
            with patch("subprocess.run", side_effect=FileNotFoundError()):
                with self.assertRaises(SecOpsConfigurationError):
                    prov.get_token()

    def test_gcloud_command_failure_surfaces_stderr(self):
        err = subprocess.CalledProcessError(1, [], stderr="Reauth required")
        with patch.dict(os.environ, {}, clear=True):
            prov = CredentialProvider(mode="gcloud")
            with patch("subprocess.run", side_effect=err):
                with self.assertRaises(SecOpsConfigurationError) as ctx:
                    prov.get_token()
                self.assertIn("Reauth required", str(ctx.exception))

    # ---- auto chain fallthrough ------------------------------------------

    def test_auto_falls_through_to_gcloud_when_adc_unavailable(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="fallback-token\n", stderr=""
        )
        with patch.dict(os.environ, {}, clear=True):
            prov = CredentialProvider()  # auto
            with patch.object(prov, "_from_library_adc",
                              side_effect=SecOpsConfigurationError("no google-auth")), \
                 patch("subprocess.run", return_value=completed):
                self.assertEqual(prov.get_token(), "fallback-token")

    def test_auto_aggregates_errors_when_all_fail(self):
        with patch.dict(os.environ, {}, clear=True):
            prov = CredentialProvider()  # auto, no static token
            with patch.object(prov, "_from_library_adc",
                              side_effect=SecOpsConfigurationError("adc boom")), \
                 patch.object(prov, "_from_gcloud_adc",
                              side_effect=SecOpsConfigurationError("gcloud boom")):
                with self.assertRaises(SecOpsConfigurationError) as ctx:
                    prov.get_token()
                msg = str(ctx.exception)
                self.assertIn("adc boom", msg)
                self.assertIn("gcloud boom", msg)


if __name__ == "__main__":
    unittest.main()
