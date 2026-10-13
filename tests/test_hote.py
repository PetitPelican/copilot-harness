# -*- coding: utf-8 -*-
"""Port des `#[test]` de `harnais/src/hote.rs` (4 tests) — LE CONTRAT DE L'HÔTE."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

from hote import contexte_copilot, refus, renvoi_copilot, traduis


class Essais(unittest.TestCase):

    def test_la_forme_pascal_de_copilot_passe_presque_telle_quelle(self):
        v = traduis({"hook_event_name": "PostToolUse", "session_id": "s", "cwd": "C:\\p",
                     "tool_name": "Read", "tool_input": {"path": "C:\\m\\note.md"},
                     "tool_result": {"result_type": "success", "text_result_for_llm": "contenu"}})
        self.assertEqual(v["tool_name"], "Read")
        self.assertEqual(v["tool_input"]["file_path"], "C:\\m\\note.md")
        self.assertEqual(v["tool_response"], "contenu")
        self.assertEqual(v["hook_event_name"], "PostToolUse", "un nom donné n'est jamais écrasé")

    def test_la_forme_camel_est_ramenee_a_la_forme_pascal(self):
        v = traduis({"sessionId": "s", "cwd": "/p", "toolName": "powershell",
                     "toolArgs": "{\"command\":\"git commit -m x\"}",
                     "toolResult": {"resultType": "success", "textResultForLlm": "ok"}})
        self.assertEqual(v["session_id"], "s")
        self.assertEqual(v["tool_name"], "Bash", "PowerShell est le shell de Windows")
        self.assertEqual(v["tool_input"]["command"], "git commit -m x")
        self.assertEqual(v["tool_response"], "ok")
        # Un fichier déjà nommé `file_path` n'est pas remplacé par `path`.
        v = traduis({"tool_input": {"file_path": "/a", "path": "/b"}})
        self.assertEqual(v["tool_input"]["file_path"], "/a")

    def test_le_message_transforme_est_un_message_de_l_utilisateur(self):
        v = traduis({"sessionId": "s", "cwd": "/p", "prompt": "salut",
                     "transformedPrompt": "salut (transformé)"})
        self.assertEqual(v["hook_event_name"], "UserPromptSubmit")
        self.assertEqual(v["prompt"], "salut")
        # TÉMOIN : un autre événement camelCase ne devient pas un message.
        self.assertNotIn("hook_event_name", traduis({"sessionId": "s"}))

    def test_les_sorties_copilot_sont_du_json_ascii_lisible(self):
        t = "Café — à relire"
        c = json.loads(contexte_copilot(None, t))
        self.assertEqual(c["additionalContext"], t)
        c = contexte_copilot("la demande", t)
        self.assertTrue(c.isascii(), "un octet non ASCII peut être abîmé par PowerShell : %s" % c)
        c = json.loads(c)
        m = c["modifiedTransformedPrompt"]
        self.assertTrue(m.startswith("la demande"), "la demande d'abord, intacte")
        self.assertIn(t, m)
        r = json.loads(refus("non"))
        self.assertEqual(r["permissionDecision"], "deny")
        self.assertEqual(r["permissionDecisionReason"], "non")
        b = json.loads(renvoi_copilot("reprends"))
        self.assertEqual(b["decision"], "block")
        self.assertEqual(b["reason"], "reprends")


if __name__ == "__main__":
    unittest.main()
