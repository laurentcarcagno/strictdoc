"""
The AI servers of the desktop application: what the user may declare in the
screen of the settings, what the application keeps of it, and the
configuration of the assistant that follows from it.

A server has a name, a protocol (the chat completions of OpenAI, which Ollama,
vLLM, STRATA and Mistral speak, or Anthropic), an address, a model, a key and
the answer to "does the data stay in the company". The key is in the keyring
(SecretStore), never in the settings file and never in the environment of the
process; the screen never shows it again. When the address changes, the key is
erased: it would go to the new address otherwise.

Anthropic, and Mistral (known by its host), are always external. An external
server needs an https address and a key. An internal server needs an address;
its key is optional, and an http address is fine in the network of the company.

The AiRuntime turns the settings into the LLMConfig of each project that is
open: a server that is complete becomes a provider, the default one is the
first internal server, and external servers exist only while the policy of the
company (ai_policy.py) is valid. The LLMConfig of a project is made before its
server starts and then changed in place: the routes of the assistant read it at
every call, so a change of the settings needs no restart. Without any provider,
the feature of the assistant is off for the project and no AI button shows.

@relation(SDOC-SRS-1253, scope=file)
@relation(SDOC-SRS-1254, scope=file)
@relation(SDOC-SRS-1255, scope=file)
"""

import json
import re
import threading
import urllib.error
import urllib.request
import weakref
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence
from urllib.parse import urlsplit

from strictdoc.core.project_config import ProjectConfig, ProjectFeature
from strictdoc.features.desktop.ai_policy import (
    AiPolicy,
    get_policy_message,
    load_ai_policy,
)
from strictdoc.features.desktop.secret_store import SecretStore
from strictdoc.features.desktop.settings import (
    AI_KIND_ANTHROPIC,
    AI_KIND_OPENAI,
    AI_KINDS,
    AiServer,
    DesktopSettings,
    get_ai_secret_name,
    is_ai_server_complete,
    is_ai_server_internal,
    is_mistral_url,
    load_settings,
)
from strictdoc.features.i18n.i18n import gettext
from strictdoc.features.llm.config import (
    Anthropic,
    LLMConfig,
    OpenAICompatible,
    ProviderConfig,
)

ANTHROPIC_URL = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"
KEY_VARIABLE_PREFIX = "STRICTDOC_AI_KEY_"
MAXIMUM_NAME_LENGTH = 60
MAXIMUM_URL_LENGTH = 300
MAXIMUM_MODEL_LENGTH = 100
MAXIMUM_KEY_LENGTH = 500
MODELS_TIMEOUT_SECONDS = 5.0
MAXIMUM_MODELS_BYTES = 512 * 1024
MAXIMUM_MODELS = 300

_KEY_PATTERN = re.compile(r"^[\x21-\x7e]+$")
_MODEL_PATTERN = re.compile(r"^[\x21-\x7e]+$")


@dataclass
class AiServerForm:
    """What the user typed for a server, checked."""

    server_id: str = ""
    name: str = ""
    kind: str = AI_KIND_OPENAI
    url: str = ""
    model: str = ""
    is_internal: bool = False
    # The key that was typed. Empty: the key that is saved stays.
    key: str = ""
    clear_key: bool = False
    errors: Dict[str, str] = field(default_factory=dict)


@dataclass
class AiServerView:
    """A server as the screen shows it. Never the key."""

    server: AiServer
    is_internal: bool
    is_forced_external: bool
    has_key: bool
    # "" when the server is used, else why it is not (a text for the user).
    problem: str


@dataclass
class AiOverview:
    servers: List[AiServerView]
    policy: AiPolicy
    policy_message: str


def parse_ai_server_form(
    *,
    server_id: str,
    name: str,
    kind: str,
    url: str,
    model: str,
    is_internal: bool,
    key: str,
    clear_key: bool,
    other_names: Sequence[str],
) -> AiServerForm:
    """
    Check the fields of a server. other_names are the names of the other
    servers. Nothing is saved while a field has an error.
    """
    form = AiServerForm(
        server_id=server_id,
        name=name.strip(),
        kind=kind.strip(),
        url=url.strip(),
        model=model.strip(),
        is_internal=is_internal,
        key=key.strip(),
        clear_key=clear_key,
    )
    errors = form.errors
    if len(form.name) == 0 or len(form.name) > MAXIMUM_NAME_LENGTH:
        errors["name"] = gettext("Give the server a name of up to 60 letters.")
    elif form.name.casefold() in {name_.casefold() for name_ in other_names}:
        errors["name"] = gettext("Another server has this name.")
    if form.kind not in AI_KINDS:
        errors["kind"] = gettext("Choose the type of the server.")
    if form.url == "" and form.kind == AI_KIND_ANTHROPIC:
        form.url = ANTHROPIC_URL
    url_error = _check_url(form.url)
    if url_error != "":
        errors["url"] = url_error
    elif (
        not _is_internal(form.kind, form.url, form.is_internal)
        and urlsplit(form.url).scheme != "https"
    ):
        errors["url"] = gettext("An external server needs an https address.")
    if (
        len(form.model) == 0
        or len(form.model) > MAXIMUM_MODEL_LENGTH
        or _MODEL_PATTERN.match(form.model) is None
    ):
        errors["model"] = gettext(
            "Choose the model in the list, or type its name."
        )
    if form.key != "" and (
        len(form.key) > MAXIMUM_KEY_LENGTH
        or _KEY_PATTERN.match(form.key) is None
    ):
        errors["key"] = gettext(
            "The key has letters, digits and signs, and no space."
        )
    return form


