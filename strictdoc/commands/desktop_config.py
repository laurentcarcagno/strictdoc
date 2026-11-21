"""
@relation(SDOC-SRS-1220, scope=file)
@relation(SDOC-SRS-1229, scope=file)
"""

import os
from typing import Optional

from strictdoc.cli.base_command import CLIValidationError
from strictdoc.helpers.auto_described import auto_described


@auto_described
class DesktopCommandConfig:
    def __init__(
        self,
        *,
        debug: bool,
        development: bool = False,
        command: str,
        input_path: Optional[str],
        no_window: bool,
        port: Optional[int],
    ):
        self.debug: bool = debug
        self.development: bool = development
        self.command: str = command
        # Without a path, the application opens its home screen.
        self.input_path: Optional[str] = input_path
        self.no_window: bool = no_window
        self.port: Optional[int] = port

    def get_full_input_path(self) -> str:
        assert self.input_path is not None, "The command has no input path."
        return os.path.abspath(self.input_path)

    def validate(self) -> None:
        if self.input_path is None:
            return
        if not os.path.exists(self.input_path):
            raise CLIValidationError(
                f"Provided input path does not exist: {self.input_path}"
            )
