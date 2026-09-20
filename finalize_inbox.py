from __future__ import annotations

import hashlib
import json
import pathlib

import validate_requests as vr

ROOT = pathlib.Path(__file__).resolve().parent


def finalize_hash(obj: dict) -> dict:
    out = dict(obj)
    out["request_sha256"] = ""
    out["request_sha256"] = hashlib.sha256(
        vr.canonical(out).encode("utf-8")
    ).hexdigest()
    return out


def mutation_from_draft(draft: dict) -> dict:
    lane = str(draft.get("lane_id") or "")
    if lane not in vr.TARGETS:
        raise ValueError("invalid lane")
    if draft.get("operation_type") not in vr.ALLOWED_OPS:
        raise ValueError("operation_type not allowlisted")
    out = {
        "schema": "LUKE_QUEST_ENV_GATEWAY_REQUEST:v1",
        "request_id": draft.get("request_id"),
        "lane_id": lane,
        "owner_run_id": draft.get("owner_run_id"),
        "lease_epoch": draft.get("lease_epoch"),
        "operation_id": draft.get("operation_id"),
        "operation_type": draft.get("operation_type"),
        "expected_lane_head": draft.get("expected_lane_head"),
        "expected_target_identity": vr.TARGET_IDENTITIES[lane],
        "payload": draft.get("payload") or {},
        "created_at": draft.get("created_at"),
        "request_sha256": "",
    }
    return finalize_hash(out)


def capture_from_draft(draft: dict) -> dict:
    lane = str(draft.get("lane_id") or "")
    if lane not in vr.TARGETS:
        raise ValueError("invalid lane")
    out = {
        "schema": "LUKE_QUEST_ENV_EVIDENCE_CAPTURE_REQUEST:v1",
        "request_id": draft.get("request_id"),
        "lane_id": lane,
        "owner_run_id": draft.get("owner_run_id"),
        "lease_epoch": draft.get("lease_epoch"),
        "evidence_id": draft.get("evidence_id"),
        "adoption_id": draft.get("adoption_id"),
        "child_issue": draft.get("child_issue"),
        "implementation_head": draft.get("implementation_head"),
        "expected_target_identity": draft.get("expected_target_identity"),
        "created_at": draft.get("created_at"),
        "request_sha256": "",
    }
    return finalize_hash(out)


def write_once(destination: pathlib.Path, obj: dict) -> bool:
    data = (
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    if destination.exists():
        if destination.read_text(encoding="utf-8") != data:
            raise ValueError(
                f"append-only destination collision: {destination}"
            )
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(data, encoding="utf-8")
    return True


def main() -> None:
    changed = 0
    rejected = 0
    for path in sorted(ROOT.glob("inbox/*/*.json")):
        lane = path.parent.name
        try:
            draft = json.loads(path.read_text(encoding="utf-8"))
            request_id = str(draft.get("request_id") or "")
            if lane != draft.get("lane_id"):
                raise ValueError(f"lane/path mismatch: {path}")
            if path.name != request_id + ".json":
                raise ValueError(f"filename/request_id mismatch: {path}")

            schema = draft.get("schema")
            if schema == "LUKE_QUEST_ENV_GATEWAY_REQUEST_DRAFT:v1":
                obj = mutation_from_draft(draft)
                dest = ROOT / "requests" / lane / (request_id + ".json")
            elif schema == "LUKE_QUEST_ENV_EVIDENCE_CAPTURE_REQUEST_DRAFT:v1":
                obj = capture_from_draft(draft)
                dest = ROOT / "evidence-requests" / lane / (request_id + ".json")
            else:
                raise ValueError(f"unsupported draft schema: {schema}")

            if write_once(dest, obj):
                changed += 1
                print(
                    f"FINALIZED {path.relative_to(ROOT)} -> "
                    f"{dest.relative_to(ROOT)}"
                )
            else:
                print(f"ALREADY_FINAL {dest.relative_to(ROOT)}")
        except Exception as exc:
            rejected += 1
            safe_id = path.stem
            reject = ROOT / "rejected" / lane / (safe_id + ".json")
            report = {
                "schema": "LUKE_QUEST_ENV_GATEWAY_DRAFT_REJECTION:v1",
                "source_path": path.relative_to(ROOT).as_posix(),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            write_once(reject, report)
            print(
                f"REJECTED {path.relative_to(ROOT)}: "
                f"{type(exc).__name__}: {exc}"
            )

    # Validate every durable finalized request. A bad finalized request remains
    # fail-closed, but a bad draft can no longer prevent unrelated good drafts
    # from being committed.
    vr.main()
    print(f"FINALIZER_CHANGED={changed}")
    print(f"FINALIZER_REJECTED={rejected}")


if __name__ == "__main__":
    main()
