import json
import pathlib
import tempfile
import unittest

import finalize_inbox as fi
import validate_requests as vr


def draft(request_id="worker-a-patch", *, phase="PATCHSET_SUBMITTED"):
    expected_head = "a" * 40
    payload = {
        "issue_number": 130,
        "task_id": "T016",
        "worker_id": "A",
        "claim_generation": 7,
        "files": [
            {
                "path": "prototypes/target-image-threejs/x.txt",
                "encoding": "utf-8",
                "content": "x",
            }
        ],
    }
    return {
        "schema": "LUKE_QUEST_ENV_GATEWAY_REQUEST_DRAFT:v1",
        "request_id": request_id,
        "lane_id": "visual-rebuild",
        "owner_run_id": "run-a",
        "lease_epoch": 0,
        "operation_id": request_id + "-op",
        "operation_type": "IMPLEMENTATION_PATCHSET",
        "expected_lane_head": expected_head,
        "payload": payload,
        "work_context": {
            "issue_number": 130,
            "task_id": "T016",
            "worker_id": "A",
            "owner_run_id": "run-a",
            "claim_generation": 7,
            "operation_id": request_id + "-op",
            "work_phase": phase,
            "submitted_payload_reference": (
                f"inbox/visual-rebuild/{request_id}.json"
            ),
            "expected_head": expected_head,
            "last_progress_at": "2026-09-23T12:00:00Z",
            "next_recovery_action": "RECONCILE_PATCHSET_RECEIPT",
        },
        "created_at": "2026-09-23T12:00:00Z",
    }

class WorkContextTests(unittest.TestCase):
    def test_legacy_finalizer_does_not_inject_null_work_context(self):
        d = draft()
        d.pop("work_context")
        d["operation_type"] = "ISSUE_COMMENT"
        d["payload"] = {"issue_number": 130, "body": "legacy"}
        req = fi.mutation_from_draft(d)
        self.assertNotIn("work_context", req)

    def test_finalizer_preserves_durable_work_context(self):
        d = draft()
        req = fi.mutation_from_draft(d)
        self.assertEqual(req["work_context"], d["work_context"])
        self.assertTrue(vr.request_hash_ok(req))
        self.assertIn("IMPLEMENTATION_PATCHSET", vr.ALLOWED_OPS)
        self.assertIn("TASK_COMPLETE", vr.ALLOWED_OPS)
        self.assertIn("WORK_CLAIM_TAKEOVER", vr.ALLOWED_OPS)

    def test_validator_accepts_consistent_patchset_context(self):
        req = fi.mutation_from_draft(draft())
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td) / "requests" / "visual-rebuild"
            root.mkdir(parents=True)
            path = root / (req["request_id"] + ".json")
            path.write_text(
                json.dumps(req, ensure_ascii=False),
                encoding="utf-8",
            )
            errors = vr.validate_mutation(
                path, req, "visual-rebuild"
            )
        self.assertEqual(errors, [])

    def test_validator_rejects_context_phase_drift(self):
        d = draft(phase="WAITING_IS_TERMINAL")
        req = fi.mutation_from_draft(d)
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td) / "requests" / "visual-rebuild"
            root.mkdir(parents=True)
            path = root / (req["request_id"] + ".json")
            path.write_text(json.dumps(req), encoding="utf-8")
            errors = vr.validate_mutation(
                path, req, "visual-rebuild"
            )
        self.assertTrue(
            any("work_context mismatch work_phase" in e for e in errors),
            errors,
        )

    def test_validator_rejects_non_durable_payload_pointer(self):
        d = draft()
        d["work_context"]["submitted_payload_reference"] = "local://dirty"
        req = fi.mutation_from_draft(d)
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td) / "requests" / "visual-rebuild"
            root.mkdir(parents=True)
            path = root / (req["request_id"] + ".json")
            path.write_text(json.dumps(req), encoding="utf-8")
            errors = vr.validate_mutation(
                path, req, "visual-rebuild"
            )
        self.assertTrue(
            any("submitted_payload_reference mismatch" in e for e in errors),
            errors,
        )


if __name__ == "__main__":
    unittest.main()

