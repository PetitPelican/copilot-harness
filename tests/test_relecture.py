# -*- coding: utf-8 -*-
"""Port des `#[test]` de `harnais/src/relecture.rs` (1 test)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

from _isole import Isole
from relecture import normalise


class Essais(Isole):

    def test_un_juge_bavard_ou_ambigu_ne_confirme_jamais(self):
        self.assertEqual(normalise("CONFIRME\n"), "CONFIRME")
        self.assertEqual(normalise("CONFIRMÉ"), "CONFIRME")
        self.assertEqual(normalise("CONTREDIT pas mesuré"), "CONTREDIT pas mesuré")
        for t in ["CONFIRME pas vraiment", "CONFIRME\nmais non", "CONFIRMERA", "", "CONTREDIT"]:
            self.assertTrue(normalise(t).startswith("INSUFFISANT"), t)


if __name__ == "__main__":
    unittest.main()
