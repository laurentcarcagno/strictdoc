"""The errors of the stub keyring of the end2end tests."""


class KeyringError(Exception):
    pass


class PasswordDeleteError(KeyringError):
    pass
