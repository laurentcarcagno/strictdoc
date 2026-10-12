import os
import re

import pytest
from jinja2 import DictLoader, Environment

from strictdoc.core.project_config import ProjectConfigLoader
from strictdoc.features.i18n import i18n
from strictdoc.helpers.exception import StrictDocException

CATALOG = """
msgid ""
msgstr ""
"Language: fr\\n"
"Content-Type: text/plain; charset=utf-8\\n"
"Plural-Forms: nplurals=2; plural=(n > 1);\\n"

#: strictdoc/export/html/_static/nav.js:1
msgid "Save"
msgstr "Enregistrer"

msgid "Members of %(title)s"
msgstr "Membres de %(title)s"

msgid "Not translated yet"
msgstr ""
"""


@pytest.fixture(name="french")
def fixture_french(tmp_path, monkeypatch):
    """A French catalog in a folder of its own, then back to English."""
    folder = tmp_path / "fr" / "LC_MESSAGES"
    folder.mkdir(parents=True)
    (folder / "strictdoc.po").write_text(CATALOG, encoding="utf8")
    monkeypatch.setattr(i18n, "LOCALES_DIR", str(tmp_path))
    i18n._load.cache_clear()
    i18n.set_language("fr")
    yield
    i18n.set_language("en")
    i18n._load.cache_clear()


def test_001_english_is_the_default_and_keeps_the_texts():
    assert i18n.get_language() == "en"
    assert i18n.gettext("Save") == "Save"
    assert i18n.js_catalog() == {}


@pytest.mark.usefixtures("french")
def test_002_a_catalog_translates_the_texts_it_has():
    assert i18n.gettext("Save") == "Enregistrer"
    # A text that the catalog does not translate stays English.
    assert i18n.gettext("Not translated yet") == "Not translated yet"
    assert i18n.gettext("Unknown") == "Unknown"


@pytest.mark.usefixtures("french")
def test_003_the_templates_follow_the_language():
    environment = Environment(
        loader=DictLoader(
            {
                "page": (
                    '{{ _("Save") }} | {{ _("Members of %(title)s", '
                    'title="ISIS") }} | {% trans %}Save{% endtrans %} | '
                    "{{ sdoc_language() }}"
                )
            }
        ),
        autoescape=True,
    )
    i18n.install(environment)
    assert environment.get_template("page").render() == (
        "Enregistrer | Membres de ISIS | Enregistrer | fr"
    )


@pytest.mark.usefixtures("french")
def test_004_the_scripts_get_the_texts_of_the_scripts_only():
    # "Members of %(title)s" is a text of the templates: not embedded.
    assert i18n.js_catalog() == {"Save": "Enregistrer"}


def test_005_an_unknown_language_is_refused():
    with pytest.raises(ValueError):
        i18n.set_language("de")
    assert i18n.get_language() == "en"


def test_006_the_project_option_and_the_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("STRICTDOC_LANGUAGE", raising=False)
    path = tmp_path / "strictdoc.toml"
    path.write_text('[project]\ntitle = "T"\nlanguage = "fr"\n')
    config = ProjectConfigLoader.load_from_path_or_get_default(
        path_to_config=str(path)
    )
    assert config.language == "fr"

    # The deployment wins over the project file.
    monkeypatch.setenv("STRICTDOC_LANGUAGE", "en")
    config = ProjectConfigLoader.load_from_path_or_get_default(
        path_to_config=str(path)
    )
    assert config.language == "en"


def test_007_a_bad_language_in_the_project_file_is_an_error(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("STRICTDOC_LANGUAGE", raising=False)
    path = tmp_path / "strictdoc.toml"
    path.write_text('[project]\ntitle = "T"\nlanguage = "klingon"\n')
    config = ProjectConfigLoader.load_from_path_or_get_default(
        path_to_config=str(path)
    )
    config.input_paths = [str(tmp_path)]
    with pytest.raises(StrictDocException, match="language"):
        config.validate_and_finalize()
    assert os.environ.get("STRICTDOC_LANGUAGE") is None


def test_008_the_french_catalog_is_complete_and_keeps_the_placeholders():
    """
    Every text of the real catalog is translated, with the same
    %(name)s placeholders (a missing one breaks the page).
    """
    from babel.messages.pofile import read_po  # noqa: PLC0415

    path = os.path.join(
        i18n.LOCALES_DIR, "fr", "LC_MESSAGES", f"{i18n.DOMAIN}.po"
    )
    with open(path, "rb") as file_:
        catalog = read_po(file_, locale="fr")
    placeholder = re.compile(r"%\([a-z_]+\)s")
    for message_ in catalog:
        if not message_.id:
            continue
        assert message_.string, message_.id
        assert sorted(placeholder.findall(message_.id)) == sorted(
            placeholder.findall(message_.string)
        ), message_.id
