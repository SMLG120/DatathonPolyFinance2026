# Sandbox snippet for the AWS MCP tool (run_script). Not a local script:
# `call_boto3`, `uuid`, `json` and `ClientError` are provided by the sandbox.
#
# Idempotent bootstrap of the two things that live outside the stack:
#   1. the private artifacts bucket that holds the Lambda zip and the template;
#   2. the access code, an SSM SecureString created out-of-band so that its
#      value never appears in the template, the repository, logs or output.
#
# Safe to run again: an existing bucket is left as it is (its settings are
# re-applied) and an existing parameter is never overwritten or read.

ACCOUNT = "010928212265"
REGION = "us-east-1"
ARTIFACTS_BUCKET = f"byb-artifacts-{ACCOUNT}-{REGION}"
ACCESS_CODE_PARAMETER = "/before-you-buy/access-code"


async def aws(service, operation, **params):
    return await call_boto3(service_name=service, operation_name=operation, region_name=REGION, params=params)


identity = await aws("sts", "GetCallerIdentity")
if identity.get("Account") != ACCOUNT:
    raise RuntimeError("Refusing to continue: this is not the authorized account.")

report = {"account": identity["Account"], "bucket": ARTIFACTS_BUCKET, "parameter": ACCESS_CODE_PARAMETER}

existing = [b["Name"] for b in (await aws("s3", "ListBuckets")).get("Buckets", [])]
if ARTIFACTS_BUCKET in existing:
    report["bucket_action"] = "already existed"
else:
    await aws("s3", "CreateBucket", Bucket=ARTIFACTS_BUCKET)
    report["bucket_action"] = "created"

await aws(
    "s3",
    "PutPublicAccessBlock",
    Bucket=ARTIFACTS_BUCKET,
    PublicAccessBlockConfiguration={
        "BlockPublicAcls": True,
        "IgnorePublicAcls": True,
        "BlockPublicPolicy": True,
        "RestrictPublicBuckets": True,
    },
)
await aws(
    "s3",
    "PutBucketEncryption",
    Bucket=ARTIFACTS_BUCKET,
    ServerSideEncryptionConfiguration={"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]},
)
await aws(
    "s3",
    "PutBucketPolicy",
    Bucket=ARTIFACTS_BUCKET,
    Policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "DenyInsecureTransport",
                    "Effect": "Deny",
                    "Principal": "*",
                    "Action": "s3:*",
                    "Resource": [f"arn:aws:s3:::{ARTIFACTS_BUCKET}", f"arn:aws:s3:::{ARTIFACTS_BUCKET}/*"],
                    "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                }
            ],
        }
    ),
)
await aws(
    "s3",
    "PutBucketLifecycleConfiguration",
    Bucket=ARTIFACTS_BUCKET,
    LifecycleConfiguration={
        "Rules": [
            {"ID": "ExpireArtifacts", "Status": "Enabled", "Filter": {"Prefix": ""}, "Expiration": {"Days": 7}, "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1}},
            {"ID": "ExpireTransfers", "Status": "Enabled", "Filter": {"Prefix": "transfer/"}, "Expiration": {"Days": 1}},
        ]
    },
)
report["public_access_block"] = (await aws("s3", "GetPublicAccessBlock", Bucket=ARTIFACTS_BUCKET))["PublicAccessBlockConfiguration"]

# Access code: created only if absent. The value is generated here, from two
# random UUIDs (os.urandom underneath), and is never returned or printed.
try:
    await aws(
        "ssm",
        "PutParameter",
        Name=ACCESS_CODE_PARAMETER,
        Description="Before You Buy demo access code (bearer token checked by the Lambda authorizer).",
        Type="SecureString",
        Value=(uuid.uuid4().hex + uuid.uuid4().hex)[:48],
        Overwrite=False,
        Tags=[{"Key": "project", "Value": "before-you-buy"}],
    )
    report["parameter_action"] = "created"
except Exception as error:  # the sandbox surfaces AWS errors as exceptions
    if "ParameterAlreadyExists" not in str(error):
        raise
    report["parameter_action"] = "already existed (left unchanged)"

described = await aws("ssm", "DescribeParameters", ParameterFilters=[{"Key": "Name", "Values": [ACCESS_CODE_PARAMETER]}])
report["parameter_metadata"] = [
    {"Name": p["Name"], "Type": p["Type"], "KeyId": p.get("KeyId"), "Version": p.get("Version"), "Tier": p.get("Tier")}
    for p in described.get("Parameters", [])
]
result = report
result
