"""
The frame of a server screen that a feature renders by itself: the sidebar
and the page header of the project around the content of the feature
(_shared/app_screen.jinja.html).

@relation(SDOC-SRS-211, scope=file)
"""

from markupsafe import Markup

from strictdoc import __version__
from strictdoc.core.project_config import ProjectConfig
from strictdoc.export.html.html_templates import JinjaEnvironment
from strictdoc.export.html.renderers.link_renderer import LinkRenderer


class AppScreenViewObject:
    def __init__(
        self,
        *,
        project_config: ProjectConfig,
        title: str,
        viewtype: str,
        content: Markup,
    ) -> None:
        """
        title: the name of the screen in the page header and the tab.
        viewtype: the value of data-viewtype on <body>, which marks the item
        of the sidebar that is the current screen.
        content: the HTML of the feature, inside the main area.
        """
        self.project_config: ProjectConfig = project_config
        self.title: str = title
        self.viewtype: str = viewtype
        self.content: Markup = content
        self.is_running_on_server: bool = project_config.is_running_on_server
        self.strictdoc_version: str = __version__
        self.link_renderer: LinkRenderer = LinkRenderer(
            root_path="", static_path=project_config.dir_for_sdoc_assets
        )

    def render_screen(self, jinja_environment: JinjaEnvironment) -> Markup:
        return jinja_environment.render_template_as_markup(
            "_shared/app_screen.jinja.html", view_object=self
        )

    def get_document_level(self) -> int:
        return 0

    def render_url(self, url: str) -> Markup:
        return Markup(self.link_renderer.render_url(url))

    def render_static_url(self, url: str) -> str:
        return self.link_renderer.render_static_url(url)

    def render_static_url_with_prefix(self, url: str) -> str:
        return self.link_renderer.render_static_url_with_prefix(url)


def render_app_screen(
    *,
    jinja_environment: JinjaEnvironment,
    project_config: ProjectConfig,
    title: str,
    viewtype: str,
    content_template: str,
    **content_variables: object,
) -> Markup:
    """
    Renders the template of a feature, then the frame around it. The
    template of the feature has the content of the page only.
    """
    content = jinja_environment.render_template_as_markup(
        content_template, **content_variables
    )
    return AppScreenViewObject(
        project_config=project_config,
        title=title,
        viewtype=viewtype,
        content=content,
    ).render_screen(jinja_environment)