def save_ai_server(
    settings: DesktopSettings, form: AiServerForm, secret_store: SecretStore
) -> AiServer:
    """
    Put the server in the settings (the caller saves them) and the key in the
    keyring. A key typed is saved. With no key typed, the key stays, unless the
    user asked to remove it or the address changed: the key was for the old
    address. It raises SecretStoreError when the keyring refuses; the settings
    are then not changed.
    """
    existing = _find_server(settings, form.server_id)
    server = (
        AiServer.create()
        if existing is None
        else AiServer(server_id=existing.server_id)
    )
    server.name = form.name
    server.kind = form.kind
    server.url = form.url
    server.model = form.model
    server.is_internal = form.is_internal
    secret_name = get_ai_secret_name(server.server_id)
    if form.key != "":
        secret_store.set(secret_name, form.key)
    elif form.clear_key or (
        existing is not None
        and normalize_url(existing.url) != normalize_url(server.url)
    ):
        secret_store.delete(secret_name)
    if existing is None:
        settings.ai_servers.append(server)
    else:
        settings.ai_servers[settings.ai_servers.index(existing)] = server
    return server


def delete_ai_server(
    settings: DesktopSettings, server_id: str, secret_store: SecretStore
) -> bool:
    """
    Remove the server and its key. It returns False when there is no such
    server.
    """
    server = _find_server(settings, server_id)
    if server is None:
        return False
    secret_store.delete(get_ai_secret_name(server.server_id))
    settings.ai_servers.remove(server)
    return True


def get_key_variable(server_id: str) -> str:
    """
    The name that the provider reads its key under. It is a name of the
    private environment of the providers (get_provider_environment), never a
    variable of the process.
    """
    return f"{KEY_VARIABLE_PREFIX}{server_id}"


def get_provider_environment(
    settings: DesktopSettings, secret_store: SecretStore
) -> Dict[str, str]:
    """
    The keys of the servers, by the name that their provider reads. It is given
    to create_provider(environment=...): no key is in os.environ.
    """
    environment: Dict[str, str] = {}
    for server_ in settings.ai_servers:
        key = secret_store.get(get_ai_secret_name(server_.server_id))
        if key is not None and key.strip() != "":
            environment[get_key_variable(server_.server_id)] = key.strip()
    return environment


def get_server_problem(
    server: AiServer, secret_store: SecretStore, policy: AiPolicy
) -> str:
    """Why the server is not used, "" when it is."""
    if server.model.strip() == "":
        return gettext("Choose a model.")
    if len(server.url.strip()) == 0:
        return gettext("The address is missing.")
    if not is_ai_server_internal(server):
        if urlsplit(server.url).scheme != "https":
            return gettext("An external server needs an https address.")
        if not is_ai_server_complete(server, secret_store):
            return gettext("An external server needs a key.")
        if not policy.is_valid:
            return gettext(
                "Not used: the rules for external servers are missing."
            )
    return ""


def get_overview(
    settings: DesktopSettings, secret_store: SecretStore, policy: AiPolicy
) -> AiOverview:
    """What the screen of the settings shows of the servers."""
    views: List[AiServerView] = []
    for server_ in settings.ai_servers:
        key = secret_store.get(get_ai_secret_name(server_.server_id))
        views.append(
            AiServerView(
                server=server_,
                is_internal=is_ai_server_internal(server_),
                is_forced_external=(
                    server_.kind == AI_KIND_ANTHROPIC
                    or is_mistral_url(server_.url)
                ),
                has_key=key is not None and key.strip() != "",
                problem=get_server_problem(server_, secret_store, policy),
            )
        )
    return AiOverview(views, policy, get_policy_message(policy))


