from typing import Any, Dict, Optional


class BaseSkill:
    """Minimal interface for built-in and engineer-authored skills."""

    name = ""
    description = ""
    input_schema: Dict[str, Any] = {}
    output_schema: Dict[str, Any] = {}
    enabled = True

    def run(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        raise NotImplementedError

    def metadata(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "enabled": self.enabled,
            "type": self.__class__.__name__,
        }
