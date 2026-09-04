"""Revision-checked drawing batches, provenance, compensating undo, and paint receipts."""
from __future__ import annotations

import json
import time

from .authorization import actor_for, assert_document_scope, assert_object_scope
from .codec import digest, encode, new_id
from .models import ApplyRequest, ChartObject, UndoRequest


class DocumentStore:
    @staticmethod
    def _document(db, document_id):
        row = db.execute("SELECT body FROM documents WHERE id=?", (document_id,)).fetchone()
        if row is None:
            raise ValueError("Chart document unavailable")
        return json.loads(row["body"])

    def document(self, document_id: str, context=None) -> dict:
        assert_document_scope(context, document_id)
        with self.connect() as db:
            document = self._document(db, document_id)
            receipts = [{key: value for key, value in json.loads(row["receipt"]).items() if key != "document"} for row in db.execute(
                "SELECT receipt FROM operations WHERE document_id=? ORDER BY rowid DESC LIMIT 50", (document_id,))]
            renders = [json.loads(row["body"]) for row in db.execute(
                "SELECT body FROM render_receipts WHERE document_id=? AND revision=?", (document_id, document["revision"]))]
            return {"document": document, "batches": receipts, "renderStatus": renders}

    def apply(self, raw: dict, context=None) -> dict:
        request = ApplyRequest.model_validate(raw)
        payload = request.model_dump(by_alias=True, exclude_none=True)
        actor = actor_for(context)
        assert_document_scope(context, request.documentId)
        fingerprint = digest({"request": payload, "actor": actor})
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = self._dedupe(db, request.documentId, request.operationId, fingerprint)
            if previous:
                return previous
            document = self._document(db, request.documentId)
            if document["revision"] != request.expectedRevision:
                raise ValueError("Chart revision conflict; read the current document and use a new operationId")
            objects = {obj["id"]: obj for obj in document["objects"]}
            before, after = {}, {}
            for operation in payload["operations"]:
                object_id = operation["object"]["id"] if operation["kind"] == "create" else operation["objectId"]
                if object_id in before:
                    raise ValueError("A batch may touch each object only once")
                old = objects.get(object_id)
                before[object_id] = old
                if operation["kind"] == "create":
                    if old is not None:
                        raise ValueError("Drawing object id already exists")
                    obj = {**operation["object"], "owner": actor}
                else:
                    if old is None:
                        raise ValueError("Drawing object unavailable")
                    assert_object_scope(context, old)
                    obj = None if operation["kind"] == "delete" else {**old, **operation["patch"], "owner": actor}
                if obj is None:
                    objects.pop(object_id)
                else:
                    obj = ChartObject.model_validate(obj).model_dump(by_alias=True, exclude_none=True)
                    self._validate_evidence(db, document, obj, context)
                    objects[object_id] = obj
                after[object_id] = obj
            if len(objects) > 200:
                raise ValueError("Chart documents support up to 200 drawings")
            document["objects"] = list(objects.values())
            return self._commit_batch(db, request.documentId, request.operationId, fingerprint,
                                      document, before, after, actor)

    def undo(self, raw: dict, context=None) -> dict:
        request = UndoRequest.model_validate(raw)
        actor = actor_for(context)
        assert_document_scope(context, request.documentId)
        fingerprint = digest({"request": request.model_dump(), "actor": actor})
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = self._dedupe(db, request.documentId, request.operationId, fingerprint)
            if previous:
                return previous
            document = self._document(db, request.documentId)
            if document["revision"] != request.expectedRevision:
                raise ValueError("Chart revision conflict; read the current document before undo")
            row = db.execute("SELECT body FROM operations WHERE batch_id=? AND document_id=?",
                             (request.batchId, request.documentId)).fetchone()
            if row is None:
                raise ValueError("Drawing batch unavailable")
            batch = json.loads(row["body"])
            if context is not None and (batch["actor"]["kind"] != "agent" or batch["actor"].get("sessionKey") != context.session_key):
                raise ValueError("This batch belongs to the operator or another session")
            objects = {obj["id"]: obj for obj in document["objects"]}
            for object_id, expected in batch["after"].items():
                current = objects.get(object_id)
                if current != expected:
                    raise ValueError("Undo conflicts with a later edit to an affected object")
                if current is not None:
                    assert_object_scope(context, current)
            restored = {}
            for object_id, old in batch["before"].items():
                if old is None:
                    objects.pop(object_id, None)
                    restored[object_id] = None
                else:
                    # Undo is an explicit edit. A human taking over an agent drawing retains control.
                    restored[object_id] = {**old, "owner": actor}
                    objects[object_id] = restored[object_id]
            if len(objects) > 200:
                raise ValueError("Undo would exceed the 200 drawing limit")
            document["objects"] = list(objects.values())
            return self._commit_batch(db, request.documentId, request.operationId, fingerprint,
                                      document, batch["after"], restored, actor, undo_of=request.batchId)

    @staticmethod
    def _dedupe(db, document_id, operation_id, fingerprint):
        row = db.execute("SELECT * FROM operations WHERE document_id=? AND operation_id=?",
                         (document_id, operation_id)).fetchone()
        if row is None:
            return None
        if row["fingerprint"] != fingerprint:
            raise ValueError("operationId already used with a different batch or actor")
        return json.loads(row["receipt"])

    def _commit_batch(self, db, document_id, operation_id, fingerprint, document, before, after, actor, undo_of=None):
        document["revision"] += 1
        receipt = {"batchId": new_id("batch"), "documentId": document_id, "revision": document["revision"],
                   "status": "applied", "objectIds": list(after), "renderStatus": "pending",
                   "document": document}
        body = {"before": before, "after": after, "actor": actor, "undoOf": undo_of, "createdAt": time.time()}
        if self._used_bytes(db) + len(encode(body).encode()) + len(encode(receipt).encode()) > self.capacity_bytes:
            raise ValueError("Chart store capacity reached; drawing batch was not applied")
        db.execute("UPDATE documents SET revision=?,body=? WHERE id=?",
                   (document["revision"], encode(document), document_id))
        db.execute("INSERT INTO operations VALUES (?,?,?,?,?,?)", (
            receipt["batchId"], document_id, operation_id, fingerprint, encode(body), encode(receipt)))
        return receipt

    def _validate_evidence(self, db, document, obj, context):
        if context is not None and not obj["evidence"]:
            raise ValueError("Agent drawings require evidence references from this observation")
        for evidence in obj["evidence"]:
            if context is not None and (evidence["observationId"] != context.observation_id
                                       or evidence["resourceKey"] not in context.resource_keys):
                raise ValueError("Drawing evidence is outside this turn's observation")
            row = db.execute("SELECT o.document_id,r.body FROM observations o "
                             "JOIN observation_resources x ON x.observation_id=o.id "
                             "JOIN resources r ON r.id=x.resource_id WHERE o.id=? AND x.resource_key=?",
                             (evidence["observationId"], evidence["resourceKey"])).fetchone()
            if row is None or row["document_id"] != document["documentId"]:
                raise ValueError("Drawing evidence does not resolve to this document")
            resource = json.loads(row["body"])
            times = {r["t"] for r in resource["rows"] if "t" in r}
            for bound in (evidence.get("from"), evidence.get("to")):
                if bound is not None and bound not in times:
                    raise ValueError("Evidence bounds must refer to exact captured timestamps")
            db.execute("UPDATE observations SET bound=1 WHERE id=?", (evidence["observationId"],))
        if context is not None:
            observation = json.loads(db.execute("SELECT body FROM observations WHERE id=?", (context.observation_id,)).fetchone()[0])
            if obj["timeframe"] != observation["timeframe"]:
                raise ValueError("Drawing timeframe must match the captured chart")
            if observation["settings"].get("comparisonMode") is True or observation["settings"].get("comparisonMode") in ("indexed", "rebased", "percent"):
                raise ValueError("Price drawings are unavailable on comparison axes")
            candle_rows = db.execute("SELECT r.body FROM resources r JOIN observation_resources o ON r.id=o.resource_id WHERE o.observation_id=?",
                                     (context.observation_id,)).fetchall()
            candle_times = {r["t"] for row in candle_rows for resource in [json.loads(row[0])]
                            if resource["kind"] == "candles" and resource["metadata"].get("timeframe") == obj["timeframe"]
                            for r in resource["rows"] if "t" in r}
            if any(anchor["t"] not in candle_times for anchor in obj["anchors"]):
                raise ValueError("Drawing anchors must use captured candle timestamps")

    def rendered(self, raw: dict) -> dict:
        from .requests import RenderRequest
        receipt = RenderRequest.model_validate(raw).model_dump(exclude_none=True)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            document = self._document(db, receipt["documentId"])
            if receipt["revision"] > document["revision"]:
                raise ValueError("Cannot acknowledge an unsaved document revision")
            if receipt["revision"] == document["revision"]:
                known = {obj["id"] for obj in document["objects"]}
                if set(receipt["objectIds"]) - known:
                    raise ValueError("Render receipt contains unknown object ids")
            receipt["receivedAt"] = time.time()
            previous = db.execute("SELECT length(CAST(body AS BLOB)) FROM render_receipts WHERE document_id=? AND view_id=? AND revision=?",
                                  (receipt["documentId"], receipt["viewId"], receipt["revision"])).fetchone()
            replaced_bytes = previous[0] if previous else 0
            if self._used_bytes(db) - replaced_bytes + len(encode(receipt).encode()) > self.capacity_bytes:
                raise ValueError("Chart store capacity reached; display receipt was not recorded")
            db.execute("INSERT INTO render_receipts VALUES (?,?,?,?) ON CONFLICT(document_id,view_id,revision) DO UPDATE SET body=excluded.body",
                       (receipt["documentId"], receipt["viewId"], receipt["revision"], encode(receipt)))
        return receipt