def build_llm_config(
    settings: DesktopSettings, secret_store: SecretStore, policy: AiPolicy
) -> LLMConfig:
    """
    The configuration of the assistant that the settings make: one provider for
    each server that is complete. The policy decides what the external servers
    may get. Without a valid policy, no external server is a provider.
    """
    providers: Dict[str, ProviderConfig] = {}
    environment: Dict[str, str] = {}
    internal_names: List[str] = []
    external_names: List[str] = []
    for server_ in settings.ai_servers:
        if get_server_problem(server_, secret_store, policy) != "":
            continue
        name = _get_provider_name(server_.name, providers)
        is_internal = is_ai_server_internal(server_)
        key = secret_store.get(get_ai_secret_name(server_.server_id))
        key_variable = ""
        if key is not None and key.strip() != "":
            # The key stays in the configuration of this application, which
            # gives it to the provider: it is never in os.environ.
            key_variable = get_key_variable(server_.server_id)
            environment[key_variable] = key.strip()
        providers[name] = _create_provider_config(
            server_, is_internal, key_variable
        )
        (internal_names if is_internal else external_names).append(name)
    names = internal_names + external_names
    return LLMConfig(
        default=names[0] if len(names) > 0 else "",
        providers=providers,
        allow_cloud=len(external_names) > 0,
        cloud_blocked_classifications=(
            list(policy.blocked_classifications) if policy.is_valid else []
        ),
        cloud_token_budget_per_month=(
            policy.monthly_token_budget if policy.is_valid else 0
        ),
        environment=environment,
    )


class AiRuntime:
    """
    The AI servers of the application, for the projects that are open: it
    gives each project its configuration of the assistant, and changes them
    all in place when the settings change.
    """

    def __init__(
        self,
        *,
        settings_path: Optional[Path],
        secret_store: SecretStore,
        audit_directory: Path,
        get_policy: Callable[[], AiPolicy] = load_ai_policy,
    ) -> None:
        self.settings_path: Optional[Path] = settings_path
        self.secret_store: SecretStore = secret_store
        # One audit log for the user, all the projects together: the budget of
        # the month is the one of the user.
        self.audit_directory: Path = audit_directory
        self._get_policy: Callable[[], AiPolicy] = get_policy
        self._lock: threading.Lock = threading.Lock()
        self._projects: List[weakref.ReferenceType[ProjectConfig]] = []

    def attach(self, project_config: ProjectConfig) -> None:
        """
        Replace the configuration of the assistant of a project, before its
        server is made. What the project declared (providers, knowledge base)
        is not used in the application.
        """
        project_config.llm = LLMConfig()
        project_config.audit_dir = str(self.audit_directory)
        with self._lock:
            self._projects = [
                reference_
                for reference_ in self._projects
                if reference_() is not None
            ]
            self._projects.append(weakref.ref(project_config))
        self._apply_to(project_config, self._build())

    def apply(self) -> None:
        """The settings changed: every project that is open follows."""
        new = self._build()
        with self._lock:
            projects = [
                project_
                for project_ in (reference_() for reference_ in self._projects)
                if project_ is not None
            ]
        for project_ in projects:
            self._apply_to(project_, new)

    def get_overview(self) -> AiOverview:
        return get_overview(
            load_settings(self.settings_path),
            self.secret_store,
            self._get_policy(),
        )

    def get_provider_environment(self) -> Dict[str, str]:
        return get_provider_environment(
            load_settings(self.settings_path), self.secret_store
        )

    def _build(self) -> LLMConfig:
        return build_llm_config(
            load_settings(self.settings_path),
            self.secret_store,
            self._get_policy(),
        )

    @staticmethod
    def _apply_to(project_config: ProjectConfig, new: LLMConfig) -> None:
        llm = project_config.llm
        assert llm is not None
        # A call that reads the configuration at the same time never finds a
        # provider without its key: the keys of both sides are there while the
        # providers change, and the old ones leave after.
        new_environment = new.environment
        old_environment = llm.environment
        if new_environment is not None:
            llm.environment = {
                **(old_environment if old_environment is not None else {}),
                **new_environment,
            }
        # A whole object for each field: a call that reads the configuration
        # at the same time sees the old providers or the new ones.
        llm.providers = new.providers
        llm.default = new.default
        llm.allow_cloud = new.allow_cloud
        llm.cloud_blocked_classifications = new.cloud_blocked_classifications
        llm.cloud_token_budget_per_month = new.cloud_token_budget_per_month
        llm.kb = None
        llm.environment = new_environment
        features = project_config.project_features
        if len(new.providers) > 0 and ProjectFeature.LLM not in features:
            features.append(ProjectFeature.LLM)
        elif len(new.providers) == 0 and ProjectFeature.LLM in features:
            features.remove(ProjectFeature.LLM)


@dataclass
class ModelList:
    models: List[str] = field(default_factory=list)
    # A text for the user when the list could not be read.
    message: str = ""


