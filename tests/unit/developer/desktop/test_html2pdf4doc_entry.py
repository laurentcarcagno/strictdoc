"""
@relation(SDOC-SRS-1258, scope=file)
"""

from typing import Any

from developer.desktop import html2pdf4doc_entry


class _FakePopen:
    def __init__(self, *_: Any, **kwargs: Any) -> None:
        self.kwargs = kwargs


def test_every_program_that_is_started_gets_no_window_flag() -> None:
    html2pdf4doc_entry.hide_subprocess_windows(_FakePopen)

    plain = _FakePopen(["chromedriver"])
    flagged = _FakePopen(["chromedriver"], creationflags=0x200)

    no_window = html2pdf4doc_entry.CREATE_NO_WINDOW
    assert plain.kwargs["creationflags"] == no_window
    assert flagged.kwargs["creationflags"] == 0x200 | no_window
