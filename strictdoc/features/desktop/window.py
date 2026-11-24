"""
The window of the desktop application.

@relation(SDOC-SRS-1220, scope=file)
@relation(SDOC-SRS-1230, scope=file)
@relation(SDOC-SRS-1232, scope=file)
"""

import importlib
import importlib.util
import sys
import threading
from pathlib import Path
from typing import Any, Callable, List, Optional

from strictdoc.features.i18n.i18n import gettext

WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 800
# How long a request waits for the thread of the window to do something.
GUI_THREAD_TIMEOUT_SECONDS = 10.0

# The Python module that each engine of pywebview needs: qtpy for Qt, and
# clr (pythonnet) for WebView2.
_ENGINE_REQUIREMENTS = {"qt": "qtpy", "edgechromium": "clr"}


class DesktopWindowError(Exception):
    pass


# The window of this process, while run_window() shows it. None when the
# application runs without a window (--no-window).
_window: Optional[Any] = None

# The function that runs a job in the thread of the window, with Qt. None with
# the other engines, whose pywebview does it by itself.
_post_to_gui_thread: Optional[Callable[[Callable[[], None]], None]] = None

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


def get_window_engine(platform: str) -> str:
    """
    The engine of the window: WebView2 on Windows, Qt WebEngine elsewhere.

    The engine is the "gui" argument of pywebview.
    """
    return "edgechromium" if platform == "win32" else "qt"


def check_window_available() -> None:
    """Raise DesktopWindowError if the window cannot be shown."""
    engine = get_window_engine(sys.platform)
    _import_webview(engine)


def run_window(*, title: str, url: str, storage_path: Path) -> None:
    """
    Show the URL in a window and return when the user closes the window.

    The window keeps its browser profile in the storage folder, so that the
    settings of the pages survive between two runs.
    """
    global _window, _post_to_gui_thread  # noqa: PLW0603
    engine = get_window_engine(sys.platform)
    webview = _import_webview(engine)
    storage_path.mkdir(parents=True, exist_ok=True)
    if engine == "qt":
        # This is the thread of the window: the jobs of the other threads come
        # back here, to the loop of Qt that webview.start() runs.
        _post_to_gui_thread = create_qt_poster()
    window = webview.create_window(
        title, url, width=WINDOW_WIDTH, height=WINDOW_HEIGHT
    )
    _window = window

    def keep_own_links_in_window() -> None:
        window.evaluate_js(_KEEP_OWN_LINKS_IN_WINDOW_SCRIPT)

    window.events.loaded += keep_own_links_in_window
    try:
        webview.start(
            gui=engine,
            private_mode=False,
            storage_path=str(storage_path),
            menu=_create_menu(),
        )
    finally:
        _window = None
        _post_to_gui_thread = None


def create_qt_poster() -> Callable[[Callable[[], None]], None]:
    """
    A function that runs a job in the thread that calls this one, which is the
    main thread of the application and the one of the loop of Qt. Qt objects,
    the cookie store of the window included, may be used from this thread
    only: the store crashes the process when another thread calls it.
    """
    qt_core = importlib.import_module("qtpy.QtCore")

    class Poster(qt_core.QObject):  # type: ignore[misc, name-defined]
        requested = qt_core.Signal(object)

        def __init__(self) -> None:
            super().__init__()
            self.requested.connect(self.run)

        def run(self, job: Callable[[], None]) -> None:
            job()

    poster = Poster()

    def post(job: Callable[[], None]) -> None:
        poster.requested.emit(job)

    return post


def run_on_gui_thread(
    function: Callable[[], None],
    *,
    timeout_seconds: float = GUI_THREAD_TIMEOUT_SECONDS,
) -> bool:
    """
    Run the function in the thread of the window, and wait until it is done.
    It returns False when the thread of the window did not do it in time. An
    exception of the function is raised here. Without a Qt poster (another
    engine, whose pywebview moves the call itself), or when this is the thread
    of the window, the function runs here.
    """
    post = _post_to_gui_thread
    if post is None or threading.current_thread() is threading.main_thread():
        function()
        return True
    done = threading.Event()
    errors: List[BaseException] = []

    def job() -> None:
        try:
            function()
        except BaseException as exception_:  # noqa: BLE001
            errors.append(exception_)
        finally:
            done.set()

    post(job)
    if not done.wait(timeout_seconds):
        return False
    if len(errors) > 0:
        raise errors[0]
    return True


def set_home_url(url: Optional[str]) -> None:
    """
    Tell the window where the home screen is. The window then has the menu
    "Projects > Switch project", which goes back to it, and "Projects >
    Settings", which shows the screen of the settings. The home screen has
    the session cookie of its server already: the window opens it directly.
    """
    global _home_url  # noqa: PLW0603
    _home_url = url


def go_to_home() -> None:
    """Show the home screen in the window. A thread of the menu calls it."""
    if _window is not None and _home_url is not None:
        _window.load_url(_home_url)


def go_to_settings() -> None:
    """Show the screen of the settings in the window."""
    if _window is not None and _home_url is not None:
        _window.load_url(f"{_home_url.rstrip('/')}/settings")


def clear_window_cookies() -> bool:
    """
    Forget every cookie of the window: the ones of GitLab and of the sign-in
    service, so that the next sign-in asks for the user again, and the session
    cookies of the servers of the application. It returns True when a window
    was cleared, and False when there is none (the application runs with
    --no-window, or in a test) or when its thread did not answer in time.

    @relation(SDOC-SRS-1234, scope=function)
    """
    window = _window
    if window is None:
        return False
    # The cookie store is used in the thread of the window, and the call waits
    # until it is done: what the window loads next, with a new session cookie,
    # does not come before the end of the clearing.
    return run_on_gui_thread(window.clear_cookies)


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
    webview = _import_webview(get_window_engine(sys.platform))
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
            [
                menu_module.MenuAction(gettext("Switch project"), go_to_home),
                menu_module.MenuAction(gettext("Settings"), go_to_settings),
            ],
        )
    ]


def _import_webview(engine: str) -> Any:
    # The module is imported here and not at the top: the other commands and
    # --no-window do not need pywebview, and it is in an optional group.
    try:
        webview = importlib.import_module("webview")
        # The module that the engine needs, found without importing it: the
        # import of Qt or .NET has side effects.
        if importlib.util.find_spec(_ENGINE_REQUIREMENTS[engine]) is None:
            raise ImportError(_ENGINE_REQUIREMENTS[engine])
        return webview
    except ImportError as exception_:
        if engine == "edgechromium":
            hint = "pip install pywebview (it needs WebView2)"
            name = "WebView2"
        else:
            hint = "pip install 'pywebview[qt]'"
            name = "Qt"
        raise DesktopWindowError(
            f"The desktop window needs the 'pywebview' package with {name}. "
            f"Install it with: {hint}. "
            "To run the server without a window, use --no-window."
        ) from exception_
