"""
@relation(SDOC-SRS-1220, scope=file)
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
        input_path: str,
        no_window: bool,
        port: Optional[int],
    ):
        self.debug: bool = debug
        self.development: bool = development
        self.command: str = command
        self.input_path: str = input_path
        self.no_window: bool = no_window
        self.port: Optional[int] = port

    def get_full_input_path(self) -> str:
        return os.path.abspath(self.input_path)

    def validate(self) -> None:
        if not os.path.exists(self.input_path):
            raise CLIValidationError(
                f"Provided input path does not exist: {self.input_path}"
            )
