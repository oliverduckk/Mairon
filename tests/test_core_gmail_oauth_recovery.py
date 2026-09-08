import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

# Normal installed location when copied to Mairon/tests.
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SRC_DIR),
    )


# This regression runs inside Mairon's normal Windows venv, where the Google
# libraries are installed. It deliberately exercises Mairon's auth policy with
# fakes so no real browser, token, account, or network request is touched.
import tools.gmail_tools as gmail_tools


class _ExpiredCredentials:
    valid = False
    expired = True
    refresh_token = "refresh-token"

    def __init__(
        self,
        refresh_error=None,
    ):
        self.refresh_error = refresh_error
        self.refresh_calls = 0

    def refresh(
        self,
        request,
    ):
        self.refresh_calls += 1

        if self.refresh_error is not None:
            raise self.refresh_error

        self.valid = True
        self.expired = False

    def to_json(self):
        return '{"token":"refreshed"}'


class _FreshCredentials:
    valid = True
    expired = False
    refresh_token = "new-refresh-token"

    def to_json(self):
        return '{"token":"fresh-oauth"}'


class _CredentialsLoader:
    loaded = None
    calls = 0

    @classmethod
    def from_authorized_user_file(
        cls,
        filename,
        scopes,
    ):
        cls.calls += 1
        return cls.loaded


class _Flow:
    def __init__(
        self,
        fresh_credentials,
    ):
        self.fresh_credentials = fresh_credentials
        self.run_calls = 0

    def run_local_server(
        self,
        port=0,
    ):
        assert port == 0
        self.run_calls += 1
        return self.fresh_credentials


class _FlowFactory:
    flow = None
    create_calls = 0

    @classmethod
    def from_client_secrets_file(
        cls,
        filename,
        scopes,
    ):
        cls.create_calls += 1
        return cls.flow


def _reset_fakes():
    _CredentialsLoader.calls = 0
    _FlowFactory.create_calls = 0
    _FlowFactory.flow = None


def run():
    original = {
        "GOOGLE_DATA_DIR": gmail_tools.GOOGLE_DATA_DIR,
        "CREDENTIALS_PATH": gmail_tools.CREDENTIALS_PATH,
        "TOKEN_PATH": gmail_tools.TOKEN_PATH,
        "Credentials": gmail_tools.Credentials,
        "InstalledAppFlow": gmail_tools.InstalledAppFlow,
        "Request": gmail_tools.Request,
    }

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(
                temp_dir
            )

            google_dir = root / "google"
            google_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            credentials_path = (
                google_dir
                / "credentials.json"
            )

            token_path = (
                google_dir
                / "gmail_token.json"
            )

            credentials_path.write_text(
                "{}",
                encoding="utf-8",
            )

            token_path.write_text(
                '{"token":"stale"}',
                encoding="utf-8",
            )

            gmail_tools.GOOGLE_DATA_DIR = (
                google_dir
            )
            gmail_tools.CREDENTIALS_PATH = (
                credentials_path
            )
            gmail_tools.TOKEN_PATH = (
                token_path
            )
            gmail_tools.Credentials = (
                _CredentialsLoader
            )
            gmail_tools.InstalledAppFlow = (
                _FlowFactory
            )
            gmail_tools.Request = lambda: object()

            # --------------------------------------------------
            # 1. Ordinary expired credentials refresh silently.
            # --------------------------------------------------

            _reset_fakes()

            expired = _ExpiredCredentials()
            _CredentialsLoader.loaded = expired

            fresh = _FreshCredentials()
            flow = _Flow(
                fresh
            )
            _FlowFactory.flow = flow

            result = gmail_tools.get_credentials()

            assert result is expired
            assert expired.refresh_calls == 1
            assert _FlowFactory.create_calls == 0
            assert flow.run_calls == 0
            assert token_path.read_text(
                encoding="utf-8"
            ) == '{"token":"refreshed"}'

            # --------------------------------------------------
            # 2. Revoked/expired grant self-recovers via OAuth.
            # --------------------------------------------------

            _reset_fakes()

            revoked_error = gmail_tools.RefreshError(
                "invalid_grant: Token has been expired or revoked."
            )

            revoked = _ExpiredCredentials(
                refresh_error=revoked_error,
            )

            _CredentialsLoader.loaded = revoked

            fresh = _FreshCredentials()
            flow = _Flow(
                fresh
            )
            _FlowFactory.flow = flow

            result = gmail_tools.get_credentials()

            assert result is fresh
            assert revoked.refresh_calls == 1
            assert _FlowFactory.create_calls == 1
            assert flow.run_calls == 1
            assert token_path.read_text(
                encoding="utf-8"
            ) == '{"token":"fresh-oauth"}'

            # --------------------------------------------------
            # 3. Transient refresh failure stays fail-closed.
            #    It must NOT start a browser OAuth loop.
            # --------------------------------------------------

            _reset_fakes()

            transient_error = gmail_tools.RefreshError(
                "temporary transport failure"
            )

            transient = _ExpiredCredentials(
                refresh_error=transient_error,
            )

            _CredentialsLoader.loaded = transient

            fresh = _FreshCredentials()
            flow = _Flow(
                fresh
            )
            _FlowFactory.flow = flow

            try:
                gmail_tools.get_credentials()

            except gmail_tools.RefreshError as error:
                assert error is transient_error

            else:
                raise AssertionError(
                    "Transient refresh errors must propagate instead of "
                    "opening interactive OAuth."
                )

            assert transient.refresh_calls == 1
            assert _FlowFactory.create_calls == 0
            assert flow.run_calls == 0

            # --------------------------------------------------
            # 4. The exact observed Google error is recognised.
            # --------------------------------------------------

            assert gmail_tools._refresh_error_requires_reauthentication(
                gmail_tools.RefreshError(
                    "invalid_grant: Token has been expired or revoked.",
                    {
                        "error": "invalid_grant",
                        "error_description": "Token has been expired or revoked.",
                    },
                )
            ) is True

            assert gmail_tools._refresh_error_requires_reauthentication(
                gmail_tools.RefreshError(
                    "temporary transport failure"
                )
            ) is False

    finally:
        gmail_tools.GOOGLE_DATA_DIR = original[
            "GOOGLE_DATA_DIR"
        ]
        gmail_tools.CREDENTIALS_PATH = original[
            "CREDENTIALS_PATH"
        ]
        gmail_tools.TOKEN_PATH = original[
            "TOKEN_PATH"
        ]
        gmail_tools.Credentials = original[
            "Credentials"
        ]
        gmail_tools.InstalledAppFlow = original[
            "InstalledAppFlow"
        ]
        gmail_tools.Request = original[
            "Request"
        ]

    print(
        "Gmail OAuth self-recovery regression tests: PASS"
    )


if __name__ == "__main__":
    run()
