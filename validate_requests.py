from __future__ import annotations

import hashlib
import json
import pathlib
import re

TARGETS = {
    "village": {
        "target_source_commit_sha": "0d225f77944eb54eed648b76f00869879f4284ff",
        "target_blob_sha": "e6536371eddcc7fb5cf5803568216f008011a5f1",
        "children": set(range(54, 68)),
    },
    "castle": {
        "target_source_commit_sha": "0d225f77944eb54eed648b76f00869879f4284ff",
        "target_blob_sha": "573c13225471820d063043a37e3ee26fad389d63",
        "children": set(range(68, 82)),
    },
    "dungeon": {
        "target_source_commit_sha": "0d225f77944eb54eed648b76f00869879f4284ff",
        "target_blob_sha": "198d0f5f3da115b70218ae8180d5f8363d744959",
        "children": set(range(82, 96)),
    },
    "visual-rebuild": {
        "target_source_commit_sha": "90635ceff9d35d69f80da350df1e6ea0610657dd",
        "target_blob_sha": "b7281e6580689a7a22cfa3b67d500950e4af7285",
        "children": set(range(102, 117)),
    },
}
TARGET_IDENTITIES = {
    lane: {
        "target_source_commit_sha": cfg["target_source_commit_sha"],
        "target_blob_sha": cfg["target_blob_sha"],
    }
    for lane, cfg in TARGETS.items()
}
ROOT = pathlib.Path(__file__).resolve().parent
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

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
    "DURABLE_EVIDENCE_PUBLISH_FROM_ARTIFACT",
    "EVIDENCE_ADOPT",
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def request_hash_ok(req: dict) -> bool:
    supplied = req.get("request_sha256")
    normalized = dict(req)
    normalized["request_sha256"] = ""
    actual = hashlib.sha256(canonical(normalized).encode("utf-8")).hexdigest()
    return supplied == actual


def common_checks(path: pathlib.Path, req: dict, lane: str) -> list[str]:
    errors = []
    request_id = str(req.get("request_id") or "")
    if not REQUEST_ID_RE.fullmatch(request_id):
        errors.append(f"{path}: invalid request_id")
    elif path.name != request_id + ".json":
        errors.append(f"{path}: filename must equal request_id + .json")
    if req.get("lane_id") != lane:
        errors.append(f"{path}: lane_id does not match path")
    if req.get("expected_target_identity") != TARGET_IDENTITIES[lane]:
        errors.append(f"{path}: target identity mismatch")
    if not request_hash_ok(req):
        errors.append(f"{path}: request_sha256 mismatch")
    if path.stat().st_size > 256 * 1024:
        errors.append(f"{path}: request exceeds 256 KiB; binary evidence is prohibited")
    return errors


def validate_mutation(path: pathlib.Path, req: dict, lane: str) -> list[str]:
    errors = common_checks(path, req, lane)
    if req.get("schema") != "LUKE_QUEST_ENV_GATEWAY_REQUEST:v1":
        errors.append(f"{path}: mutation schema mismatch")
    if req.get("operation_type") not in ALLOWED_OPS:
        errors.append(f"{path}: operation_type not allowlisted")
    if not req.get("operation_id") or not req.get("owner_run_id"):
        errors.append(f"{path}: operation_id/owner_run_id required")
    if not isinstance(req.get("lease_epoch"), int) or req["lease_epoch"] < 0:
        errors.append(f"{path}: lease_epoch must be non-negative int")
    return errors


def validate_capture(path: pathlib.Path, req: dict, lane: str) -> list[str]:
    errors = common_checks(path, req, lane)
    if req.get("schema") != "LUKE_QUEST_ENV_EVIDENCE_CAPTURE_REQUEST:v1":
        errors.append(f"{path}: capture schema mismatch")
    if not req.get("owner_run_id") or not req.get("evidence_id") or not req.get("adoption_id"):
        errors.append(f"{path}: owner_run_id/evidence_id/adoption_id required")
    if not isinstance(req.get("lease_epoch"), int) or req["lease_epoch"] < 1:
        errors.append(f"{path}: capture lease_epoch must be positive int")
    child = req.get("child_issue")
    if not isinstance(child, int) or child not in TARGETS[lane]["children"]:
        errors.append(f"{path}: child_issue outside lane allowlist")
    if not SHA40_RE.fullmatch(str(req.get("implementation_head") or "")):
        errors.append(f"{path}: implementation_head must be 40-char SHA")
    return errors


def audit_status(obj: object) -> str:
    if not isinstance(obj, dict):
        return ""
    return str(obj.get("STATUS", obj.get("status", ""))).upper()


def validate(path: pathlib.Path) -> list[str]:
    rel = path.relative_to(ROOT).as_posix()
    parts = rel.split("/")
    if len(parts) != 3 or parts[1] not in TARGETS:
        return [f"{rel}: invalid request path"]
    family, lane = parts[0], parts[1]
    try:
        req = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"{path}: invalid JSON: {exc}"]
    if family == "requests":
        return validate_mutation(path, req, lane)
    if family == "evidence-requests":
        return validate_capture(path, req, lane)
    return [f"{rel}: unsupported request family"]


def main():
    files = []
    for family in ("requests", "evidence-requests"):
        files.extend(sorted(ROOT.glob(f"{family}/*/*.json")))
    errors = []
    seen = {}
    for path in files:
        errors.extend(validate(path))
        try:
            request_id = str(json.loads(path.read_text(encoding="utf-8")).get("request_id") or "")
        except Exception:
            continue
        if request_id in seen:
            errors.append(f"duplicate request_id {request_id}: {seen[request_id]} and {path}")
        else:
            seen[request_id] = path
    if errors:
        print("\n".join(errors))
        raise SystemExit(1)
    print(f"VALID {len(files)} request file(s)")


if __name__ == "__main__":
    main()
