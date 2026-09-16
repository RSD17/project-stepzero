import csv
import json

import pytest

from experiments.cli import main
from experiments.definitions import list_experiments

# A deliberately tiny grid so the command line tests stay fast.
FAST_RUN = ["--seeds", "11", "--max-sessions", "10", "--quiet"]


def test_list_command_reports_every_registered_experiment(capsys):
    assert main(["list"]) == 0
    output = capsys.readouterr().out
    for name in list_experiments():
        assert name in output


def test_run_command_prints_a_summary(capsys):
    assert main(["run", "weighting_profile_comparison", "--no-save", *FAST_RUN]) == 0
    output = capsys.readouterr().out
    assert "Experiment: weighting_profile_comparison" in output
    assert "Ranking by 'completion_rate'" in output
    assert "signal to noise" in output


def test_run_command_writes_json_and_csv(tmp_path, capsys):
    exit_code = main([
        "run", "weighting_profile_comparison", "--output-dir", str(tmp_path), *FAST_RUN
    ])
    assert exit_code == 0

    json_path = tmp_path / "weighting_profile_comparison.json"
    csv_path = tmp_path / "weighting_profile_comparison.csv"
    assert json_path.exists()
    assert csv_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["config"]["name"] == "weighting_profile_comparison"
    assert len(payload["runs"]) == 15

    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        assert len(list(csv.DictReader(f))) == 15


def test_run_command_respects_seed_and_session_overrides(tmp_path):
    main(["run", "seed_stability", "--output-dir", str(tmp_path), "--seeds", "1", "2",
          "--max-sessions", "10", "--quiet"])
    payload = json.loads((tmp_path / "seed_stability.json").read_text(encoding="utf-8"))
    assert payload["config"]["seeds"] == [1, 2]
    assert payload["config"]["simulation"]["max_sessions"] == 10
    assert len(payload["runs"]) == 2


def test_run_command_rejects_unknown_experiment(capsys):
    assert main(["run", "no_such_experiment", "--no-save"]) == 2
    assert "Unknown experiment" in capsys.readouterr().err


def test_run_command_rejects_duplicate_seed_override(capsys):
    assert main(["run", "seed_stability", "--no-save", "--seeds", "7", "7"]) == 2
    assert "duplicate seeds" in capsys.readouterr().err


def test_show_command_summarizes_a_saved_file(tmp_path, capsys):
    main(["run", "weighting_profile_comparison", "--output-dir", str(tmp_path), *FAST_RUN])
    capsys.readouterr()

    path = tmp_path / "weighting_profile_comparison.json"
    assert main(["show", str(path)]) == 0
    output = capsys.readouterr().out
    assert "weighting_profile_comparison" in output
    assert "Ranking by 'completion_rate'" in output


def test_show_command_supports_lower_is_better(tmp_path, capsys):
    main(["run", "weighting_profile_comparison", "--output-dir", str(tmp_path), *FAST_RUN])
    capsys.readouterr()

    path = tmp_path / "weighting_profile_comparison.json"
    assert main(["show", str(path), "--metric", "total_study_hours", "--lower-is-better"]) == 0
    assert "lower is better" in capsys.readouterr().out


def test_show_command_can_regroup_results(tmp_path, capsys):
    main(["run", "weighting_profile_comparison", "--output-dir", str(tmp_path), *FAST_RUN])
    capsys.readouterr()

    path = tmp_path / "weighting_profile_comparison.json"
    assert main(["show", str(path), "--group-by", "profile_id"]) == 0
    assert "beginner_student" in capsys.readouterr().out


def test_show_command_reports_a_missing_file(tmp_path, capsys):
    assert main(["show", str(tmp_path / "absent.json")]) == 2
    assert "not found" in capsys.readouterr().err.lower()


def test_show_command_rejects_unrelated_json(tmp_path, capsys):
    path = tmp_path / "other.json"
    path.write_text('{"unrelated": true}', encoding="utf-8")
    assert main(["show", str(path)]) == 2
    assert "Experiment error" in capsys.readouterr().err


def test_cli_requires_a_command():
    with pytest.raises(SystemExit):
        main([])
