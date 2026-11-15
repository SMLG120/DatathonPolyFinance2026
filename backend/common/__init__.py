"""Shared service plumbing for the API, worker and authorizer Lambdas.

Standard library plus boto3 only. Nothing in this package calculates a
financial result: that belongs to ``backend/engine`` (phase 2).
"""
