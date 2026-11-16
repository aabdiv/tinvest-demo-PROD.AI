"""Deployment guardrails and LLM diagnostic checks, without network or real data."""
import contextlib
import io
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import config, llm
from scripts import check_openrouter, demo_healthcheck, serve_demo


class DeploymentChecks(unittest.TestCase):
    def test_missing_key_cannot_silently_enable_mock(self):
        with patch.object(config, "OPENROUTER_API_KEY", ""), patch.dict(os.environ, {"MOCK_LLM": "0"}):
            with self.assertRaisesRegex(SystemExit, "OPENROUTER_API_KEY"):
                serve_demo.preflight()

    def test_explicit_mock_creates_writable_persistent_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "account.sqlite3"
            with patch.object(config, "ACCOUNT_DB_PATH", path), patch.object(config, "OPENROUTER_API_KEY", ""), \
                 patch.dict(os.environ, {"MOCK_LLM": "1"}), patch.object(serve_demo, "get_universe", return_value=SimpleNamespace(N=1)):
                serve_demo.preflight()
                with sqlite3.connect(path) as db:
                    db.execute("CREATE TABLE portfolios (title TEXT)")
                    db.execute("INSERT INTO portfolios VALUES ('keep me')")
                serve_demo.preflight()
                with sqlite3.connect(path) as db:
                    self.assertEqual(db.execute("SELECT title FROM portfolios").fetchone()[0], "keep me")

    def test_empty_universe_rejected(self):
        with patch.object(config, "OPENROUTER_API_KEY", "test"), \
             patch.object(serve_demo, "get_universe", return_value=SimpleNamespace(N=0)):
            with self.assertRaisesRegex(SystemExit, "empty"):
                serve_demo.preflight()

    def test_readiness_rejects_empty_universe(self):
        response = io.BytesIO(b'{"universe":{"ok":true,"count":0}}')
        with patch.object(demo_healthcheck, "urlopen", return_value=response):
            with self.assertRaises(SystemExit):
                demo_healthcheck.main()

    def test_diagnostic_refuses_mock_without_making_request(self):
        with patch.object(config, "MOCK", True), patch.object(llm, "structured") as call, \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(check_openrouter.main(), 1)
            call.assert_not_called()

    def test_diagnostic_uses_structured_application_path(self):
        meta = {"model": "test/model", "mode": "json_schema", "ms": 12}
        with patch.object(config, "MOCK", False), patch.object(llm, "_get_client", return_value=SimpleNamespace(max_retries=2)), \
             patch.object(llm, "structured", return_value=({"ok": True}, meta)) as call, \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(check_openrouter.main(), 0)
            self.assertEqual(call.call_args.args[0], "fast")
            self.assertIn("OpenRouter OK", out.getvalue())

    def test_provider_errors_do_not_print_secrets(self):
        with patch.object(config, "MOCK", False), patch.object(llm, "_get_client", return_value=SimpleNamespace(max_retries=2)), \
             patch.object(llm, "structured", side_effect=llm.LLMError("private-api-key")), \
             contextlib.redirect_stderr(io.StringIO()) as out:
            self.assertEqual(check_openrouter.main(), 1)
            self.assertNotIn("private-api-key", out.getvalue())


if __name__ == "__main__":
    unittest.main()
