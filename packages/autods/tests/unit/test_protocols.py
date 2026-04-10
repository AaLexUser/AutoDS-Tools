from autods.environments.jupyter import JupyterExecutor
from autods.tools.base import Observation


def test_jupyter_executor_is_importable_from_core() -> None:
    assert JupyterExecutor.__name__ == "JupyterExecutor"


def test_observation_model_defaults() -> None:
    observation = Observation(is_success=True, message="ok")

    assert observation.base64_images is None
