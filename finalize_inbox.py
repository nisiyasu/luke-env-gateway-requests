from __future__ import annotations

import hashlib
import json
import pathlib
from datetime import datetime, timezone

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
    payload = dict(draft.get("payload") or {})
    if draft.get("operation_type") in {"LEASE_ACQUIRE", "LEASE_HEARTBEAT"}:
        if lane == "visual-rebuild":
            requested_ttl = int(payload.get("ttl_seconds", 600))
            if requested_ttl < 60 or requested_ttl > 600:
                raise ValueError("visual-rebuild ttl_seconds must be 60..600")
            payload["ttl_seconds"] = requested_ttl
        else:
            payload["ttl_seconds"] = 600

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
        "payload": payload,
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


LEASE_LIFECYCLE_OPS = {"LEASE_ACQUIRE", "LEASE_HEARTBEAT", "LEASE_RELEASE"}
MAX_ACQUIRE_AGE_SECONDS = 900


def _parse_time(value: str | None) -> float | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def _created_key(obj: dict, path: pathlib.Path) -> tuple[str, str]:
    return (str(obj.get("created_at") or ""), path.name)


def _archive_request(path: pathlib.Path) -> None:
    rel = path.relative_to(ROOT)
    dest = ROOT / "superseded" / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = path.read_bytes()
    if dest.exists() and dest.read_bytes() != data:
        digest = hashlib.sha256(data).hexdigest()[:12]
        dest = dest.with_name(dest.stem + "." + digest + dest.suffix)
    if not dest.exists():
        dest.write_bytes(data)
    path.unlink()
    print(f"SUPERSEDED {rel} -> {dest.relative_to(ROOT)}")


def supersede_old_lease_lifecycle() -> int:
    moved = 0
    for lane in sorted(vr.TARGETS):
        entries = []
        for path in sorted((ROOT / "requests" / lane).glob("*.json")):
            try:
                obj = json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            op = obj.get("operation_type")
            if op in LEASE_LIFECYCLE_OPS:
                entries.append((path, obj))

        acquires = [(p, o) for p, o in entries if o.get("operation_type") == "LEASE_ACQUIRE"]
        if not acquires:
            continue
        latest_path, latest = max(acquires, key=lambda item: _created_key(item[1], item[0]))
        latest_owner = latest.get("owner_run_id")
        latest_created = str(latest.get("created_at") or "")
        latest_ts = _parse_time(latest_created)
        latest_stale = (
            latest_ts is not None
            and datetime.now(timezone.utc).timestamp() - latest_ts > MAX_ACQUIRE_AGE_SECONDS
        )

        for path, obj in entries:
            op = obj.get("operation_type")
            owner = obj.get("owner_run_id")
            created = str(obj.get("created_at") or "")
            should_archive = False
            if op == "LEASE_ACQUIRE" and (path != latest_path or latest_stale):
                should_archive = True
            elif op == "LEASE_HEARTBEAT" and owner != latest_owner:
                should_archive = True
            elif op == "LEASE_RELEASE" and owner != latest_owner:
                should_archive = True
            if should_archive:
                _archive_request(path)
                moved += 1
    return moved


def main() -> None:
    changed = 0
    rejected = 0
    for path in sorted(ROOT.glob("inbox/*/*.json")):
        lane = path.parent.name
        try:
            draft = json.loads(path.read_text(encoding="utf-8-sig"))
            request_id = str(draft.get("request_id") or "")
            if lane != draft.get("lane_id"):
                raise ValueError(f"lane/path mismatch: {path}")
            if path.name != request_id + ".json":
                raise ValueError(f"filename/request_id mismatch: {path}")

            schema = draft.get("schema")
            if schema == "LUKE_QUEST_ENV_GATEWAY_REQUEST_DRAFT:v1":
                dest = ROOT / "requests" / lane / (request_id + ".json")
                builder = mutation_from_draft
            elif schema == "LUKE_QUEST_ENV_EVIDENCE_CAPTURE_REQUEST_DRAFT:v1":
                dest = ROOT / "evidence-requests" / lane / (request_id + ".json")
                builder = capture_from_draft
            else:
                raise ValueError(f"unsupported draft schema: {schema}")

            superseded_dest = ROOT / "superseded" / dest.relative_to(ROOT)
            if superseded_dest.exists():
                print(f"ALREADY_SUPERSEDED {superseded_dest.relative_to(ROOT)}")
                continue
            if dest.exists():
                print(f"ALREADY_FINAL {dest.relative_to(ROOT)}")
                continue

            obj = builder(draft)
            if write_once(dest, obj):
                changed += 1
                print(
                    f"FINALIZED {path.relative_to(ROOT)} -> "
                    f"{dest.relative_to(ROOT)}"
                )
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

    superseded = supersede_old_lease_lifecycle()

    # Validate the active queue after superseding old lease lifecycle requests.
    # Superseded requests remain preserved under superseded/ and in Git history,
    # but the Target poller no longer sees them as executable work.
    vr.main()
    print(f"FINALIZER_CHANGED={changed}")
    print(f"FINALIZER_SUPERSEDED={superseded}")
    print(f"FINALIZER_REJECTED={rejected}")


if __name__ == "__main__":
    main()
