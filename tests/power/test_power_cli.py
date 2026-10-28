import json

import pytest

from experiments.power.cli import main

FAST = ["--replications", "20", "--quiet"]


def test_validate_config_reports_the_hash_and_provisional_warning(capsys, power_config):
    assert main(["validate-config"]) == 0
    output = capsys.readouterr().out
    assert power_config.config_hash() in output
    assert "PROVISIONAL" in output
    assert "14.3" in output


def test_plans_lists_every_plan(capsys):
    assert main(["plans"]) == 0
    output = capsys.readouterr().out
    for name in ("primary", "pilot", "icc_sensitivity", "attrition_sensitivity", "imbalance"):
        assert name in output


def test_run_pilot_prints_a_summary_without_saving(capsys):
    assert main(["run", "pilot", "--no-save", *FAST]) == 0
    output = capsys.readouterr().out
    assert "Power surface: pilot" in output
    assert "PROVISIONAL" in output


def test_run_writes_json_and_csv(tmp_path, capsys):
    assert main(["run", "pilot", "--output-dir", str(tmp_path), *FAST]) == 0
    capsys.readouterr()
    json_path = tmp_path / "power_surface_pilot.json"
    csv_path = tmp_path / "power_surface_pilot.csv"
    assert json_path.exists() and csv_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["metadata"]["plan_name"] == "pilot"
    assert payload["metadata"]["replications_requested"] == 20
    assert len(payload["cells"]) == 2


def test_run_rejects_an_unknown_plan(capsys):
    assert main(["run", "not_a_plan", "--no-save"]) == 2
    assert "Unknown plan" in capsys.readouterr().err


def test_summarize_reads_a_saved_surface(tmp_path, capsys):
    main(["run", "pilot", "--output-dir", str(tmp_path), *FAST])
    capsys.readouterr()
    assert main(["summarize", str(tmp_path / "power_surface_pilot.json")]) == 0
    assert "Power surface: pilot" in capsys.readouterr().out


def test_summarize_reports_a_missing_file(tmp_path, capsys):
    assert main(["summarize", str(tmp_path / "absent.json")]) == 2
    assert "not found" in capsys.readouterr().err.lower()


def test_select_reports_criteria_and_refuses_to_auto_pick(tmp_path, capsys):
    main(["run", "pilot", "--output-dir", str(tmp_path), *FAST])
    capsys.readouterr()
    assert main(["select", str(tmp_path / "power_surface_pilot.json")]) == 0
    output = capsys.readouterr().out
    assert "methodology decisions" in output
    # Either no design passes, or the smallest passing design is explicitly not auto-selected.
    assert ("does not yet support locking a design" in output) or ("NOT automatically" in output)


def test_verify_reproducibility_passes_across_worker_counts(capsys):
    assert main(["verify-reproducibility", "--plan", "pilot", "--replications", "12",
                 "--workers", "1", "2"]) == 0
    output = capsys.readouterr().out
    assert "Identical across worker counts [1, 2]: True" in output
    assert "Repeated run with the same worker count is identical: True" in output


def test_visualize_writes_figures(tmp_path, capsys):
    main(["run", "pilot", "--output-dir", str(tmp_path), *FAST])
    capsys.readouterr()
    figures = tmp_path / "figures"
    assert main(["visualize", str(tmp_path / "power_surface_pilot.json"),
                 "--output-dir", str(figures)]) == 0
    written = list(figures.glob("*.png"))
    assert written
    assert all(path.stat().st_size > 1000 for path in written)


def test_custom_config_path_is_honoured(tmp_path, capsys, power_config):
    payload = power_config.to_dict()
    payload["master_seed"] = 12345
    path = tmp_path / "custom.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert main(["--config", str(path), "validate-config"]) == 0
    assert "12345" in capsys.readouterr().out


def test_invalid_config_is_reported(tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    assert main(["--config", str(path), "validate-config"]) == 2
    assert "Power analysis error" in capsys.readouterr().err


def test_cli_requires_a_command():
    with pytest.raises(SystemExit):
        main([])


# The validation figure and suite entry points must be reachable from the CLI.
def test_cli_exposes_the_validation_suite_and_figure_commands():
    from experiments.power.cli import _build_parser

    parser = _build_parser()
    suite = parser.parse_args(
        ["bootstrap-validate", "--suite", "--replications", "5", "--resamples", "7", "--workers", "2"]
    )
    assert suite.suite is True
    assert suite.replications == 5
    assert suite.resamples == 7
    assert suite.workers == 2

    figures = parser.parse_args(["visualize-validation", "some/path.json"])
    assert figures.command == "visualize-validation"
    assert figures.path == "some/path.json"
