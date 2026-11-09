from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.services import otp

MAILER_URL = "https://mailer.example.test/exec"
MAILER_SECRET = "test-mailer-shared-secret"
OTP_CODE = "01234567"
RECIPIENT = "holder@example.com"


def install_mailer(
    monkeypatch: pytest.MonkeyPatch,
    transport: httpx.MockTransport,
) -> dict[str, object]:
    settings = SimpleNamespace(
        otp_mailer_url=MAILER_URL,
        otp_mailer_secret=SecretStr(MAILER_SECRET),
    )
    monkeypatch.setattr(otp, "get_settings", lambda: settings)

    client_options: dict[str, object] = {}
    client_class = httpx.Client

    def create_client(*, timeout: float, follow_redirects: bool) -> httpx.Client:
        client_options.update(
            timeout=timeout,
            follow_redirects=follow_redirects,
        )
        return client_class(
            transport=transport,
            timeout=timeout,
            follow_redirects=follow_redirects,
        )

    monkeypatch.setattr(otp.httpx, "Client", create_client)
    return client_options


def test_send_otp_email_posts_json_and_follows_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                302,
                headers={"Location": "https://mailer.example.test/result"},
                request=request,
            )
        return httpx.Response(200, json={"ok": True}, request=request)

    options = install_mailer(monkeypatch, httpx.MockTransport(handle_request))

    otp.send_otp_email(RECIPIENT, OTP_CODE)

    assert len(requests) == 2
    assert requests[0].method == "POST"
    assert str(requests[0].url) == MAILER_URL
    assert requests[0].read() == (
        b'{"secret":"test-mailer-shared-secret","email":"holder@example.com",'
        b'"code":"01234567"}'
    )
    assert requests[1].url == "https://mailer.example.test/result"
    assert options == {"timeout": 10, "follow_redirects": True}


@pytest.mark.parametrize(
    ("status_code", "body", "headers"),
    [
        (500, b'{"ok":true}', {"Content-Type": "application/json"}),
        (200, b'{"ok":false,"error":"rejected"}', {"Content-Type": "application/json"}),
        (200, b"not-json", {"Content-Type": "application/json"}),
    ],
)
def test_send_otp_email_rejects_unsuccessful_mailer_responses(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    body: bytes,
    headers: dict[str, str],
) -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            content=body,
            headers=headers,
            request=request,
        )

    install_mailer(monkeypatch, httpx.MockTransport(handle_request))

    with pytest.raises(otp.OtpDeliveryError):
        otp.send_otp_email(RECIPIENT, OTP_CODE)


def test_send_otp_email_requires_mailer_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        otp,
        "get_settings",
        lambda: SimpleNamespace(otp_mailer_url=None, otp_mailer_secret=None),
    )

    with pytest.raises(otp.OtpDeliveryError):
        otp.send_otp_email(RECIPIENT, OTP_CODE)


def test_mailer_settings_load_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTP_MAILER_URL", MAILER_URL)
    monkeypatch.setenv("OTP_MAILER_SECRET", MAILER_SECRET)

    settings = Settings(
        jwt_secret_key=SecretStr("test-jwt-secret-" + "x" * 32),
        otp_hmac_secret=SecretStr("test-otp-secret-" + "x" * 32),
        _env_file=None,
    )

    assert settings.otp_mailer_url == MAILER_URL
    assert settings.otp_mailer_secret is not None
    assert settings.otp_mailer_secret.get_secret_value() == MAILER_SECRET
