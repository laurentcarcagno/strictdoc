"""
The server of the home screen.

@relation(SDOC-SRS-1220, scope=file)
@relation(SDOC-SRS-1229, scope=file)
@relation(SDOC-SRS-1232, scope=file)
"""

from typing import Optional

from strictdoc.features.desktop import window
from strictdoc.features.desktop.home_app import create_home_app
from strictdoc.features.desktop.local_server import LocalServer


class HomeServer(LocalServer):
    """
    The server of the home screen. It tells the window where the home screen
    is, so that the menu of the window can bring the user back to it.
    """

    def start(self) -> None:
        super().start()
        window.set_home_url(self.direct_url)


def create_home_server(*, port: Optional[int] = None) -> LocalServer:
    """
    A server on the loopback address with its own free port, with the same
    session token as the server of a project.
    """
    return HomeServer(application_factory=create_home_app, port=port)
