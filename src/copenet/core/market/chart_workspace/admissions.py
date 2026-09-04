"""Durable run admission identity; uncertain runs are never silently redispatched."""


class AdmissionStore:
    def get_admission(self, session_key: str, idempotency_key: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM admissions WHERE session_key=? AND idempotency_key=?",
                             (session_key, idempotency_key)).fetchone()
            return self._admission_wire(row, False) if row else None

    def reserve_admission(self, session_key: str, idempotency_key: str, fingerprint: str,
                          run_id: str, observation_id: str) -> dict:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT * FROM admissions WHERE session_key=? AND idempotency_key=?",
                                  (session_key, idempotency_key)).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise ValueError("Chart request key already used with different content or authority")
                return self._admission_wire(previous, False)
            observation = db.execute("SELECT 1 FROM observations WHERE id=? AND session_key=?",
                                     (observation_id, session_key)).fetchone()
            if observation is None:
                raise ValueError("Cannot admit unavailable chart evidence")
            added_bytes = sum(len(value.encode()) for value in (session_key, idempotency_key, fingerprint, run_id, observation_id)) + 32
            if self._used_bytes(db) + added_bytes > self.capacity_bytes:
                raise ValueError("Chart store capacity reached; model request was not admitted")
            db.execute("INSERT INTO admissions VALUES (?,?,?,?,?,?)", (
                session_key, idempotency_key, fingerprint, run_id, observation_id, "admitted"))
            db.execute("UPDATE observations SET bound=1 WHERE id=?", (observation_id,))
            return {"new": True, "runId": run_id, "state": "admitted", "fingerprint": fingerprint,
                    "observationId": observation_id}

    def update_admission(self, session_key: str, idempotency_key: str, state: str):
        if state not in ("admitted", "dispatched", "completed", "failed", "interrupted"):
            raise ValueError("Unknown chart admission state")
        with self.connect() as db:
            row = db.execute("SELECT state FROM admissions WHERE session_key=? AND idempotency_key=?",
                             (session_key, idempotency_key)).fetchone()
            if not row:
                raise ValueError("Chart admission unavailable")
            if row[0] in ("completed", "failed", "interrupted") and state != row[0]:
                raise ValueError("Terminal chart admissions cannot be redispatched")
            db.execute("UPDATE admissions SET state=? WHERE session_key=? AND idempotency_key=?",
                       (state, session_key, idempotency_key))

    @staticmethod
    def _admission_wire(row, new):
        return {"new": new, "runId": row["run_id"], "state": row["state"],
                "fingerprint": row["fingerprint"], "observationId": row["observation_id"]}
