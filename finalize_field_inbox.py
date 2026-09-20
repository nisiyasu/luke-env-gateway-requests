from __future__ import annotations

import hashlib
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent
TARGET_IDENTITY = {
    "target_source_commit_sha": "90635ceff9d35d69f80da350df1e6ea0610657dd",
    "target_blob_sha": "b7281e6580689a7a22cfa3b67d500950e4af7285",
}
ALLOWED_OPS = {
    "LEASE_ACQUIRE",
    "LEASE_HEARTBEAT",
    "LEASE_RELEASE",
    "IMPLEMENTATION_FILE_UPDATE",
    "ISSUE_COMMENT",
    "ROUTER_ASSERT",
    "CURRENT_PACKET_STATE",
    "ROUTER_UPDATE",
}
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def canonical(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def request_hash(req: dict) -> str:
    normalized = dict(req)
    normalized["request_sha256"] = ""
    return hashlib.sha256(
        canonical(normalized).encode("utf-8")
    ).hexdigest()


def finalize(draft: dict, request_id: str) -> dict:
    if draft.get("schema") != "LUKE_QUEST_CANONICAL_FIELD_GATEWAY_REQUEST_DRAFT:v1":
        raise ValueError("unsupported field draft schema")
    if draft.get("request_id") != request_id:
        raise ValueError("request_id must equal filename")
    if draft.get("lane_id") != "field":
        raise ValueError("lane_id must be field")
    op = draft.get("operation_type")
    if op not in ALLOWED_OPS:
        raise ValueError("operation_type not allowlisted")
    owner = str(draft.get("owner_run_id") or "")
    operation_id = str(draft.get("operation_id") or "")
    if not owner or not operation_id:
        raise ValueError("owner_run_id and operation_id required")
    epoch = draft.get("lease_epoch")
    if not isinstance(epoch, int) or epoch < 0:
        raise ValueError("lease_epoch must be non-negative int")
    payload = dict(draft.get("payload") or {})
    if op in {"LEASE_ACQUIRE", "LEASE_HEARTBEAT"}:
        payload["ttl_seconds"] = 600

    req = {
        "schema": "LUKE_QUEST_ENV_GATEWAY_REQUEST:v1",
        "request_id": request_id,
        "lane_id": "field",
        "owner_run_id": owner,
        "lease_epoch": epoch,
        "operation_id": operation_id,
        "operation_type": op,
        "expected_lane_head": draft.get("expected_lane_head"),
        "expected_target_identity": TARGET_IDENTITY,
        "payload": payload,
        "created_at": draft.get("created_at"),
        "request_sha256": "",
    }
    req["request_sha256"] = request_hash(req)
    return req


def validate_request(path: pathlib.Path) -> list[str]:
    errors = []
    try:
        req = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"{path}: invalid JSON: {exc}"]
    request_id = str(req.get("request_id") or "")
    if not REQUEST_ID_RE.fullmatch(request_id):
        errors.append(f"{path}: invalid request_id")
    if path.name != request_id + ".json":
        errors.append(f"{path}: filename mismatch")
    if req.get("schema") != "LUKE_QUEST_ENV_GATEWAY_REQUEST:v1":
        errors.append(f"{path}: schema mismatch")
    if req.get("lane_id") != "field":
        errors.append(f"{path}: lane mismatch")
    if req.get("operation_type") not in ALLOWED_OPS:
        errors.append(f"{path}: operation not allowlisted")
    if req.get("expected_target_identity") != TARGET_IDENTITY:
        errors.append(f"{path}: target identity mismatch")
    if request_hash(req) != req.get("request_sha256"):
        errors.append(f"{path}: request hash mismatch")
    if path.stat().st_size > 512 * 1024:
        errors.append(f"{path}: request exceeds 512 KiB")
    return errors


LEASE_LIFECYCLE_OPS = {"LEASE_ACQUIRE", "LEASE_HEARTBEAT", "LEASE_RELEASE"}


def _created_key(obj: dict, path: pathlib.Path) -> tuple[str, str]:
    return (str(obj.get("created_at") or ""), path.name)


def _archive_field_request(path: pathlib.Path) -> None:
    rel = path.relative_to(ROOT)
    dest = ROOT / "superseded" / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = path.read_bytes()
    if dest.exists():
        if dest.read_bytes() != data:
            raise ValueError(f"superseded collision: {dest}")
    else:
        dest.write_bytes(data)
    path.unlink()
    print(f"SUPERSEDED {rel} -> {dest.relative_to(ROOT)}")


def supersede_old_field_lease_lifecycle() -> int:
    entries = []
    for path in sorted((ROOT / "field-requests").glob("*.json")):
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if obj.get("operation_type") in LEASE_LIFECYCLE_OPS:
            entries.append((path, obj))

    acquires = [(p, o) for p, o in entries if o.get("operation_type") == "LEASE_ACQUIRE"]
    if not acquires:
        return 0
    latest_path, latest = max(acquires, key=lambda item: _created_key(item[1], item[0]))
    latest_owner = latest.get("owner_run_id")
    latest_created = str(latest.get("created_at") or "")
    moved = 0
    for path, obj in entries:
        op = obj.get("operation_type")
        owner = obj.get("owner_run_id")
        created = str(obj.get("created_at") or "")
        should_archive = False
        if op == "LEASE_ACQUIRE" and path != latest_path:
            should_archive = True
        elif op == "LEASE_HEARTBEAT" and owner != latest_owner:
            should_archive = True
        elif (
            op == "LEASE_RELEASE"
            and owner != latest_owner
            and created < latest_created
        ):
            should_archive = True
        if should_archive:
            _archive_field_request(path)
            moved += 1
    return moved


def main() -> None:
    changed = 0
    for path in sorted(ROOT.glob("field-inbox/*.json")):
        request_id = path.stem
        if not REQUEST_ID_RE.fullmatch(request_id):
            raise ValueError(f"invalid request filename: {path}")
        draft = json.loads(path.read_text(encoding="utf-8"))
        req = finalize(draft, request_id)
        dest = ROOT / "field-requests" / (request_id + ".json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        rendered = (
            json.dumps(req, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        )
        if dest.exists():
            if dest.read_text(encoding="utf-8") != rendered:
                raise ValueError(
                    f"append-only field request collision: {dest}"
                )
        else:
            dest.write_text(rendered, encoding="utf-8")
            changed += 1
            print(f"FINALIZED {path.name} -> {dest.name}")

    superseded = supersede_old_field_lease_lifecycle()

    errors = []
    for path in sorted(ROOT.glob("field-requests/*.json")):
        errors.extend(validate_request(path))
    if errors:
        print("\n".join(errors))
        raise SystemExit(1)
    print(f"FIELD_REQUESTS_VALID changed={changed} superseded={superseded}")


if __name__ == "__main__":
    main()
