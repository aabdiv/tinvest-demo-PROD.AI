"""Agent account boundaries, community copying and public data isolation."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["MOCK_LLM"] = "1"
os.environ["UNIVERSE_PATH"] = str(ROOT / "tests" / "universe.fake.json")

from fastapi.testclient import TestClient
from backend import account_store as store, config
from backend.main import app


class ManagementChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = config.ACCOUNT_DB_PATH
        config.ACCOUNT_DB_PATH = Path(self.temp.name) / "account.sqlite3"
        self.client = TestClient(app)
        self.client.get("/api/account/portfolios")
        self.url = "/api/account/portfolios/example-oil"

    def tearDown(self):
        self.client.close()
        config.ACCOUNT_DB_PATH = self.old_path
        self.temp.cleanup()

    def get(self):
        return self.client.get(self.url).json()

    def activate(self):
        r = self.get()
        response = self.client.put(self.url + "/management", json={"revision": r["revision"], "mode": "agent", "agent_id": "balance", "amount_rub": 250000})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def action(self, action):
        r = self.get()
        return self.client.post(self.url + "/management/actions", json={"revision": r["revision"], "action": action})

    def test_agent_account_is_separate_and_reused(self):
        before = self.get()
        active = self.activate()
        account_id = active["management"]["account"]["id"]
        self.assertEqual(active["state"], before["state"])
        self.assertEqual(active["current"]["amount"], 250000)
        self.assertEqual(active["management"]["account"]["initial_amount"], 250000)
        self.assertEqual(self.action("pause").status_code, 200)
        self.assertEqual(self.action("resume").status_code, 200)
        r = self.get()
        manual = self.client.put(self.url + "/management", json={"revision": r["revision"], "mode": "manual"})
        self.assertEqual(manual.status_code, 200)
        self.assertEqual(manual.json()["current"]["amount"], before["current"]["amount"])
        resumed = self.activate()
        self.assertEqual(resumed["management"]["account"]["id"], account_id)
        self.assertEqual(resumed["state"], before["state"])

    def test_pause_rejects_execution(self):
        self.activate()
        self.action("pause")
        before = store.get("example-oil")
        self.assertEqual(self.action("review").status_code, 409)
        self.assertEqual(store.get("example-oil"), before)

    def test_agent_execution_keeps_manual_positions_and_constraints(self):
        r = self.get()
        r["state"]["manual_red_lines"].append({"id": "exclude_oil", "kind": "exclude_sector", "sector": "oil_gas", "label": "Без нефтегаза"})
        self.client.put(self.url, json={"revision": r["revision"], "state": r["state"], "editor_chat": r["editor_chat"]})
        active = self.activate()
        original = active["state"]["executed"]
        response = self.action("review")
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["state"]["executed"], original)
        self.assertTrue(all(h["sector"] != "oil_gas" for h in result["current"]["holdings"]))
        for event in result["management"]["account"]["events"]:
            if event["trades"]:
                self.assertTrue(all(check["ok"] for check in event["checks"]))

    def test_editor_changes_require_mandate_approval(self):
        self.activate()
        r = self.get()
        old_policy = store.get("example-oil")["management"]["account"]["mandate_state"]
        r["state"]["manual_axes"]["growth"] = 9
        saved = self.client.put(self.url, json={"revision": r["revision"], "state": r["state"], "editor_chat": r["editor_chat"]}).json()
        self.assertTrue(saved["management"]["mandate_changed"])
        self.assertEqual(store.get("example-oil")["management"]["account"]["mandate_state"], old_policy)
        response = self.action("approve_mandate")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["management"]["mandate_changed"])

    def test_review_invalidates_old_chat_scenario(self):
        self.activate()
        result = self.client.post(self.url + "/chat", json={"text": "Как снизить риск концентрации?"}).json()
        plan = result["plan"]
        if plan is None:
            result = self.client.post(self.url + "/chat", json={"intent": "idea", "source_kind": "text", "article_text": "Добавить IT компании."}).json()
            plan = result["plan"]
        self.assertIsNotNone(plan)
        self.assertEqual(self.action("review").status_code, 200)
        self.assertEqual(self.client.post(self.url + "/plans/" + plan["id"] + "/apply").status_code, 409)

    def test_community_clone_manual_and_agent(self):
        before = store.get("example-oil")
        items = self.client.get("/api/community").json()["items"]
        self.assertEqual(sum(i["kind"] == "agent" for i in items), 3)
        self.assertEqual(sum(i["kind"] == "portfolio" for i in items), 6)
        manual = self.client.post("/api/community/dividend-club/use", json={"title": "Моя стратегия", "amount_rub": 100000, "mode": "manual"})
        self.assertEqual(manual.status_code, 201, manual.text)
        self.assertEqual(manual.json()["management"]["mode"], "manual")
        self.assertIsNone(manual.json()["state"]["executed"])
        agent = self.client.post("/api/community/agent-balance/use", json={"amount_rub": 200000, "mode": "agent"})
        self.assertEqual(agent.status_code, 201, agent.text)
        self.assertEqual(agent.json()["management"]["mode"], "agent")
        self.assertEqual(agent.json()["current"]["amount"], 200000)
        self.assertEqual(store.get("example-oil"), before)

    def test_publication_excludes_private_data(self):
        r = store.get("example-oil")
        r["state"]["messages"] += ["PRIVATE_SENTENCE"]
        r["messages"].append({"role": "user", "text": "PRIVATE_SENTENCE"})
        r["source_text"] = "PRIVATE_SENTENCE"
        r["sources"] = [{"text": "PRIVATE_SENTENCE", "url": "https://private.example"}]
        r["state"]["manual_themes"][0]["query"] = "PRIVATE_SENTENCE"
        store.update(r, r["revision"])
        response = self.client.post("/api/community/publish", json={"portfolio_id": "example-oil", "title": "Публичная стратегия", "description": "Открытое описание"})
        self.assertEqual(response.status_code, 201, response.text)
        public = self.client.get("/api/community/" + response.json()["id"]).json()
        self.assertNotIn("PRIVATE_SENTENCE", json.dumps(public))
        self.assertNotIn("private.example", json.dumps(public))
        self.assertNotIn("650000", json.dumps(public))
        self.assertNotIn("messages", public)
        self.assertNotIn("blueprint", public)
        clone = self.client.post("/api/community/" + public["id"] + "/use", json={"amount_rub": 50000})
        self.assertEqual(clone.status_code, 201, clone.text)
        self.assertNotIn("PRIVATE_SENTENCE", json.dumps(clone.json()))

    def test_publish_agent_requires_agent_account(self):
        response = self.client.post("/api/community/publish", json={"portfolio_id": "example-oil", "kind": "agent", "title": "Агент"})
        self.assertEqual(response.status_code, 400)
        active = self.activate()
        response = self.client.post("/api/community/publish", json={"portfolio_id": "example-oil", "kind": "agent", "title": "Агент"})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertNotIn(active["management"]["account"]["id"], json.dumps(response.json()))

    def test_video_fixture_is_explicit_in_api(self):
        result = self.client.post("/api/video/analyze", json={"source_url": "https://www.tiktok.com/@example/video/1"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["mode"], "prototype")
        self.assertEqual(self.client.post("/api/video/analyze", json={}).status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
