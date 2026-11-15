"""Job store on S3 with conditional writes.

One JSON document per job at ``jobs/<job_id>.json``. Every write is
conditional, so there is no code path that can overwrite a job blindly:

* create  -> ``If-None-Match: *``   (the key must not exist yet)
* update  -> ``If-Match: <etag>``   (compare-and-swap on the version we read)

Lifecycle: ``QUEUED -> RUNNING -> SUCCEEDED | FAILED`` (``QUEUED -> FAILED``
is allowed for a dispatch failure or an expired deadline). ``SUCCEEDED`` and
``FAILED`` are terminal and immutable: :meth:`JobStore.update` refuses to
touch a terminal job whatever the caller asks for.

Results and traces are separate write-once objects (``results/<id>.json``,
``traces/<id>.json``).

The IAM policies in ``infra/template.yaml`` enforce the same rules a second
time: ``s3:PutObject`` is only allowed when the request carries the matching
conditional header.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Callable

from botocore.exceptions import ClientError

from backend.common import log
from backend.common.clock import to_iso

QUEUED = "QUEUED"
RUNNING = "RUNNING"
SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"

TERMINAL_STATUSES = frozenset({SUCCEEDED, FAILED})
ALLOWED_TRANSITIONS = {
    QUEUED: frozenset({RUNNING, FAILED}),
    RUNNING: frozenset({SUCCEEDED, FAILED}),
}

# The contract id pattern allows no underscore: "inv-" + 32 hexadecimal characters.
JOB_ID_RE = re.compile(r"inv-[0-9a-f]{32}")

_PRECONDITION_FAILED = {"PreconditionFailed", "412"}
_CONDITIONAL_CONFLICT = {"ConditionalRequestConflict", "409"}
_NOT_FOUND = {"NoSuchKey", "404", "NotFound"}
_ACCESS_DENIED = {"AccessDenied", "403"}


class JobStoreError(Exception):
    """Base class for job store failures."""


class JobNotFoundError(JobStoreError):
    pass


class TerminalStateError(JobStoreError):
    """The job is already SUCCEEDED or FAILED. Carries the stored job."""

    def __init__(self, job: dict[str, Any]) -> None:
        super().__init__(f"job {job.get('id')} is terminal ({job.get('status')})")
        self.job = job


class StateConflict(JobStoreError):
    """Raised by a mutation callback that finds the job in an unexpected state."""

    def __init__(self, message: str, job: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.job = job


class InvalidTransitionError(JobStoreError):
    pass


class ConcurrentUpdateError(JobStoreError):
    """Compare-and-swap kept losing. The caller decides whether to give up."""


def is_valid_job_id(value: Any) -> bool:
    return isinstance(value, str) and JOB_ID_RE.fullmatch(value) is not None


def job_key(job_id: str) -> str:
    return f"jobs/{job_id}.json"


def result_key(job_id: str) -> str:
    return f"results/{job_id}.json"


def trace_key(job_id: str) -> str:
    return f"traces/{job_id}.json"


def _error_code(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code", ""))


def correction_prefix(job_id: str) -> str:
    return f"jobs/{job_id}/corrections/"


def _dumps(document: dict[str, Any]) -> bytes:
    # UTF-8 end to end: formula strings contain characters such as "≈".
    return json.dumps(document, separators=(",", ":"), sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")


class JobStore:
    """S3-backed job documents.

    ``can_list`` says whether the caller's role holds ``s3:ListBucket`` on the
    ``jobs/`` prefix. Without that permission S3 answers 403 (not 404) for a
    key that does not exist, so a caller that must tell "absent" from "denied"
    (the API, for its 404) needs it; the worker does not.
    """

    def __init__(self, s3: Any, bucket: str, clock: Any, *, can_list: bool = False) -> None:
        self._s3 = s3
        self._bucket = bucket
        self._clock = clock
        self._can_list = can_list

    # ------------------------------------------------------------------ reads

    def _get_json(self, key: str) -> tuple[dict[str, Any], str] | None:
        try:
            response = self._s3.get_object(Bucket=self._bucket, Key=key)
        except ClientError as error:
            code = _error_code(error)
            if code in _NOT_FOUND:
                return None
            if code in _ACCESS_DENIED and self._can_list and not self._exists(key):
                # S3 answers 403 for a missing key unless the caller may list it.
                log.info("s3_missing_key_confirmed_by_listing", key=key)
                return None
            raise
        body = response["Body"]
        try:
            raw = body.read()
        finally:
            body.close()
        return json.loads(raw.decode("utf-8")), response["ETag"]

    def _exists(self, key: str) -> bool:
        listing = self._s3.list_objects_v2(Bucket=self._bucket, Prefix=key, MaxKeys=1)
        return any(item.get("Key") == key for item in listing.get("Contents", []))

    def get(self, job_id: str) -> tuple[dict[str, Any], str] | None:
        """Return ``(job, etag)`` or ``None`` when the job does not exist."""
        return self._get_json(job_key(job_id))

    def get_result(self, job_id: str) -> dict[str, Any] | None:
        found = self._get_json(result_key(job_id))
        return found[0] if found else None

    # ----------------------------------------------------------------- writes

    def _put(self, key: str, document: dict[str, Any], *, if_none_match: bool = False, if_match: str | None = None) -> str:
        if if_none_match == (if_match is not None):
            raise ValueError("exactly one of if_none_match / if_match is required: unconditional writes are not allowed")
        arguments: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": key,
            "Body": _dumps(document),
            "ContentType": "application/json; charset=utf-8",
        }
        if if_none_match:
            arguments["IfNoneMatch"] = "*"
        else:
            arguments["IfMatch"] = if_match
        return self._s3.put_object(**arguments)["ETag"]

    def create(self, job: dict[str, Any]) -> tuple[dict[str, Any], str, bool]:
        """Create the job unless one with the same id exists.

        Returns ``(job, etag, created)``. When ``created`` is false the
        returned job is the one already stored, not the argument.
        """
        key = job_key(job["id"])
        for _ in range(4):
            try:
                etag = self._put(key, job, if_none_match=True)
                return job, etag, True
            except ClientError as error:
                code = _error_code(error)
                if code in _CONDITIONAL_CONFLICT:
                    continue  # a concurrent create is in flight: S3 asks us to retry
                if code not in _PRECONDITION_FAILED:
                    raise
            existing = self.get(job["id"])
            if existing is not None:
                return existing[0], existing[1], False
            # Lost the race and the winner's object is not readable yet: retry.
        raise ConcurrentUpdateError(f"could not create or read job {job['id']}")

    def update(
        self,
        job_id: str,
        mutate: Callable[[dict[str, Any]], dict[str, Any] | None],
        *,
        max_attempts: int = 6,
    ) -> dict[str, Any]:
        """Read-modify-write with compare-and-swap.

        ``mutate`` receives a private copy of the stored job and returns the
        new document (or mutates the copy in place and returns ``None``). It
        runs again on every retry, always against the latest stored version,
        and may raise :class:`StateConflict` to abandon the update.

        Raises :class:`TerminalStateError` without calling ``mutate`` when the
        stored job is terminal.
        """
        for attempt in range(1, max_attempts + 1):
            found = self.get(job_id)
            if found is None:
                raise JobNotFoundError(job_id)
            current, etag = found
            before = current.get("status")
            if before in TERMINAL_STATUSES:
                raise TerminalStateError(current)
            draft = copy.deepcopy(current)
            returned = mutate(draft)
            updated = draft if returned is None else returned
            after = updated.get("status")
            if after != before and after not in ALLOWED_TRANSITIONS.get(before, frozenset()):
                raise InvalidTransitionError(f"{before} -> {after} is not an allowed transition")
            if updated.get("id") != job_id:
                raise InvalidTransitionError("a job id cannot change")
            updated["updated_at"] = to_iso(self._clock.time())
            try:
                self._put(job_key(job_id), updated, if_match=etag)
                return updated
            except ClientError as error:
                code = _error_code(error)
                if code not in _PRECONDITION_FAILED and code not in _CONDITIONAL_CONFLICT:
                    raise
                log.info("job_update_conflict", job_id=job_id, attempt=attempt, s3_error=code)
        raise ConcurrentUpdateError(f"job {job_id} changed {max_attempts} times while being updated")

    def _put_once(self, key: str, document: dict[str, Any]) -> bool:
        """Write-once object. Returns False when the key already exists."""
        for _ in range(3):
            try:
                self._put(key, document, if_none_match=True)
                return True
            except ClientError as error:
                code = _error_code(error)
                if code in _PRECONDITION_FAILED:
                    return False
                if code not in _CONDITIONAL_CONFLICT:
                    raise
        return False

    def put_result(self, job_id: str, result: dict[str, Any]) -> bool:
        return self._put_once(result_key(job_id), result)

    def put_trace(self, job_id: str, trace: dict[str, Any]) -> bool:
        return self._put_once(trace_key(job_id), trace)

    # ------------------------------------------------------------ corrections

    def put_correction(self, job_id: str, correction: dict[str, Any]) -> bool:
        """A proposed correction is its own write-once object next to the job.

        The terminal job document is never rewritten: ``proposed_corrections`` is the one member
        allowed to grow after a terminal state, and it grows by adding objects, not by editing.
        """
        return self._put_once(correction_prefix(job_id) + f"{correction['correction_id']}.json", correction)

    def list_corrections(self, job_id: str) -> list[dict[str, Any]]:
        """Needs ``s3:ListBucket`` on the ``jobs/`` prefix (the API role)."""
        listing = self._s3.list_objects_v2(Bucket=self._bucket, Prefix=correction_prefix(job_id), MaxKeys=200)
        corrections = []
        for item in listing.get("Contents", []):
            found = self._get_json(item["Key"])
            if found is not None:
                corrections.append(found[0])
        return sorted(corrections, key=lambda c: (c["provenance"]["asserted_at"], c["correction_id"]))
