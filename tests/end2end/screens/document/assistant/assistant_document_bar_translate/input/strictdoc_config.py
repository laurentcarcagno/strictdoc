import json

from strictdoc.core.project_config import ProjectConfig
from strictdoc.features.llm.config import Fake, LLMConfig


def create_config() -> ProjectConfig:
    # The refs of the batch are n1, n2 for the two requirements, doc for the title.
    answer = {
        "nodes": [
            {"ref": "doc", "fields": {"TITLE": "Document 1 (FR)"}},
            {
                "ref": "n1",
                "fields": {
                    "STATEMENT": "Le système doit démarrer, voir [LINK: REQ-2]."
                },
            },
            {
                "ref": "n2",
                "fields": {"STATEMENT": "Le système doit s'arrêter."},
            },
        ]
    }
    return ProjectConfig(
        project_title="Assistant bar",
        project_features=["LLM"],
        llm=LLMConfig(
            default="fake",
            providers={"fake": Fake(answers=[json.dumps(answer)])},
        ),
    )
