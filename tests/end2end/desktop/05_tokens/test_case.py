"""
@relation(SDOC-SRS-1235, scope=file)
@relation(SDOC-SRS-1239, scope=file)
"""

import json
import os
import sys
import tempfile
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, Optional, Tuple

import pytest

from tests.end2end.desktop.desktop_case import DesktopCase
from tests.end2end.desktop.desktop_test_server import DesktopTestServer
from tests.end2end.desktop.fake_gitlab import (
    CLIENT_ID,
    DISPLAY_NAME,
    REFRESH_INVALID_GRANT,
    FakeGitLab,
)
from tests.end2end.end2end_test_setup import End2EndTestSetup

SIGN_IN = '[data-testid="sign-in"]'
SIGNED_IN_USER = '[data-testid="signed-in-user"]'
OFFLINE_NOTICE = '[data-testid="offline-notice"]'
SIGN_IN_EXPIRED = '[data-testid="sign-in-expired"]'
WAIT_SECONDS = 30.0


@pytest.mark.skipif(
    sys.platform == "win32", reason="The user folders follow XDG variables."
)
class Test(DesktopCase):
    """
    The application is started twice with the same user folder: the second
    launch finds the tokens of the first one in the keyring (a keyring of the
    tests, in a file of the user folder) and does not ask the user to sign in.
    """

    def test_001_the_second_launch_is_signed_in_with_no_network(self) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with _create_environment() as (fake_gitlab, user_path):
            with self._create_server(
                test_setup, fake_gitlab, user_path
            ) as test_server:
                self.open(test_server.get_start_url())
                self.click(SIGN_IN)
                self.assert_text(DISPLAY_NAME, SIGNED_IN_USER)

                # The keyring holds the tokens, the settings hold none.
                record = _read_record(test_server)
                assert record["access_token"] != ""
                assert record["refresh_token"] != ""
                assert record["name"] == DISPLAY_NAME
                with open(
                    test_server.get_settings_path(), encoding="utf-8"
                ) as file_:
                    settings_text = file_.read()
                assert record["access_token"] not in settings_text
                assert record["refresh_token"] not in settings_text

            # GitLab is gone: a token that is still good needs no network.
            fake_gitlab.stop()
            with self._create_server(
                test_setup, fake_gitlab, user_path
            ) as test_server:
                self.open(test_server.get_start_url())

                self.assert_text(DISPLAY_NAME, SIGNED_IN_USER)
                self.assert_element_not_visible(SIGN_IN)
                self.assert_element_not_visible(OFFLINE_NOTICE)
            assert len(fake_gitlab.token_requests) == 1
            assert fake_gitlab.refresh_requests == []

    def test_002_a_token_that_has_ended_is_renewed_at_the_launch(self) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with _create_environment() as (fake_gitlab, user_path):
            with self._create_server(
                test_setup, fake_gitlab, user_path
            ) as test_server:
                self.open(test_server.get_start_url())
                self.click(SIGN_IN)
                self.assert_text(DISPLAY_NAME, SIGNED_IN_USER)
                old_record = _read_record(test_server)
                _end_access_token(test_server)

            with self._create_server(
                test_setup, fake_gitlab, user_path
            ) as test_server:
                self.open(test_server.get_start_url())
                self.assert_text(DISPLAY_NAME, SIGNED_IN_USER)

                # The timer renews the tokens: GitLab got the refresh token,
                # and the keyring holds the two new tokens.
                self._wait_until(lambda: len(fake_gitlab.refresh_requests) == 1)
                self._wait_until(
                    lambda: (
                        _read_record(test_server)["access_token"]
                        != old_record["access_token"]
                    )
                )
                new_record = _read_record(test_server)
                assert (
                    new_record["refresh_token"] != old_record["refresh_token"]
                )
                assert new_record["expires_at"] > time.time() + 3600
                assert fake_gitlab.refresh_requests == [
                    {"client_id": CLIENT_ID, "grant_type": "refresh_token"}
                ]
                self.assert_element_not_visible(SIGN_IN)

    def test_003_a_refusal_of_gitlab_goes_back_to_the_sign_in(self) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with _create_environment() as (fake_gitlab, user_path):
            with self._create_server(
                test_setup, fake_gitlab, user_path
            ) as test_server:
                self.open(test_server.get_start_url())
                self.click(SIGN_IN)
                self.assert_text(DISPLAY_NAME, SIGNED_IN_USER)
                _end_access_token(test_server)

            fake_gitlab.refresh_mode = REFRESH_INVALID_GRANT
            with self._create_server(
                test_setup, fake_gitlab, user_path
            ) as test_server:
                self.open(test_server.get_start_url())
                self._wait_for_element_after_reload(SIGN_IN_EXPIRED)

                self.assert_element(SIGN_IN)
                self.assert_element_not_visible(SIGNED_IN_USER)
                # The record is deleted.
                assert _read_record(test_server, is_required=False) is None

                # The user signs in again.
                self.click(SIGN_IN)
                self.assert_text(DISPLAY_NAME, SIGNED_IN_USER)
                assert _read_record(test_server) is not None

    def test_004_without_network_the_home_says_that_it_is_offline(
        self,
    ) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with _create_environment() as (fake_gitlab, user_path):
            with self._create_server(
                test_setup, fake_gitlab, user_path
            ) as test_server:
                self.open(test_server.get_start_url())
                self.click(SIGN_IN)
                self.assert_text(DISPLAY_NAME, SIGNED_IN_USER)
                old_record = _read_record(test_server)
                _end_access_token(test_server)

            fake_gitlab.stop()
            with self._create_server(
                test_setup, fake_gitlab, user_path
            ) as test_server:
                self.open(test_server.get_start_url())
                self._wait_for_element_after_reload(OFFLINE_NOTICE)

                # The user is named, and the tokens are kept.
                self.assert_text(DISPLAY_NAME, SIGNED_IN_USER)
                self.assert_text("You are offline", OFFLINE_NOTICE)
                self.assert_element_not_visible(SIGN_IN)
                record = _read_record(test_server)
                assert record["access_token"] == old_record["access_token"]
                assert record["refresh_token"] == old_record["refresh_token"]

    @staticmethod
    def _create_server(
        test_setup: End2EndTestSetup, fake_gitlab: FakeGitLab, user_path: str
    ) -> DesktopTestServer:
        return DesktopTestServer(
            input_path=test_setup.path_to_sandbox,
            fake_catalog_path=os.path.join(
                test_setup.path_to_sandbox, "catalog.json"
            ),
            gitlab_url=fake_gitlab.url,
            oauth_client_id=CLIENT_ID,
            user_path=user_path,
        )

    def _wait_until(self, condition: Callable[[], bool]) -> None:
        deadline = time.monotonic() + WAIT_SECONDS
        while not condition():
            assert time.monotonic() < deadline, "The wait ended."
            time.sleep(0.2)

    def _wait_for_element_after_reload(self, selector: str) -> None:
        """
        The home screen shows the state of the tokens when the page is made:
        load it again until the element is there.
        """
        deadline = time.monotonic() + WAIT_SECONDS
        while not self.is_element_visible(selector):
            assert time.monotonic() < deadline, f"{selector} did not appear."
            time.sleep(0.5)
            self.refresh_page()


