import logging

from jinja2 import Environment, FileSystemLoader

from domain.genai.prompt import PromptRepository
from infrastructure.core.config import genai_config

logger = logging.getLogger(__name__)


class PromptJinjaRepository(PromptRepository):
    def __init__(self, route: str = genai_config.PROMPT_REPOSITORY_ROUTE):
        self.route = route

    def __enter__(self):
        self.environment = Environment(loader=FileSystemLoader(self.route))

    def get_prompt(self, template: str, template_parameters: dict = None):
        if template_parameters is None:
            template_parameters = {}

        logger.info(f"Reading template {template}")
        prompt = self.environment.get_template(template)
        logger.info(f"Reading prompt {prompt}")
        return prompt.render(template_parameters).replace("\n", "")

    def close(self):
        pass
