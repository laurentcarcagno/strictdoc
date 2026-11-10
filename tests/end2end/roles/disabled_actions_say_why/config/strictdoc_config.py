from strictdoc.core.project_config import ProjectConfig


def create_config() -> ProjectConfig:
    # Behind a login proxy that the test plays: the browser sends the
    # identity headers from 127.0.0.1.
    return ProjectConfig(
        project_title="Roles test",
        auth_mode="proxy",
        trusted_proxies=["127.0.0.1/32"],
        roles={
            "administrator": ["t-admins"],
            "author": ["t-authors"],
            "reviewer": ["t-reviewers"],
            "reader": ["t-readers"],
        },
    )
