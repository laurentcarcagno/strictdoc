"""
A stand-in for the "keyring" package, for the end2end tests of the desktop
application.

The application runs in a process of its own and must not touch the keyring of
the person who runs the tests. The test server puts the folder of this stub
first in PYTHONPATH, so that "import keyring" finds it, with or without the
real package installed. The secrets are in a JSON file of the temporary user
folder, which the test can read and change.

@relation(SDOC-SRS-1235, scope=file)
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional

from keyring.errors import PasswordDeleteError
from strictdoc.helpers.file_system import file_open_read_utf8

KEYRING_FILE_VARIABLE = "STRICTDOC_TEST_KEYRING_FILE"


def get_password(service_name: str, username: str) -> Optional[str]:
    return _read().get(_get_key(service_name, username))


def set_password(service_name: str, username: str, password: str) -> None:
    secrets = _read()
    secrets[_get_key(service_name, username)] = password
    _write(secrets)


def delete_password(service_name: str, username: str) -> None:
    secrets = _read()
    key = _get_key(service_name, username)
    if key not in secrets:
        raise PasswordDeleteError("No such secret.")
    del secrets[key]
    _write(secrets)


def _get_key(service_name: str, username: str) -> str:
    return f"{service_name}\n{username}"


def _read() -> Dict[str, str]:
    path = os.environ[KEYRING_FILE_VARIABLE]
    if not os.path.isfile(path):
        return {}
    with file_open_read_utf8(path) as file_:
        secrets: Dict[str, str] = json.load(file_)
    return secrets


def _write(secrets: Dict[str, str]) -> None:
    Path(os.environ[KEYRING_FILE_VARIABLE]).write_text(
        json.dumps(secrets), encoding="utf-8"
    )
