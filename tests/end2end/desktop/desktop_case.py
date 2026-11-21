"""
The base class of the end2end tests of the desktop application.

@relation(SDOC-SRS-1229, scope=file)
"""

from tests.end2end.e2e_case import E2ECase

# The size of the window of the application: the screens of the project show
# their tree of documents on a window of this size.
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 800


class DesktopCase(E2ECase):
    """
    A test of the desktop application starts with a window of the size of the
    application.

    The end2end tests share one browser (--reuse-session), and some tests of
    other features narrow the window and leave it so. On a narrow window, the
    project screen hides its tree of documents, and a test that looks for a
    document in the tree fails depending on the tests that ran before it.
    """

    def setUp(self, masterqa_mode: bool = False) -> None:
        super().setUp(masterqa_mode=masterqa_mode)
        self.set_window_size(WINDOW_WIDTH, WINDOW_HEIGHT)
