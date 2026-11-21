"""
The window of the desktop application.

@relation(SDOC-SRS-1220, scope=file)
"""

import importlib
from pathlib import Path
from typing import Any

WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 800


class DesktopWindowError(Exception):
    pass


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
    webview = _import_webview()
    storage_path.mkdir(parents=True, exist_ok=True)
    window = webview.create_window(
        title, url, width=WINDOW_WIDTH, height=WINDOW_HEIGHT
    )

    def keep_own_links_in_window() -> None:
        window.evaluate_js(_KEEP_OWN_LINKS_IN_WINDOW_SCRIPT)

    window.events.loaded += keep_own_links_in_window
    webview.start(gui="qt", private_mode=False, storage_path=str(storage_path))


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
