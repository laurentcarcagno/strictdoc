"""Two projects behind one dispatcher."""

from pathlib import Path
from typing import Dict, List, Tuple

from fastapi.testclient import TestClient

from strictdoc.features.projects.app import create_projects_app
from strictdoc.features.projects.dispatcher import (
    PROJECT_COOKIE,
    ProjectDispatcher,
)
from strictdoc.features.projects.registry import ProjectSpec
from strictdoc.server.app import create_app

ROOT = "strictdoc.test"
PROXY = ("10.89.2.7", 40000)


def roles(prefix: str) -> Dict[str, List[str]]:
    return {
        "administrator": [f"{prefix}-admins"],
        "author": [f"{prefix}-authors"],
        "reviewer": [f"{prefix}-reviewers"],
        "reader": [f"{prefix}-readers"],
    }


def as_user(*groups: str, user: str = "u") -> Dict[str, str]:
    return {
        "X-Forwarded-Preferred-Username": user,
        "X-Forwarded-User": f"id-{user}",
        "X-Forwarded-Groups": ",".join(groups),
    }


def project_document(
    title: str, mid: str, requirement_mid: str, uid: str
) -> str:
    return (
        f"[DOCUMENT]\nMID: {mid}\nTITLE: {title}\nOPTIONS:\n  ENABLE_MID: True\n\n"
        f"[REQUIREMENT]\nMID: {requirement_mid}\nUID: {uid}\nTITLE: {uid}\n"
        f"STATEMENT: >>>\nThe {title} shall work.\n<<<\n"
    )


ALPHA_DOC = "a" * 32
ALPHA_REQ = "a1" * 16
BETA_DOC = "b" * 32
BETA_REQ = "b1" * 16


def make_specs(root: Path) -> List[ProjectSpec]:
    alpha = root / "data" / "alpha"
    beta = root / "data" / "beta"
    alpha.mkdir(parents=True)
    beta.mkdir(parents=True)
    (alpha / "alpha_doc.sdoc").write_text(
        project_document("Alpha spec", ALPHA_DOC, ALPHA_REQ, "ALPHA-1"),
        encoding="utf8",
    )
    (beta / "beta_doc.sdoc").write_text(
        project_document("Beta spec", BETA_DOC, BETA_REQ, "BETA-1"),
        encoding="utf8",
    )
    return [
        ProjectSpec(
            slug="alpha",
            title="Alpha program",
            path=str(alpha),
            roles=roles("alpha"),
        ),
        ProjectSpec(
            slug="beta",
            title="Beta program",
            path=str(beta),
            roles=roles("beta"),
        ),
    ]


def make_dispatcher(
    root: Path,
    monkeypatch=None,
    proxy: bool = True,
    platform_admins=None,
    comments: bool = False,
    features=None,
) -> ProjectDispatcher:
    if monkeypatch is not None:
        if proxy:
            monkeypatch.setenv("STRICTDOC_AUTH_MODE", "proxy")
            monkeypatch.setenv("STRICTDOC_TRUSTED_PROXIES", "10.89.2.0/24")
        else:
            monkeypatch.delenv("STRICTDOC_AUTH_MODE", raising=False)
    specs = make_specs(root)
    if comments:
        features = ["COMMENTS"]
    if features:
        listed = ", ".join(f'"{feature_}"' for feature_ in features)
        for spec_ in specs:
            (Path(spec_.path) / "strictdoc.toml").write_text(
                f"[project]\nfeatures = [{listed}]\n", encoding="utf8"
            )
    return create_projects_app(
        create_app=create_app,
        platform_admin_groups=platform_admins,
        specs=specs,
        root_host=ROOT,
        output_root=str(root / "output"),
        audit_root=str(root / "audit"),
        data_root=str(root / "data"),
    )


def client_for(
    dispatcher: ProjectDispatcher, host: str, proxy: bool = True
) -> TestClient:
    """
    A client of the server. "<slug>.<ROOT>" names a project: the client is on
    the one address of the server with that project as the current one (the
    cookie of the dispatcher). Any other host is used as it is.
    """
    suffix = "." + ROOT
    slug = host[: -len(suffix)] if host.endswith(suffix) else None
    client = TestClient(
        dispatcher,
        base_url=f"http://{ROOT if slug else host}",
        client=PROXY if proxy else ("127.0.0.1", 40000),
        raise_server_exceptions=False,
    )
    if slug:
        client.cookies.set(PROJECT_COOKIE, slug)
    return client


def clients(
    dispatcher: ProjectDispatcher, proxy: bool = True
) -> Tuple[TestClient, TestClient, TestClient]:
    return (
        client_for(dispatcher, ROOT, proxy),
        client_for(dispatcher, f"alpha.{ROOT}", proxy),
        client_for(dispatcher, f"beta.{ROOT}", proxy),
    )
