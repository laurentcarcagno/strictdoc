"""
The place of the secrets of the desktop application.

An access token or an API key goes through a SecretStore and never into the
settings file.

@relation(SDOC-SRS-1224, scope=file)
"""

import importlib
from typing import Dict, Optional, Protocol

KEYRING_SERVICE_NAME = "strictdoc-desktop"


class SecretStoreError(Exception):
    """A secret cannot be saved or deleted."""


class SecretStore(Protocol):
    def get(self, name: str) -> Optional[str]:
        """The secret, or None when there is none."""
        ...

    def set(self, name: str, value: str) -> None: ...

    def delete(self, name: str) -> None:
        """Delete the secret. A secret that does not exist is not an error."""
        ...


class KeyringSecretStore:
    """
    The keyring of the operating system.

    A keyring that fails (none installed, locked, refusing) does not stop the
    application: reading answers that there is no secret, and writing raises
    a SecretStoreError that the caller shows to the user.
    """

    def __init__(self, service_name: str = KEYRING_SERVICE_NAME) -> None:
        self._service_name: str = service_name

    def get(self, name: str) -> Optional[str]:
        keyring = importlib.import_module("keyring")
        keyring_errors = importlib.import_module("keyring.errors")
        try:
            secret: Optional[str] = keyring.get_password(
                self._service_name, name
            )
        except keyring_errors.KeyringError:
            return None
        return secret

    def set(self, name: str, value: str) -> None:
        keyring = importlib.import_module("keyring")
        keyring_errors = importlib.import_module("keyring.errors")
        try:
            keyring.set_password(self._service_name, name, value)
        except keyring_errors.KeyringError as exception_:
            raise SecretStoreError(
                f"The system keyring refused to save the secret '{name}': "
                f"{exception_}"
            ) from exception_

    def delete(self, name: str) -> None:
        keyring = importlib.import_module("keyring")
        keyring_errors = importlib.import_module("keyring.errors")
        try:
            keyring.delete_password(self._service_name, name)
        except keyring_errors.PasswordDeleteError:
            # There was no such secret.
            pass
        except keyring_errors.KeyringError as exception_:
            raise SecretStoreError(
                f"The system keyring refused to delete the secret '{name}': "
                f"{exception_}"
            ) from exception_


class MemorySecretStore:
    """Secrets kept in memory, for the tests."""

    def __init__(self) -> None:
        self._secrets: Dict[str, str] = {}

    def get(self, name: str) -> Optional[str]:
        return self._secrets.get(name)

    def set(self, name: str, value: str) -> None:
        self._secrets[name] = value

    def delete(self, name: str) -> None:
        self._secrets.pop(name, None)
