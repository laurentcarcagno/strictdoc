import json

from strictdoc.core.project_config import ProjectConfig
from strictdoc.features.llm.config import Fake, LLMConfig


def create_config() -> ProjectConfig:
    answer = {
        "comments": [
            {
                "node": "REQ-1",
                "severity": "warning",
                "quote": "start",
                "body": "Start what, and when?",
            },
            {
                "node": "REQ-2",
                "severity": "info",
                "quote": "",
                "body": "Name the stopping condition.",
            },
        ]
    }
    return ProjectConfig(
        project_title="Assistant bar",
        project_features=["LLM", "COMMENTS"],
        llm=LLMConfig(
            default="fake",
            providers={"fake": Fake(answers=[json.dumps(answer)])},
        ),
    )
