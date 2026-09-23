import json
import pathlib
import tempfile
import unittest

import finalize_inbox as fi


class FinalizeInboxRejectionTests(unittest.TestCase):
    def test_existing_rejection_does_not_abort_on_changed_error(self):
        with tempfile.TemporaryDirectory() as td:
            old_root = fi.ROOT
            try:
                fi.ROOT = pathlib.Path(td)
                dest = fi.ROOT / "rejected" / "visual-rebuild" / "bad.json"
                dest.parent.mkdir(parents=True)
                dest.write_text(
                    json.dumps({"error": "old parser error"}, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                self.assertFalse(
                    fi.write_rejection_once(
                        dest,
                        {"error": "new validation error"},
                    )
                )
                persisted = json.loads(dest.read_text(encoding="utf-8"))
                self.assertEqual(persisted["error"], "old parser error")
            finally:
                fi.ROOT = old_root

    def test_new_rejection_is_written_once(self):
        with tempfile.TemporaryDirectory() as td:
            old_root = fi.ROOT
            try:
                fi.ROOT = pathlib.Path(td)
                dest = fi.ROOT / "rejected" / "visual-rebuild" / "bad.json"
                self.assertTrue(fi.write_rejection_once(dest, {"error": "bad"}))
                self.assertFalse(fi.write_rejection_once(dest, {"error": "changed"}))
            finally:
                fi.ROOT = old_root


if __name__ == "__main__":
    unittest.main()
