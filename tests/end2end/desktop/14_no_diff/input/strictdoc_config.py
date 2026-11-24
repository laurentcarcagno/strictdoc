from strictdoc.core.project_config import ProjectConfig


def create_config() -> ProjectConfig:
    return ProjectConfig(
        project_title="Project that declares DIFF",
        project_features=["TABLE_SCREEN", "TRACEABILITY_SCREEN", "DIFF"],
    )
