"""Policy versions on S3: immutable, write-once objects ``policies/<policy_id>/v<version>.json``.

A version is created with ``If-None-Match: *`` and never rewritten, so an earlier version stays
exactly as it was confirmed. The latest version is found by listing the policy's prefix
(``s3:ListBucket`` restricted to ``policies/*`` for the API role).
"""

from __future__ import annotations

import json
import re
from typing import Any

from botocore.exceptions import ClientError

POLICY_ID_RE = re.compile(r"pol-[a-z0-9][a-z0-9-]{0,60}")
_VERSION_KEY_RE = re.compile(r"policies/[^/]+/v([1-9][0-9]{0,5})\.json")
_PRECONDITION = {"PreconditionFailed", "412", "ConditionalRequestConflict", "409"}
_MISSING = {"NoSuchKey", "404", "NotFound", "AccessDenied", "403"}


class PolicyVersionExists(Exception):
    """Another request created this version first."""


def is_valid_policy_id(value: Any) -> bool:
    return isinstance(value, str) and POLICY_ID_RE.fullmatch(value) is not None


def policy_key(policy_id: str, version: int) -> str:
    return f"policies/{policy_id}/v{version}.json"


class PolicyStore:
    def __init__(self, s3: Any, bucket: str, *, can_list: bool = True) -> None:
        self._s3, self._bucket, self._can_list = s3, bucket, can_list

    def get(self, policy_id: Any, version: Any) -> dict | None:
        """The stored version, or None. An id that cannot be a policy id is simply not found."""
        if not is_valid_policy_id(policy_id) or isinstance(version, bool) or not isinstance(version, int) or version < 1:
            return None
        try:
            response = self._s3.get_object(Bucket=self._bucket, Key=policy_key(policy_id, version))
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code in _MISSING:
                # Without s3:ListBucket on the key S3 answers 403 for a missing object. Policy keys are
                # only ever read by roles that hold s3:GetObject on policies/*, so 403 here means absent.
                return None
            raise
        body = response["Body"]
        try:
            return json.loads(body.read().decode("utf-8"))
        finally:
            body.close()

    def latest_version(self, policy_id: Any) -> int | None:
        if not is_valid_policy_id(policy_id):
            return None
        if not self._can_list:
            version = 0
            while self.get(policy_id, version + 1) is not None:
                version += 1
            return version or None
        listing = self._s3.list_objects_v2(Bucket=self._bucket, Prefix=f"policies/{policy_id}/v", MaxKeys=1000)
        versions = [int(match.group(1)) for item in listing.get("Contents", []) if (match := _VERSION_KEY_RE.fullmatch(item.get("Key", "")))]
        return max(versions) if versions else None

    def create(self, policy: dict) -> None:
        """Write-once. Raises PolicyVersionExists when the version is already stored."""
        body = json.dumps(policy, separators=(",", ":"), sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
        try:
            self._s3.put_object(Bucket=self._bucket, Key=policy_key(policy["policy_id"], policy["version"]), Body=body,
                                ContentType="application/json; charset=utf-8", IfNoneMatch="*")
        except ClientError as error:
            if str(error.response.get("Error", {}).get("Code", "")) in _PRECONDITION:
                raise PolicyVersionExists(policy_key(policy["policy_id"], policy["version"])) from error
            raise
