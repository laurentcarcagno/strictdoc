import os
from typing import Optional

from strictdoc.cli.base_command import CLIValidationError
from strictdoc.helpers.auto_described import auto_described
from strictdoc.helpers.net import is_valid_host


@auto_described
class ServerCommandConfig:
    def __init__(
        self,
        *,
        debug: bool,
        development: bool = False,
        command: str,
        input_path: Optional[str] = None,
        output_path: Optional[str],
        config: Optional[str],
        reload: bool,
        host: Optional[str],
        port: Optional[int],
        watch: bool = False,
        projects: Optional[str] = None,
        root_host: Optional[str] = None,
        data_root: Optional[str] = None,
    ):
        self.debug: bool = debug
        self.development: bool = development
        self.command: str = command
        self._input_path: Optional[str] = input_path
        self.output_path: Optional[str] = output_path
        self._config_path: Optional[str] = config
        self.reload: bool = reload
        self.host: Optional[str] = host
        self.port: Optional[int] = port
        self.watch: bool = watch
        # A server with several projects (features/projects): the registry
        # file, the host name of the portal and the folder that the projects
        # must be inside.
        self.projects: Optional[str] = projects
        self.root_host: Optional[str] = root_host
        self.data_root: Optional[str] = data_root

    def get_full_input_path(self) -> str:
        assert self._input_path is not None
        return os.path.abspath(self._input_path)

    def get_path_to_config(self) -> str:
        if self._config_path is not None:
            return self._config_path
        assert self._input_path is not None
        return self._input_path

    def validate(self) -> None:
        if self.projects is not None:
            if self._input_path is not None:
                raise CLIValidationError(
                    "Give either an input path or --projects, not both."
                )
            if not os.path.isfile(self.projects):
                raise CLIValidationError(
                    f"Provided project registry does not exist: {self.projects}"
                )
            if self.root_host is None:
                raise CLIValidationError(
                    "--projects needs --root-host, the host name of the "
                    "portal (projects are served at <slug>.<root host>)."
                )
            if self.data_root is not None and not os.path.isdir(self.data_root):
                raise CLIValidationError(
                    f"Provided data root does not exist: {self.data_root}"
                )
            return
        if self._input_path is None:
            raise CLIValidationError("Provide an input path or --projects.")
        if not os.path.exists(self._input_path):
            raise CLIValidationError(
                f"Provided input path does not exist: {self._input_path}"
            )

        if self._config_path is not None and not os.path.exists(
            self._config_path
        ):
            raise CLIValidationError(
                "Provided path to a configuration file does not exist: "
                f"{self._config_path}"
            )

        if (host_ := self.host) is not None:
            if not is_valid_host(host_):
                raise CLIValidationError(
                    f"Provided 'host' argument is not a valid host: {host_}"
                )
