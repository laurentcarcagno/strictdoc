import json

from strictdoc.core.project_config import ProjectConfig
from strictdoc.features.llm.config import Fake, LLMConfig


def create_config() -> ProjectConfig:
    answer = {
        "text": "When started, the system shall start, see [LINK: REQ-2].",
        "notes": "Event-driven pattern.",
    }
    return ProjectConfig(
        project_title="Assistant bar",
        project_features=["LLM"],
        llm=LLMConfig(
            default="fake",
            providers={"fake": Fake(answers=[json.dumps(answer)])},
        ),
    )
