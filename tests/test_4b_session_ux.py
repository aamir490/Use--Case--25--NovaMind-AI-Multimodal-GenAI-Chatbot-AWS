"""Saved-chat navigation and state transitions with mocked AWS clients."""
import unittest

import test_3c_dynamodb_persistence as fixtures
from novamind.domain.navigation import saved_page, set_saved_page
from novamind.domain.session import _clear_conversation
from services import conversation_store as store
from services.authorization import AuthorizationError, capture_scope, check_scope


class TestSessionUX(unittest.TestCase):
    setUp = fixtures.TestDynamoPersistence.setUp
    state = fixtures.TestDynamoPersistence.state

    def question(self, text="Question"):
        self.alice.chat_history.extend([
            {"role": "user", "text": text}, {"role": "assistant", "text": "Answer"}])
        self.alice.bedrock_history.extend([
            {"role": "user", "content": [{"text": text}]},
            {"role": "assistant", "content": [{"text": "Answer"}]}])

    def test_titles_normalize_whitespace_controls_and_length(self):
        self.assertEqual(store.readable_title("  First\n\tquestion\x00  "), "First question")
        self.assertEqual(store.readable_title(" \n "), "New conversation")
        title = store.readable_title("x" * 200)
        self.assertLessEqual(len(title), 80)
        self.assertTrue(title.endswith("…"))

    def test_title_uses_first_user_not_assistant_and_saves_readable_title(self):
        self.alice.chat_history.append({"role": "assistant", "text": "Welcome"})
        self.question("  My\nquestion  ")
        store.save_conversation(self.alice, client=self.db)
        self.assertEqual(store.list_conversations(self.alice, client=self.db)["items"][0]["title"], "My question")

    def test_dirty_tracks_save_followups_and_settings(self):
        self.assertFalse(store.has_unsaved_changes(self.alice))
        self.question()
        self.assertTrue(store.has_unsaved_changes(self.alice))
        store.save_conversation(self.alice, client=self.db)
        self.assertFalse(store.has_unsaved_changes(self.alice))
        self.alice.temperature = 0.1
        self.assertTrue(store.has_unsaved_changes(self.alice))
        store.save_conversation(self.alice, client=self.db)
        self.question("Follow up")
        self.assertTrue(store.has_unsaved_changes(self.alice))

    def test_clear_resets_local_state_preserves_saved_chat_and_settings(self):
        self.question()
        self.alice.system_prompt = "Persona"
        store.save_conversation(self.alice, client=self.db)
        saved_id = self.alice.conversation_id
        scope = capture_scope(self.alice)
        self.alice["_trigger_summary"] = True
        _clear_conversation(self.alice)
        self.assertNotEqual(self.alice.conversation_id, saved_id)
        self.assertEqual(self.alice.system_prompt, "Persona")
        self.assertEqual(self.alice.chat_history, [])
        self.assertEqual(self.alice.bedrock_history, [])
        self.assertEqual(self.alice.persistence_version, 0)
        self.assertFalse(self.alice["_trigger_summary"])
        self.assertFalse(store.has_unsaved_changes(self.alice))
        with self.assertRaises(AuthorizationError):
            check_scope(self.alice, scope)
        self.assertEqual(store.list_conversations(self.alice, client=self.db)["items"][0]["conversation_id"], saved_id)

    def test_restore_clears_stale_actions_and_marks_clean(self):
        self.question()
        store.save_conversation(self.alice, client=self.db)
        saved_id = self.alice.conversation_id
        _clear_conversation(self.alice)
        self.question("Different conversation")
        self.alice["_trigger_summary"] = True
        store.load_conversation(self.alice, saved_id, client=self.db)
        self.assertFalse(self.alice["_trigger_summary"])
        self.assertFalse(store.has_unsaved_changes(self.alice))
        self.assertEqual(len(self.alice.chat_history), 2)
        self.assertEqual(self.alice.chat_history[0]["text"], "Question")

    def test_failed_switch_preserves_current_unsaved_chat(self):
        self.question("Keep this draft")
        before = self.alice.chat_history
        current_id = self.alice.conversation_id
        with self.assertRaises(AuthorizationError):
            store.load_conversation(self.alice, "a" * 32, client=self.db)
        self.assertIs(self.alice.chat_history, before)
        self.assertEqual(self.alice.conversation_id, current_id)
        self.assertTrue(store.has_unsaved_changes(self.alice))

    def test_navigation_merges_pages_deduplicates_and_stays_user_scoped(self):
        set_saved_page(self.alice, {"items": [{"conversation_id": "a" * 32, "title": "First"}], "next_key": {"cursor": 1}})
        set_saved_page(self.alice, {"items": [
            {"conversation_id": "a" * 32, "title": "Updated"},
            {"conversation_id": "b" * 32, "title": "Second"}], "next_key": None}, append=True)
        self.assertEqual([row["title"] for row in saved_page(self.alice)["items"]], ["Updated", "Second"])
        self.assertEqual(saved_page(self.bob)["items"], [])
        _clear_conversation(self.alice)
        self.assertEqual(len(saved_page(self.alice)["items"]), 2)

    def test_navigation_is_bounded_and_refresh_replaces_old_rows(self):
        set_saved_page(self.alice, {"items": [
            {"conversation_id": f"{index:032x}", "title": str(index)}
            for index in range(120)], "next_key": {"cursor": 1}})
        self.assertEqual(len(saved_page(self.alice)["items"]), 100)
        self.assertIsNone(saved_page(self.alice)["next_key"])
        set_saved_page(self.alice, {"items": [], "next_key": None})
        self.assertEqual(saved_page(self.alice)["items"], [])
