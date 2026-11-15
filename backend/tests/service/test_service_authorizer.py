"""Lambda authorizer: accepts the right bearer token, rejects everything else, fails closed."""

import pytest

from backend.api.authorizer import AccessCodeAuthorizer
from backend.common.config import AuthorizerConfig, ConfigurationError
from service_fakes import FakeClock, FakeSSM, client_error

CODE = "correct-horse-battery-staple-0123456789"
PARAMETER = "/before-you-buy/access-code"


def make(value=CODE, ttl=60):
    ssm, clock = FakeSSM(value), FakeClock()
    return AccessCodeAuthorizer(ssm, AuthorizerConfig(parameter_name=PARAMETER, cache_ttl_seconds=ttl), clock), ssm, clock


def event(header=None, *, identity_source=True):
    result = {"version": "2.0", "type": "REQUEST", "routeKey": "GET /investigations/{id}", "headers": {}}
    if header is not None:
        result["headers"]["authorization"] = header
        if identity_source:
            result["identitySource"] = [header]
    return result


def test_au01_accepts_the_correct_bearer_token():
    authorizer, ssm, _ = make()
    assert authorizer.authorize(event(f"Bearer {CODE}")) == {"isAuthorized": True}
    assert ssm.calls == [{"Name": PARAMETER, "WithDecryption": True}]


def test_au02_scheme_is_case_insensitive_and_header_fallback_works():
    authorizer, _, _ = make()
    assert authorizer.authorize(event(f"bearer {CODE}"))["isAuthorized"] is True
    assert authorizer.authorize(event(f"Bearer {CODE}", identity_source=False))["isAuthorized"] is True


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        CODE,  # no scheme
        f"Basic {CODE}",
        "Bearer ",
        "Bearer wrong-code-wrong-code-wrong-code",
        f"Bearer {CODE}x",
        f"Bearer {CODE[:-1]}",
        f"Bearer {CODE.upper()}",
        "Bearer " + "x" * 2000,
    ],
)
def test_au03_rejects_missing_malformed_and_wrong_tokens(header):
    authorizer, _, _ = make()
    assert authorizer.authorize(event(header)) == {"isAuthorized": False}


def test_au04_stored_code_is_cached_briefly_then_refreshed():
    authorizer, ssm, clock = make(ttl=60)
    for _ in range(5):
        authorizer.authorize(event(f"Bearer {CODE}"))
    assert len(ssm.calls) == 1
    clock.advance(61)
    ssm.value = "rotated-code-rotated-code-rotated-code"
    assert authorizer.authorize(event(f"Bearer {CODE}"))["isAuthorized"] is False  # old code no longer works
    assert authorizer.authorize(event(f"Bearer {ssm.value}"))["isAuthorized"] is True
    assert len(ssm.calls) == 2


def test_au05_fails_closed_when_the_parameter_cannot_be_read():
    authorizer, ssm, _ = make()
    ssm.error = client_error("ParameterNotFound", "GetParameter")
    with pytest.raises(Exception):
        authorizer.authorize(event(f"Bearer {CODE}"))


def test_au06_fails_closed_on_an_implausibly_short_stored_code():
    authorizer, _, _ = make(value="short")
    with pytest.raises(ConfigurationError):
        authorizer.authorize(event("Bearer short"))


def test_au07_token_and_stored_code_never_reach_the_log(captured_log):
    authorizer, _, _ = make()
    authorizer.authorize(event(f"Bearer {CODE}"))
    authorizer.authorize(event("Bearer some-other-secret-looking-token-value"))
    output = captured_log.getvalue()
    assert "authorizer_decision" in output
    assert CODE not in output and "some-other-secret" not in output


def test_au08_missing_token_does_not_read_the_parameter():
    authorizer, ssm, _ = make()
    authorizer.authorize(event(None))
    assert ssm.calls == []