@contextmanager
def _create_environment() -> Iterator[Tuple[FakeGitLab, str]]:
    """The fake GitLab and the user folder that two launches share."""
    with FakeGitLab() as fake_gitlab:
        with tempfile.TemporaryDirectory() as user_path:
            yield fake_gitlab, user_path


def _read_record(
    test_server: DesktopTestServer, *, is_required: bool = True
) -> Optional[Dict[str, Any]]:
    """The record of the tokens in the keyring file of the tests."""
    with open(test_server.get_keyring_path(), encoding="utf-8") as file_:
        secrets: Dict[str, str] = json.load(file_)
    records = [
        json.loads(value_)
        for key_, value_ in secrets.items()
        if key_.split("\n")[1].startswith("gitlab/")
    ]
    if len(records) == 0:
        assert not is_required, "There is no record of tokens."
        return None
    assert len(records) == 1
    record: Dict[str, Any] = records[0]
    return record


def _end_access_token(test_server: DesktopTestServer) -> None:
    """
    Make the access token of the record end, as if the application had not run
    for hours: the next launch has to renew it.
    """
    with open(test_server.get_keyring_path(), encoding="utf-8") as file_:
        secrets: Dict[str, str] = json.load(file_)
    for key_, value_ in secrets.items():
        if key_.split("\n")[1].startswith("gitlab/"):
            record = json.loads(value_)
            record["expires_at"] = time.time() - 60
            secrets[key_] = json.dumps(record)
    with open(test_server.get_keyring_path(), "w", encoding="utf-8") as file_:
        json.dump(secrets, file_)
