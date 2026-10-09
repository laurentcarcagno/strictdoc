from strictdoc.core.project_config import ProjectConfig


def create_config() -> ProjectConfig:
    return ProjectConfig(
        project_title="Docx update test",
        docx_profile="profile.py",
        docx_base="../base/input.docx",
    )
