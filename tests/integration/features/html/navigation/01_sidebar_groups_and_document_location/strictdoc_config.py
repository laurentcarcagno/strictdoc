from strictdoc.core.project_config import ProjectConfig


def create_config() -> ProjectConfig:
    return ProjectConfig(
        project_title="Navigation test",
        project_features=["TRACEABILITY_MATRIX_SCREEN", "TREE_MAP_SCREEN"],
    )