def list_models(
    *, kind: str, url: str, key: str, is_internal: bool
) -> ModelList:
    """
    Ask the server for its models. The request follows no redirect (a server
    must not send the key somewhere else), waits a few seconds, reads a limited
    answer, never sends a key over http to an external server, and never puts
    the key in a message.
    """
    address = url.strip()
    if _check_url(address) != "":
        return ModelList(message=_check_url(address))
    scheme = urlsplit(address).scheme
    if (
        key != ""
        and scheme != "https"
        and not _is_internal(kind, address, is_internal)
    ):
        return ModelList(
            message=gettext("An external server needs an https address.")
        )
    if kind == AI_KIND_ANTHROPIC:
        request_url = address.rstrip("/") + "/v1/models?limit=100"
        headers = {"anthropic-version": ANTHROPIC_VERSION}
        if key != "":
            headers["x-api-key"] = key
    else:
        request_url = address.rstrip("/") + "/models"
        headers = {"Authorization": f"Bearer {key}"} if key != "" else {}
    try:
        request = urllib.request.Request(
            request_url, headers=headers, method="GET"
        )
        with _OPENER.open(request, timeout=MODELS_TIMEOUT_SECONDS) as answer_:
            raw: bytes = answer_.read(MAXIMUM_MODELS_BYTES + 1)
    except urllib.error.HTTPError as error:
        # The body of an error may echo the key: it is not read.
        if 300 <= error.code < 400:
            return ModelList(
                message=gettext(
                    "The server redirects to another address: the address "
                    "of the server is probably wrong."
                )
            )
        if error.code in (401, 403):
            return ModelList(
                message=gettext("The server refused the key (or has none).")
            )
        return ModelList(message=gettext("The server cannot list its models."))
    except (urllib.error.URLError, OSError, ValueError):
        return ModelList(message=gettext("The server cannot be reached."))
    if len(raw) > MAXIMUM_MODELS_BYTES:
        return ModelList(message=gettext("The list of models is too long."))
    return _parse_models(raw)


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    return (
        f"{parts.scheme.lower()}://{(parts.netloc or '').lower()}"
        f"{parts.path.rstrip('/')}"
    )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_: Any, **__: Any) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _parse_models(raw: bytes) -> ModelList:
    try:
        data = json.loads(raw)
        identifiers = [
            str(item_["id"])
            for item_ in data["data"]
            if isinstance(item_, dict) and isinstance(item_.get("id"), str)
        ]
    except (ValueError, KeyError, TypeError, RecursionError):
        return ModelList(message=gettext("The server cannot list its models."))
    models = sorted(
        {
            id_
            for id_ in identifiers
            if 0 < len(id_) <= MAXIMUM_MODEL_LENGTH
            and _MODEL_PATTERN.match(id_) is not None
        }
    )[:MAXIMUM_MODELS]
    if len(models) == 0:
        return ModelList(message=gettext("The server lists no model."))
    return ModelList(models=models)


def _is_internal(kind: str, url: str, is_internal: bool) -> bool:
    return (
        not (kind == AI_KIND_ANTHROPIC or is_mistral_url(url)) and is_internal
    )


def _check_url(url: str) -> str:
    """A text for the user when the address is not usable, else ""."""
    if len(url) == 0 or len(url) > MAXIMUM_URL_LENGTH:
        return gettext("Give the address of the server, with http or https.")
    try:
        parts = urlsplit(url)
        host = parts.hostname
        parts.port  # noqa: B018 - raises ValueError for a bad port
    except ValueError:
        return gettext("Give the address of the server, with http or https.")
    if (
        parts.scheme not in ("http", "https")
        or host is None
        or host == ""
        or parts.username is not None
        or parts.password is not None
        or any(char_.isspace() for char_ in url)
    ):
        return gettext("Give the address of the server, with http or https.")
    return ""


def _find_server(
    settings: DesktopSettings, server_id: str
) -> Optional[AiServer]:
    for server_ in settings.ai_servers:
        if server_.server_id == server_id:
            return server_
    return None


def _get_provider_name(name: str, taken: Dict[str, ProviderConfig]) -> str:
    """A name for the assistant: letters, digits and hyphens, unique."""
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "server"
    candidate = base
    number = 2
    while candidate in taken:
        candidate = f"{base}-{number}"
        number += 1
    return candidate


def _create_provider_config(
    server: AiServer, is_internal: bool, key_variable: str
) -> ProviderConfig:
    if server.kind == AI_KIND_ANTHROPIC:
        return Anthropic(
            model=server.model.strip(),
            api_key_env=key_variable,
            base_url=server.url.strip().rstrip("/"),
        )
    return OpenAICompatible(
        base_url=server.url.strip().rstrip("/"),
        model=server.model.strip(),
        is_local=is_internal,
        api_key_env=key_variable,
    )
