"""
@relation(SDOC-SRS-1234, scope=file)
"""

import os
import sys
from urllib.parse import urlsplit

import pytest

from tests.end2end.desktop.desktop_case import DesktopCase
from tests.end2end.desktop.desktop_test_server import DesktopTestServer
from tests.end2end.desktop.fake_gitlab import (
    CLIENT_ID,
    DISPLAY_NAME,
    MODE_DENY,
    USERNAME,
    FakeGitLab,
)
from tests.end2end.end2end_test_setup import End2EndTestSetup

SIGN_IN = '[data-testid="sign-in"]'
SIGNED_IN_USER = '[data-testid="signed-in-user"]'
SIGNED_IN_USERNAME = '[data-testid="signed-in-username"]'
MESSAGE = '[data-testid="message-text"]'
BACK_TO_CATALOG = '[data-testid="back-to-catalog"]'
CATALOG = '[data-testid="catalog"]'


@pytest.mark.skipif(
    sys.platform == "win32", reason="The user folders follow XDG variables."
)
class Test(DesktopCase):
    """
    The sign-in to GitLab from the home screen, with a fake GitLab that
    answers like the real one. The fake GitLab is at "localhost" and the home
    server at 127.0.0.1: for the browser they are two sites, so the callback
    reaches the home server without its SameSite=Strict cookie, as it does
    with the real GitLab.
    """

    def test_001_sign_in_shows_the_name_of_the_user(self) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with FakeGitLab() as fake_gitlab, DesktopTestServer(
            input_path=test_setup.path_to_sandbox,
            fake_catalog_path=os.path.join(
                test_setup.path_to_sandbox, "catalog.json"
            ),
            gitlab_url=fake_gitlab.url,
            oauth_client_id=CLIENT_ID,
        ) as test_server:
            self.open(test_server.get_start_url())

            self.assert_element(SIGN_IN)
            self.assert_element_not_visible(SIGNED_IN_USER)
            self.click(SIGN_IN)

            # The window went to the fake GitLab, which called the home
            # server back, which went to the home screen.
            self.assert_text(DISPLAY_NAME, SIGNED_IN_USER)
            self.assert_text(USERNAME, SIGNED_IN_USERNAME)
            self.assert_element_not_visible(SIGN_IN)
            self.assert_element(CATALOG)
            # The address of the callback, with the code, is not kept.
            current_path = urlsplit(self.get_current_url()).path
            assert current_path == "/"
            assert "code=" not in self.get_current_url()
            (token_request,) = fake_gitlab.token_requests
            assert token_request["grant_type"] == "authorization_code"
            assert len(token_request["code_verifier"]) >= 43

    def test_002_a_refusal_shows_a_message_and_the_way_back(self) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with FakeGitLab() as fake_gitlab, DesktopTestServer(
            input_path=test_setup.path_to_sandbox,
            fake_catalog_path=os.path.join(
                test_setup.path_to_sandbox, "catalog.json"
            ),
            gitlab_url=fake_gitlab.url,
            oauth_client_id=CLIENT_ID,
        ) as test_server:
            fake_gitlab.mode = MODE_DENY
            self.open(test_server.get_start_url())

            self.click(SIGN_IN)

            self.assert_text("The server refused the sign-in", MESSAGE)
            self.assert_text("access_denied", MESSAGE)
            self.click(BACK_TO_CATALOG)
            self.assert_element(SIGN_IN)
            self.assert_element_not_visible(SIGNED_IN_USER)
            assert fake_gitlab.token_requests == []

    def test_003_the_texts_follow_the_language(self) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with FakeGitLab() as fake_gitlab, DesktopTestServer(
            input_path=test_setup.path_to_sandbox,
            fake_catalog_path=os.path.join(
                test_setup.path_to_sandbox, "catalog.json"
            ),
            gitlab_url=fake_gitlab.url,
            oauth_client_id=CLIENT_ID,
            language="fr",
        ) as test_server:
            self.open(test_server.get_start_url())

            self.assert_text("Se connecter", SIGN_IN)
            self.click(SIGN_IN)

            self.assert_text(
                "Connecté en tant que " + DISPLAY_NAME, SIGNED_IN_USER
            )

    def test_004_without_gitlab_in_the_settings_there_is_no_sign_in(
        self,
    ) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with DesktopTestServer(
            input_path=test_setup.path_to_sandbox,
            fake_catalog_path=os.path.join(
                test_setup.path_to_sandbox, "catalog.json"
            ),
        ) as test_server:
            self.open(test_server.get_start_url())

            self.assert_element(CATALOG)
            self.assert_element_not_visible(SIGN_IN)
