"""
The GitLab client of the desktop application.

The client carries the access token of the signed-in user, so GitLab answers
with the rights of that user. It checks the certificate of GitLab against the
certificates of the operating system: a GitLab behind the certificate
authority of a company is then reached with no setting.

@relation(SDOC-SRS-1240, scope=file)
"""

import os
import ssl
from typing import Any, Optional, Union
from urllib.parse import urlsplit

import gitlab

from strictdoc.features.desktop.settings import DesktopSettings
from strictdoc.features.desktop.token_store import TokenKeeper
from strictdoc.features.project_catalog.registry import GITLAB_PROVIDER_NAME

REQUEST_TIMEOUT_SECONDS = 20


def get_system_ca_bundle() -> Union[str, bool]:
    """
    The file or the folder of the certificates of the system, which the SSL
    library knows (the variable SSL_CERT_FILE changes them). True when there is
    none, which keeps the check with the certificates that python-gitlab
    brings. The check is never off.
    """
    paths = ssl.get_default_verify_paths()
    for candidate_ in (paths.cafile, paths.openssl_cafile):
        if candidate_ is not None and os.path.isfile(candidate_):
            return candidate_
    for candidate_ in (paths.capath, paths.openssl_capath):
        if candidate_ is not None and os.path.isdir(candidate_):
            return candidate_
    return True


def create_gitlab_client(gitlab_url: str, access_token: str) -> Any:
    return gitlab.Gitlab(
        gitlab_url.strip().rstrip("/"),
        oauth_token=access_token,
        ssl_verify=get_system_ca_bundle(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


def create_catalog_client(
    settings: DesktopSettings, keeper: TokenKeeper
) -> Optional[Any]:
    """
    The client that the catalog of the settings uses: a GitLab client with the
    token of the signed-in user, once the user is signed in. The client goes to
    the GitLab that gave the token (the one of the session), and to no other:
    when the settings name another GitLab, there is no client and the user has
    to sign in again. None also when the catalog is not the one of GitLab, or
    when nobody is signed in.
    """
    if settings.catalog_provider != GITLAB_PROVIDER_NAME:
        return None
    session_url = keeper.gitlab_url
    if len(session_url) == 0 or not is_same_gitlab(
        session_url, settings.gitlab_url
    ):
        return None
    access_token = keeper.get_access_token()
    if access_token is None:
        return None
    return create_gitlab_client(session_url, access_token)


def is_same_gitlab(first_url: str, second_url: str) -> bool:
    """Tell whether two addresses name the same GitLab (scheme, host, port)."""
    return _get_origin(first_url) == _get_origin(second_url)


def _get_origin(url: str) -> str:
    parts = urlsplit(url.strip())
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"
