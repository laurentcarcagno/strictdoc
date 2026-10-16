from strictdoc.core.project_config import ProjectConfig
from strictdoc.features.git_config.config import GitConfig


def create_config() -> ProjectConfig:
    return ProjectConfig(
        project_title="Sync Test",
        project_features=["GIT"],
        git=GitConfig(push_on_tag=False),
    )
