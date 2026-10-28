import pytest

from experiments.power.config import PowerConfig
from experiments.power.replicate import ScenarioKey


@pytest.fixture(scope="session")
def power_config() -> PowerConfig:
    # The committed provisional configuration, loaded once per session.
    return PowerConfig.load()


@pytest.fixture
def reference_key(power_config) -> ScenarioKey:
    return ScenarioKey(
        groups_per_subject=6,
        students_per_group=8,
        effect_id="homog_030",
        variance_id=power_config.variance_reference.variance_id,
        missingness_id=power_config.reference_missingness_id,
        recruitment_id=power_config.reference_recruitment_id,
    )


@pytest.fixture
def null_key(power_config) -> ScenarioKey:
    return ScenarioKey(
        groups_per_subject=6,
        students_per_group=8,
        effect_id="null",
        variance_id=power_config.variance_reference.variance_id,
        missingness_id=power_config.reference_missingness_id,
        recruitment_id=power_config.reference_recruitment_id,
    )
