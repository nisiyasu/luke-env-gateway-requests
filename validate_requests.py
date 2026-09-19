from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

TARGETS = {
    "village": {
        "target_source_commit_sha": "0d225f77944eb54eed648b76f00869879f4284ff",
        "target_blob_sha": "e6536371eddcc7fb5cf5803568216f008011a5f1",
    },
    "castle": {
        "target_source_commit_sha": "0d225f77944eb54eed648b76f00869879f4284ff",
        "target_blob_sha": "573c13225471820d063043a37e3ee26fad389d63",
    },
    "dungeon": {
        "target_source_commit_sha": "0d225f77944eb54eed648b76f00869879f4284ff",
        "target_blob_sha": "198d0f5f3da115b70218ae8180d5f8363d744959",
    },
}

ROOT = pathlib.Path(__file__).resolve().parent
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

ALLOWED_OPS = {
    "LEASE_ACQUIRE",
    "LEASE_HEARTBEAT",
    "LEASE_RELEASE",
    "IMPLEMENTATION_FILE_UPDATE",
    "ISSUE_COMMENT",
    "ISSUE_CLOSE",
    "PARENT_PROGRESS_UPDATE",
    "EVIDENCE_IDENTIFIERS_RESERVE",
    "DURABLE_EVIDENCE_PUBLISH",
    "EVIDENCE_ADOPT",
}

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def validate(path: pathlib.Path) -> list[str]:
    errors=[]
    rel=path.relative_to(ROOT).as_posix()
    parts=rel.split("/")
    if len(parts)!=3 or parts[0]!="requests" or parts[1] not in TARGETS:
        return [f"{rel}: invalid request path"]
    lane=parts[1]
    try:
        req=json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"{path}: invalid JSON: {exc}"]

    request_id=str(req.get("request_id") or "")
    if not REQUEST_ID_RE.fullmatch(request_id):
        errors.append(f"{path}: invalid request_id")
    elif path.name != request_id + ".json":
        errors.append(f"{path}: filename must equal request_id + .json")

    if req.get("schema")!="LUKE_QUEST_ENV_GATEWAY_REQUEST:v1":
        errors.append(f"{path}: schema mismatch")
    if req.get("lane_id")!=lane:
        errors.append(f"{path}: lane_id does not match path")
    if req.get("operation_type") not in ALLOWED_OPS:
        errors.append(f"{path}: operation_type not allowlisted")
    if not req.get("request_id") or not req.get("operation_id") or not req.get("owner_run_id"):
        errors.append(f"{path}: request_id/operation_id/owner_run_id required")
    if not isinstance(req.get("lease_epoch"), int) or req["lease_epoch"] < 0:
        errors.append(f"{path}: lease_epoch must be non-negative int")
    if req.get("expected_target_identity") != TARGETS[lane]:
        errors.append(f"{path}: target identity mismatch")

    supplied=req.get("request_sha256")
    normalized=dict(req)
    normalized["request_sha256"]=""
    actual=hashlib.sha256(canonical(normalized).encode("utf-8")).hexdigest()
    if supplied!=actual:
        errors.append(f"{path}: request_sha256 mismatch")
    return errors

def main():
    files=sorted(ROOT.glob("requests/*/*.json"))
    errors=[]
    seen={}
    for path in files:
        errors.extend(validate(path))
        try:
            request_id=str(json.loads(path.read_text(encoding="utf-8")).get("request_id") or "")
        except Exception:
            continue
        if request_id in seen:
            errors.append(f"duplicate request_id {request_id}: {seen[request_id]} and {path}")
        else:
            seen[request_id]=path
    if errors:
        print("\n".join(errors))
        raise SystemExit(1)
    print(f"VALID {len(files)} request file(s)")

if __name__=="__main__":
    main()
