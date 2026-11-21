"""
The window of the desktop application.

@relation(SDOC-SRS-1220, scope=file)
@relation(SDOC-SRS-1230, scope=file)
@relation(SDOC-SRS-1232, scope=file)
"""

import importlib
from pathlib import Path
from typing import Any, List, Optional

from strictdoc.features.i18n.i18n import gettext

WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 800


class DesktopWindowError(Exception):
    pass


# The window of this process, while run_window() shows it. None when the
# application runs without a window (--no-window).
_window: Optional[Any] = None

# The address of the home screen, when the application has one. The menu of the
# window brings the user back to it.
_home_url: Optional[str] = None


# The pages of the server open some links in a new window (target="_blank",
# and the tree map clicks a link that it creates). pywebview sends every such
# link to the browser of the system, which has no session cookie: the server
# answers 403. This script keeps the links to the server itself in the window
# and leaves the other links to pywebview, which opens them in the browser of
# the system.
#
# - A click on a link to the same origin that would open a new window (the
#   target "_blank", or Ctrl, Shift, Meta or the middle button) loads the link
#   in the window.
# - A link that a script creates and clicks without adding it to the page does
#   not reach the listener of the document. Its click() method is wrapped.
_KEEP_OWN_LINKS_IN_WINDOW_SCRIPT = """
(function () {
  if (window.__strictdocDesktopLinks === true) {
    return;
  }
  window.__strictdocDesktopLinks = true;

  function isOwnLink(anchor) {
    return anchor.origin === window.location.origin;
  }

  function onClick(event) {
    const target = event.target;
    const anchor = target.closest ? target.closest("a[href]") : null;
    if (anchor === null || !isOwnLink(anchor)) {
      return;
    }
    const opensNewWindow = (
      anchor.target === "_blank" ||
      event.ctrlKey || event.shiftKey || event.metaKey ||
      event.button === 1
    );
    if (!opensNewWindow) {
      return;
    }
    event.preventDefault();
    window.location.href = anchor.href;
  }
  document.addEventListener("click", onClick, true);
  document.addEventListener("auxclick", onClick, true);

  const originalClick = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    if (this.target === "_blank" && isOwnLink(this)) {
      this.target = "_self";
    }
    return originalClick.call(this);
  };
})();
"""


def check_window_available() -> None:
    """Raise DesktopWindowError if the window cannot be shown."""
    _import_webview()


def run_window(*, title: str, url: str, storage_path: Path) -> None:
    """
    Show the URL in a window and return when the user closes the window.

    The window keeps its browser profile in the storage folder, so that the
    settings of the pages survive between two runs.
    """
    global _window  # noqa: PLW0603
    webview = _import_webview()
    storage_path.mkdir(parents=True, exist_ok=True)
    window = webview.create_window(
        title, url, width=WINDOW_WIDTH, height=WINDOW_HEIGHT
    )
    _window = window

    def keep_own_links_in_window() -> None:
        window.evaluate_js(_KEEP_OWN_LINKS_IN_WINDOW_SCRIPT)

    window.events.loaded += keep_own_links_in_window
    try:
        webview.start(
            gui="qt",
            private_mode=False,
            storage_path=str(storage_path),
            menu=_create_menu(),
        )
    finally:
        _window = None


def set_home_url(url: Optional[str]) -> None:
    """
    Tell the window where the home screen is. The window then has the menu
    "Projects > Switch project", which goes back to it. The home screen has
    the session cookie of its server already: the window opens it directly.
    """
    global _home_url  # noqa: PLW0603
    _home_url = url


def go_to_home() -> None:
    """Show the home screen in the window. A thread of the menu calls it."""
    if _window is not None and _home_url is not None:
        _window.load_url(_home_url)


def is_window_open() -> bool:
    """Tell whether this process shows its window, so that it has dialogs."""
    return _window is not None


def choose_folder(initial_folder: str) -> Optional[str]:
    """
    Ask the user for a folder in the dialog of the system, and return it. None
    when the user cancels the dialog.

    Call it from a thread that is not the one of the window: with Qt, the call
    runs the dialog in the thread of the window and waits for its answer, so
    the web server calls it from the thread of a request.
    """
    if _window is None:
        raise DesktopWindowError("There is no window to show a dialog.")
    webview = _import_webview()
    file_dialog = getattr(webview, "FileDialog", None)
    dialog_type = (
        file_dialog.FOLDER if file_dialog is not None else webview.FOLDER_DIALOG
    )
    chosen = _window.create_file_dialog(dialog_type, directory=initial_folder)
    if chosen is None or len(chosen) == 0:
        return None
    folder: str = chosen[0]
    return folder


def _create_menu() -> List[Any]:
    if _home_url is None:
        return []
    menu_module = importlib.import_module("webview.menu")
    return [
        menu_module.Menu(
            gettext("Projects"),
            [menu_module.MenuAction(gettext("Switch project"), go_to_home)],
        )
    ]


def _import_webview() -> Any:
    # The module is imported here and not at the top: the other commands and
    # --no-window do not need pywebview, and it is in an optional group.
    try:
        return importlib.import_module("webview")
    except ImportError as exception_:
        raise DesktopWindowError(
            "The desktop window needs the 'pywebview' package with Qt. "
            "Install it with: pip install 'pywebview[qt]'. "
            "To run the server without a window, use --no-window."
        ) from exception_
