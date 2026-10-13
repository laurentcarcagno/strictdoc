import json

from strictdoc.core.project_config import ProjectConfig
from strictdoc.features.llm.config import Fake, LLMConfig


def create_config() -> ProjectConfig:
    rewrite = {
        "text": "The system shall start within 2 s.",
        "notes": "Concise.",
    }
    comment = {
        "comments": [
            {
                "severity": "warning",
                "quote": "start",
                "body": "Which start: power on or after a reset?",
            }
        ]
    }
    return ProjectConfig(
        project_features=["COMMENTS", "LLM"],
        llm=LLMConfig(
            default="local",
            providers={
                "local": Fake(
                    answers=[json.dumps(rewrite), json.dumps(comment)],
                    is_local=True,
                )
            },
        ),
    )
