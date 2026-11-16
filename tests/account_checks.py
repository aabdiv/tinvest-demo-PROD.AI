"""Regression checks for portfolio isolation, durable chat and confirmed plan changes.

Run: python tests/make_fake_universe.py && python tests/account_checks.py
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["MOCK_LLM"] = "1"
os.environ["UNIVERSE_PATH"] = str(ROOT / "tests" / "universe.fake.json")

from fastapi.testclient import TestClient
from backend import account_store, config
from backend.main import app
from backend.sources import read_article


class AccountChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = config.ACCOUNT_DB_PATH
        config.ACCOUNT_DB_PATH = Path(self.temp.name) / "account.sqlite3"
        self.client = TestClient(app)
        self.portfolios = self.client.get("/api/account/portfolios").json()["portfolios"]
        self.oil = "/api/account/portfolios/example-oil"

    def tearDown(self):
        self.client.close()
        config.ACCOUNT_DB_PATH = self.old_path
        self.temp.cleanup()

    def test_seed_and_create_source(self):
        self.assertEqual(len(self.portfolios), 2)
        self.assertEqual(len(self.client.get("/api/account/portfolios").json()["portfolios"]), 2)
        self.assertEqual(self.client.get("/api/account/portfolios/missing").status_code, 404)
        url = "/api/account/portfolios"
        self.assertEqual(self.client.post(url, json={"title": "Видео", "source_kind": "video", "source_url": "https://www.tiktok.com/@test/video/1"}).status_code, 400)
        response = self.client.post(url, json={"title": "Рост из видео", "source_kind": "video", "source_url": "https://www.tiktok.com/@test/video/1", "text": "Хочу агрессивный рост. Без банков."})
        self.assertEqual(response.status_code, 201, response.text)
        record = response.json()
        self.assertTrue(record["state"]["wishes"])
        self.assertTrue(record["editor_chat"])
        self.assertEqual(record["source_kind"], "video")
        self.assertEqual(record["state"]["executed"], None)
        self.assertFalse(record["is_example"])

    def test_revision_prevents_lost_updates(self):
        before = self.client.get(self.oil).json()
        state = before["state"]
        state["amount_rub"] = 888000
        update = {"revision": before["revision"], "state": state, "editor_chat": before["editor_chat"], "title": "Переименован"}
        response = self.client.put(self.oil, json=update)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.put(self.oil, json=update).status_code, 409)
        loaded = account_store.get("example-oil")
        self.assertEqual(loaded["title"], "Переименован")
        self.assertEqual(loaded["state"]["amount_rub"], 888000)
        self.assertEqual(self.client.get("/api/account/portfolios/example-video").json()["state"]["amount_rub"], 250000)

    def test_chat_isolation_and_confirmed_scenario(self):
        before = self.client.get(self.oil).json()
        other = self.client.get("/api/account/portfolios/example-video").json()
        response = self.client.post(self.oil + "/chat", json={"text": "Закрыли Ормузский пролив, как снизить риск?", "article_text": "Это тестовый сценарий новости, а не подтверждённое событие."})
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        record, plan = payload["record"], payload["plan"]
        self.assertEqual(record["state"], before["state"], "Chat must not change the investment profile")
        self.assertEqual(len(record["messages"]), len(before["messages"]) + 2)
        self.assertEqual(self.client.get("/api/account/portfolios/example-video").json()["messages"], other["messages"])
        self.assertIsNotNone(plan)
        self.assertTrue(all(c["ok"] for c in plan["checks"]))
        self.assertEqual(plan["status"], "pending")
        applied = self.client.post(self.oil + "/plans/" + plan["id"] + "/apply")
        self.assertEqual(applied.status_code, 200, applied.text)
        updated = applied.json()
        self.assertEqual(updated["state"]["executed"], before["state"]["executed"], "Changing a plan must not execute trades")
        self.assertTrue(any(l["id"].startswith("research_concentration_") for l in updated["state"]["manual_red_lines"]))
        self.assertEqual(updated["plans"][0]["status"], "applied")
        self.assertEqual(self.client.post(self.oil + "/plans/" + plan["id"] + "/apply").status_code, 409)
        self.assertEqual(account_store.get("example-oil")["messages"], updated["messages"])

    def test_stale_plan_is_rejected(self):
        response = self.client.post(self.oil + "/chat", json={"text": "Как снизить риск концентрации?"})
        self.assertEqual(response.status_code, 200, response.text)
        record, plan = response.json()["record"], response.json()["plan"]
        state = record["state"]
        state["manual_axes"]["growth"] = 8
        self.assertEqual(self.client.put(self.oil, json={"revision": record["revision"], "state": state, "editor_chat": record["editor_chat"]}).status_code, 200)
        self.assertEqual(self.client.post(self.oil + "/plans/" + plan["id"] + "/apply").status_code, 409)

    def test_scenario_preserves_stricter_and_previous_sector_limits(self):
        record = self.client.get(self.oil).json()
        state = record["state"]
        state["manual_red_lines"] += [
            {"id": "strict_oil", "kind": "max_sector_share", "sector": "oil_gas", "value": 0.2, "label": "Нефтегаз до 20%"},
            {"id": "research_concentration_gov_bonds", "kind": "max_sector_share", "sector": "gov_bonds", "value": 0.6, "label": "ОФЗ до 60%"},
        ]
        self.assertEqual(self.client.put(self.oil, json={"revision": record["revision"], "state": state, "editor_chat": record["editor_chat"]}).status_code, 200)
        response = self.client.post(self.oil + "/chat", json={"text": "Как снизить риск?"})
        self.assertEqual(response.status_code, 200, response.text)
        plan = response.json()["plan"]
        self.assertIsNotNone(plan)
        lines = {line["id"]: line for line in plan["state"]["manual_red_lines"]}
        self.assertIn("research_concentration_gov_bonds", lines)
        self.assertEqual(lines["research_concentration_oil_gas"]["value"], 0.2)
        self.assertTrue(all(c["ok"] for c in plan["checks"]))

    def test_unread_sources_are_not_presented_as_read(self):
        self.assertEqual(read_article("http://127.0.0.1:8100/api/meta")["status"], "unavailable")
        self.assertEqual(read_article("https://www.tiktok.com/@test/video/1")["status"], "needs_transcript")
        result = self.client.post(self.oil + "/chat", json={"text": "Что здесь советуют?", "source_url": "https://www.tiktok.com/@test/video/1"})
        self.assertEqual(result.status_code, 200)
        record = result.json()["record"]
        self.assertEqual(record["messages"][-2]["attachment"]["status"], "needs_transcript")
        self.assertIn("расшифровка", record["messages"][-1]["text"])

    def test_model_receives_only_selected_portfolio_context(self):
        import json
        reply = {"title": "Проверка", "answer": "Учитываю ваш портфель.", "watchpoints": [], "scenario": "none"}
        with patch.object(config, "MOCK", False), patch("backend.research.structured", return_value=(reply, {})) as call:
            response = self.client.post(self.oil + "/chat", json={"text": "Какой у меня горизонт?"})
        self.assertEqual(response.status_code, 200, response.text)
        context = json.loads(call.call_args.args[2])
        self.assertEqual(context["portfolio"]["title"], "Нефтегаз и дивиденды")
        self.assertEqual(context["portfolio"]["amount_rub"], 650000)
        self.assertTrue(context["portfolio"]["holdings"])
        self.assertTrue(context["portfolio"]["red_lines"])
        self.assertNotIn("Смелая идея из видео", call.call_args.args[2])

    def test_invalid_model_reply_does_not_corrupt_saved_history(self):
        before = account_store.get("example-oil")
        with patch.object(config, "MOCK", False), patch("backend.research.structured", return_value=({"answer": "Incomplete"}, {})):
            response = self.client.post(self.oil + "/chat", json={"text": "Проверка"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(account_store.get("example-oil"), before)

    def test_create_from_external_text_and_article(self):
        response = self.client.post("/api/account/portfolios", json={
            "title": "Чужая идея из обсуждения", "strategy_origin": "external", "source_kind": "text",
            "text": "Хочу дивиденды. Без банков.",
        })
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["strategy_origin"], "external")
        self.assertEqual(response.json()["sources"][0]["kind"], "text")
        article = {"status": "read", "text": "Дивидендная стратегия на пять лет, без заёмных денег.", "url": "https://example.com/article", "notice": "Прочитано"}
        with patch("backend.accounts.read_article", return_value=article):
            response = self.client.post("/api/account/portfolios", json={
                "title": "Идея из статьи", "strategy_origin": "external", "source_kind": "article", "source_url": article["url"],
            })
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["source_text"], article["text"])

    def test_video_idea_adapts_existing_portfolio_after_confirmation(self):
        before = self.client.get(self.oil).json()
        other = account_store.get("example-video")
        response = self.client.post(self.oil + "/chat", json={
            "intent": "idea", "source_kind": "video", "source_title": "Технологии к дивидендам",
            "source_url": "https://www.tiktok.com/@example/video/1",
            "article_text": "В ролике предлагают добавить российский IT и технологические компании небольшой долей.",
            "text": "Как адаптировать мой нефтегазовый портфель к этой идее?",
        })
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertIsNotNone(result["plan"])
        self.assertEqual(result["record"]["state"], before["state"])
        source = result["record"]["sources"][-1]
        self.assertEqual(source["kind"], "video")
        self.assertEqual(result["plan"]["source_id"], source["id"])
        self.assertEqual(result["plan"]["state"]["manual_axes"], before["state"]["manual_axes"])
        self.assertEqual(account_store.get("example-video"), other)
        self.assertTrue(all(c["ok"] for c in result["plan"]["checks"]))
        applied = self.client.post(self.oil + "/plans/" + result["plan"]["id"] + "/apply")
        self.assertEqual(applied.status_code, 200, applied.text)
        self.assertEqual(applied.json()["state"]["executed"], before["state"]["executed"])
        self.assertTrue(any(t["id"] == "idea_" + source["id"] for t in applied.json()["state"]["manual_themes"]))
        recall = self.client.post(self.oil + "/chat", json={"text": "Какие идеи мы добавляли?"})
        self.assertIn("Технологии к дивидендам", recall.json()["record"]["messages"][-1]["text"])

    def test_external_idea_respects_sector_exclusion(self):
        record = self.client.get(self.oil).json()
        state = record["state"]
        state["manual_red_lines"].append({"id": "no_it", "kind": "exclude_sector", "sector": "it_internet", "label": "Без IT"})
        self.assertEqual(self.client.put(self.oil, json={"revision": record["revision"], "state": state, "editor_chat": record["editor_chat"]}).status_code, 200)
        state = self.client.get(self.oil).json()["state"]
        response = self.client.post(self.oil + "/chat", json={"intent": "idea", "source_kind": "text", "article_text": "Автор предлагает добавить IT компании."})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["plan"])
        self.assertEqual(response.json()["record"]["state"], state)
        self.assertIn("не добавляю", response.json()["record"]["messages"][-1]["text"])

    def test_unread_video_idea_is_not_saved_as_analyzed(self):
        before = account_store.get("example-oil")
        response = self.client.post(self.oil + "/chat", json={"intent": "idea", "source_kind": "video", "source_url": "https://www.tiktok.com/@example/video/1"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(account_store.get("example-oil"), before)

    def test_idea_analysis_sees_previous_news_scenario_without_treating_it_as_executed(self):
        import json
        news = self.client.post(self.oil + "/chat", json={"text": "Что делать при закрытии Ормузского пролива?"}).json()
        self.assertIsNotNone(news["plan"])
        reply = {"title": "Новая идея", "answer": "Сравниваю её с текущим составом и прошлым сценарием.",
                 "watchpoints": [], "sectors": ["it_internet"], "reduce_concentration": False}
        with patch.object(config, "MOCK", False), patch("backend.research.structured", return_value=(reply, {})) as call:
            response = self.client.post(self.oil + "/chat", json={"intent": "idea", "source_kind": "text", "article_text": "Добавить IT-компании."})
        self.assertEqual(response.status_code, 200, response.text)
        context = json.loads(call.call_args.args[2])["portfolio"]
        self.assertEqual(context["previous_scenarios"][-1]["status"], "pending")
        self.assertEqual(context["previous_scenarios"][-1]["after"], news["plan"]["after"])
        current = self.client.get(self.oil).json()["current"]
        self.assertEqual(context["sectors"], current["sectors"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
