import json

from typer.testing import CliRunner

from jev_docs.cli import app

runner = CliRunner()


def test_help_has_tasks():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "classify" in result.stdout and "split" in result.stdout


def test_doctor_only_reports_key_presence(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "do-not-print-this-secret")
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "do-not-print-this-secret" not in result.stdout
    assert json.loads(result.stdout)["credentials"]["TYPESAFE_API_KEY"] is True


def test_missing_rules_actionable(tmp_path):
    result = runner.invoke(
        app, ["classify", str(tmp_path / "missing.pdf"), "--rules", str(tmp_path / "no-rules.yaml")]
    )
    assert result.exit_code == 1
    assert not result.stdout
    assert "rules" in result.stderr.lower()


def test_no_overwrite(tmp_path, monkeypatch, document):
    monkeypatch.setattr("jev_docs.documents.parse_document", lambda *a, **k: document)
    output = tmp_path / "result.json"
    output.write_text("keep me")
    result = runner.invoke(app, ["parse", "fixture.pdf", "--output", str(output)])
    assert result.exit_code == 1
    assert output.read_text() == "keep me"
