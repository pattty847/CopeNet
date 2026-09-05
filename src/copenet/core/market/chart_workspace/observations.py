"""Atomic, immutable captures and scoped exact evidence queries."""
from __future__ import annotations

import json
import time

from .codec import digest, encode, new_id
from .models import Capture, MarketTurnContext
from .projection import project_context

MAX_CAPTURE_BYTES = 8 * 1024 * 1024
DETAIL_READ_LIMITS = {"quick": 100, "balanced": 500, "deep": 2000}


class ObservationStore:
    def capture(self, session_key: str, capture_id: str, raw: dict) -> dict:
        if not isinstance(session_key, str) or not 0 < len(session_key) <= 160:
            raise ValueError("sessionKey is required")
        if not isinstance(capture_id, str) or not 0 < len(capture_id) <= 160:
            raise ValueError("captureId is required")
        if len(encode(raw).encode()) > MAX_CAPTURE_BYTES:
            raise ValueError("Chart capture exceeds 8 MiB; reduce loaded resources and retry")
        capture = Capture.model_validate(raw).model_dump(by_alias=True)
        if type(capture["settings"].get("includeAccountContext", False)) is not bool:
            raise ValueError("includeAccountContext must be a boolean")
        fingerprint = digest(capture)
        resources = capture.pop("resources")
        for resource in resources:
            if resource["metadata"].get("accountContext") and resource["rows"] and not capture["settings"].get("includeAccountContext", False):
                raise ValueError("Account-derived resources are excluded from chart captures")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT * FROM observations WHERE session_key=? AND capture_id=?",
                                  (session_key, capture_id)).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise ValueError("captureId already used with a different capture")
                return json.loads(previous["body"])
            document = self._document(db, capture["documentId"])
            if document["instrument"] != capture["instrument"]:
                raise ValueError("Captured instrument does not match the chart document")
            if document["revision"] != capture["documentRevision"]:
                raise ValueError("Chart document changed before capture; refresh and retry")
            captured_drawings = next((r for r in resources if r["kind"] == "drawings"), None)
            if captured_drawings and captured_drawings["rows"] != document["objects"]:
                raise ValueError("Captured drawings differ from document revision")
            if not captured_drawings:
                if any(resource["key"] == "drawings" for resource in resources):
                    raise ValueError("Resource key drawings is reserved for drawing records")
                if len(resources) >= 32:
                    raise ValueError("Reserve one resource slot for displayed drawings")
                resources.append({"key": "drawings", "kind": "drawings", "label": "Chart drawings",
                                  "status": "loaded" if document["objects"] else "empty",
                                  "rows": document["objects"], "metadata": {"documentRevision": document["revision"]}})
            added_bytes = 0
            encoded = []
            for resource in resources:
                body = encode(resource)
                resource_id = digest(resource)
                if not db.execute("SELECT 1 FROM resources WHERE id=?", (resource_id,)).fetchone():
                    added_bytes += len(body.encode())
                encoded.append((resource, resource_id, body))
            used_bytes = self._used_bytes(db)
            header_bytes = len(encode(capture).encode()) + sum(len(encode({key: value for key, value in resource.items() if key != "rows"}).encode()) for resource in resources) + 1024
            if used_bytes + added_bytes + header_bytes > self.capacity_bytes:
                raise ValueError("Chart evidence capacity reached; retained observations were not removed")
            observation = {**capture, "observationId": new_id("observation"), "sessionKey": session_key,
                           "capturedAt": time.time(), "provenance": "browser_capture", "resources": []}
            for resource, resource_id, _ in encoded:
                descriptor = {key: value for key, value in resource.items() if key != "rows"}
                observation["resources"].append({**descriptor, "resourceId": resource_id,
                                                 "rowCount": len(resource["rows"])})
            db.execute("INSERT INTO observations VALUES (?,?,?,?,?,?,?,0)", (
                observation["observationId"], session_key, capture_id, fingerprint,
                capture["documentId"], encode(observation), time.time()))
            for resource, resource_id, body in encoded:
                db.execute("INSERT OR IGNORE INTO resources VALUES (?,?,?)", (resource_id, body, len(body.encode())))
                db.execute("INSERT INTO observation_resources VALUES (?,?,?)", (
                    observation["observationId"], resource["key"], resource_id))
            return observation

    def observation(self, observation_id: str, session_key: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT body FROM observations WHERE id=? AND session_key=?",
                             (observation_id, session_key)).fetchone()
            if not row:
                raise ValueError("Chart observation unavailable for this session")
            return json.loads(row["body"])

    def document_evidence_observation(self, document_id: str, observation_id: str, resource_key: str) -> dict:
        """Operator-only evidence access survives session replacement and manual takeover."""
        with self.connect() as db:
            document = self._document(db, document_id)
            referenced = any(evidence["observationId"] == observation_id and evidence["resourceKey"] == resource_key
                             for obj in document["objects"] for evidence in obj["evidence"])
            if not referenced:
                raise ValueError("This evidence is not referenced by the current chart document")
            row = db.execute("SELECT body FROM observations WHERE id=? AND document_id=?",
                             (observation_id, document_id)).fetchone()
            if row is None:
                raise ValueError("Referenced chart evidence is unavailable")
            return json.loads(row["body"])

    def resolve_context(self, session_key: str, run_id: str, market_context: dict) -> MarketTurnContext:
        observation = self.observation(market_context["observationId"], session_key)
        if observation["documentId"] != market_context["documentId"] or observation["viewId"] != market_context["viewId"]:
            raise ValueError("Chart context document/view does not match the captured observation")
        detail = market_context.get("detail", "balanced")
        access = market_context.get("access", "read")
        if detail not in DETAIL_READ_LIMITS or access not in ("read", "annotate"):
            raise ValueError("Choose quick/balanced/deep detail and read/annotate chart access")
        return MarketTurnContext(
            observation_id=observation["observationId"], document_id=observation["documentId"],
            view_id=observation["viewId"], session_key=session_key, run_id=run_id,
            detail=detail, access=access,
            include_account_context=observation["settings"].get("includeAccountContext", False),
            resource_keys=tuple(r["key"] for r in observation["resources"] if not r["metadata"].get("accountContext") or observation["settings"].get("includeAccountContext", False)),
        )

    def context_payload(self, context: MarketTurnContext) -> dict:
        observation = self.observation(context.observation_id, context.session_key)
        return project_context(self, context, observation)

    def read_resource(self, context: MarketTurnContext, resource_key: str, offset: int = 0,
                      limit: int = 100, from_time: int | None = None, to_time: int | None = None,
                      observation_id: str | None = None, fields: list[str] | None = None,
                      metadata_path: list[str | int] | None = None) -> dict:
        if resource_key not in context.resource_keys:
            raise ValueError("Resource is outside this turn's captured scope")
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= DETAIL_READ_LIMITS[context.detail]:
            raise ValueError(f"Use offset >= 0 and limit 1–{DETAIL_READ_LIMITS[context.detail]} for {context.detail}")
        observation_id = observation_id or context.observation_id
        observation = self.observation(observation_id, context.session_key)
        if observation["documentId"] != context.document_id:
            raise ValueError("Historical observation belongs to another chart document")
        with self.connect() as db:
            row = db.execute("SELECT r.body FROM resources r JOIN observation_resources o ON r.id=o.resource_id "
                             "WHERE o.observation_id=? AND o.resource_key=?", (observation_id, resource_key)).fetchone()
            if row is None:
                raise ValueError("Captured resource unavailable")
            resource = json.loads(row["body"])
        if resource["metadata"].get("accountContext") and not context.include_account_context:
            raise ValueError("Account-derived evidence is excluded")
        rows = resource.pop("rows")
        if metadata_path is not None:
            value = resource["metadata"]
            try:
                for segment in metadata_path:
                    if isinstance(value, list):
                        if type(segment) is not int or segment < 0:
                            raise ValueError("Metadata list indexes must be nonnegative integers")
                    elif not isinstance(value, dict) or not isinstance(segment, str):
                        raise ValueError("Metadata object paths must use field names")
                    value = value[segment]
            except (KeyError, IndexError) as exc:
                raise ValueError("Metadata path does not exist in the captured resource") from exc
            values = value if isinstance(value, list) else [value]
            rows = [item if isinstance(item, dict) else {"value": item} for item in values]
            resource["metadataPath"] = metadata_path
        total = len(rows)
        if from_time is not None or to_time is not None:
            rows = [row for row in rows if row.get("t") is not None
                    and (from_time is None or row["t"] >= from_time)
                    and (to_time is None or row["t"] <= to_time)]
        matched = len(rows)
        selected = rows[offset:offset + limit]
        if fields is not None:
            available = {key for row in rows for key in row}
            if set(fields) - available:
                raise ValueError("Requested fields do not exist in captured resource")
            selected = [{key: row[key] for key in fields if key in row} for row in selected]
        max_chars = {"quick": 12000, "balanced": 30000, "deep": 60000}[context.detail]
        if len(encode(resource)) > max_chars // 2:
            resource["metadata"] = {"omitted": "Resource metadata exceeds this query budget"}
        while selected and len(encode(selected)) > max_chars:
            if len(selected) == 1:
                raise ValueError("One row exceeds the query budget; request narrower fields or metadataPath")
            selected = selected[:len(selected) // 2]
        return {**resource, "observationId": observation_id, "provenance": "browser_capture",
                "instrument": observation["instrument"], "requestedRange": {"from": from_time, "to": to_time},
                "totalCount": total, "matchedCount": matched, "returnedCount": len(selected),
                "offset": offset, "nextOffset": offset + len(selected) if offset + len(selected) < matched else None,
                "rows": selected}
