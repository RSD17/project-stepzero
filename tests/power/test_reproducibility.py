import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from experiments.power.config import PowerConfig
from experiments.power.replicate import ScenarioKey, replicate_rng, run_single_simulation
from experiments.power.surface import compute_operating_characteristics, run_design_cell

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def signature_of(record) -> tuple:
    return (record.status, record.estimate, record.standard_error, record.p_one_sided, record.n_observed)


# Deterministic streams

def test_same_seed_and_cell_give_the_same_stream(power_config):
    first = replicate_rng(power_config.master_seed, "cell", 3).standard_normal(5)
    second = replicate_rng(power_config.master_seed, "cell", 3).standard_normal(5)
    assert np.array_equal(first, second)


def test_different_replicate_index_gives_a_different_stream(power_config):
    first = replicate_rng(power_config.master_seed, "cell", 3).standard_normal(5)
    second = replicate_rng(power_config.master_seed, "cell", 4).standard_normal(5)
    assert not np.array_equal(first, second)


def test_different_cell_gives_a_different_stream(power_config):
    first = replicate_rng(power_config.master_seed, "cell_a", 0).standard_normal(5)
    second = replicate_rng(power_config.master_seed, "cell_b", 0).standard_normal(5)
    assert not np.array_equal(first, second)


def test_different_master_seed_gives_a_different_stream():
    first = replicate_rng(1, "cell", 0).standard_normal(5)
    second = replicate_rng(2, "cell", 0).standard_normal(5)
    assert not np.array_equal(first, second)


def test_replicate_is_reproducible(power_config, reference_key):
    a = run_single_simulation(power_config, reference_key, 7)
    b = run_single_simulation(power_config, reference_key, 7)
    assert signature_of(a) == signature_of(b)
    assert a.estimate == b.estimate


def test_different_replicates_differ(power_config, reference_key):
    a = run_single_simulation(power_config, reference_key, 0)
    b = run_single_simulation(power_config, reference_key, 1)
    assert a.estimate != b.estimate


def test_master_seed_changes_the_result(power_config, reference_key):
    other = PowerConfig.from_dict({**power_config.to_dict(), "master_seed": power_config.master_seed + 1})
    a = run_single_simulation(power_config, reference_key, 0)
    b = run_single_simulation(other, reference_key, 0)
    assert a.estimate != b.estimate


# Worker-count invariance

def test_cell_result_is_identical_across_worker_counts(power_config, reference_key):
    serial = run_design_cell(power_config, reference_key, replications=24, workers=1)
    parallel_two = run_design_cell(power_config, reference_key, replications=24, workers=2)
    parallel_four = run_design_cell(power_config, reference_key, replications=24, workers=4)
    assert serial.characteristics.to_dict() == parallel_two.characteristics.to_dict()
    assert serial.characteristics.to_dict() == parallel_four.characteristics.to_dict()


def test_records_are_returned_in_replicate_order(power_config, reference_key):
    cell = run_design_cell(power_config, reference_key, replications=16, workers=4, retain_records=True)
    assert [r.replicate_index for r in cell.records] == list(range(16))


def test_surface_signature_is_worker_independent(power_config, reference_key):
    keys = [reference_key]
    one = compute_operating_characteristics(power_config, keys, "unit", replications=16, workers=1)
    four = compute_operating_characteristics(power_config, keys, "unit", replications=16, workers=4)
    assert one.signature() == four.signature()


def test_surface_signature_excludes_timestamps(power_config, reference_key):
    one = compute_operating_characteristics(power_config, [reference_key], "unit", replications=8)
    two = compute_operating_characteristics(power_config, [reference_key], "unit", replications=8)
    assert one.signature() == two.signature()
    assert one.metadata["created_at"] is not None


# Independence from interpreter state

@pytest.mark.parametrize("hash_seed", ["0", "1", "12345", "random"])
def test_results_are_independent_of_python_hash_seed(tmp_path, hash_seed):
    code = (
        "import json;"
        "from experiments.power.config import PowerConfig;"
        "from experiments.power.replicate import ScenarioKey, run_single_simulation;"
        "c=PowerConfig.load();"
        "k=ScenarioKey(6,8,'homog_030',c.variance_reference.variance_id,'no_attrition','balanced');"
        "r=run_single_simulation(c,k,0);"
        "print(json.dumps([r.status, r.estimate, r.standard_error]))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=tmp_path,
        env={"PYTHONHASHSEED": hash_seed, "PYTHONPATH": str(PROJECT_ROOT)},
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip())

    reference = run_single_simulation(
        PowerConfig.load(),
        ScenarioKey(6, 8, "homog_030", PowerConfig.load().variance_reference.variance_id,
                    "no_attrition", "balanced"),
        0,
    )
    assert payload[0] == reference.status
    assert payload[1] == pytest.approx(reference.estimate, rel=0, abs=0)
    assert payload[2] == pytest.approx(reference.standard_error, rel=0, abs=0)
