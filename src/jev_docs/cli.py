"""A script-friendly CLI: JSON on stdout, progress/errors on stderr."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from .errors import JevDocsError
from .rules import load_rules

app = typer.Typer(no_args_is_help=True, help="Classify and split documents with Jev + LiteParse.")


def emit(value: dict, output: Path | None = None, overwrite: bool = False) -> None:
    data = json.dumps(value, indent=2, ensure_ascii=False)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            with output.open("w" if overwrite else "x") as stream:
                stream.write(data + "\n")
        except FileExistsError:
            raise JevDocsError("Output file exists; use --overwrite or another path.") from None
    else:
        typer.echo(data)


@app.command()
def doctor(smoke: bool = False):
    """Check installation, converter, and credential presence without calling APIs."""
    from .doctor import doctor as check

    emit(check(smoke=smoke))


@app.command("parse")
def parse_command(
    document: Path,
    ocr: str = "liteparse",
    tier: str = "agentic",
    parser_version: str = "latest",
    no_cache: bool = False,
    output: Path | None = None,
    overwrite: bool = False,
):
    """Return ordered, complete page text without making a Jev call."""
    from .documents import parse_document

    try:
        emit(
            parse_document(
                document, ocr=ocr, tier=tier, parser_version=parser_version, use_cache=not no_cache
            ).model_dump(mode="json"),
            output,
            overwrite,
        )
    except (JevDocsError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None


@app.command("classify")
def classify_command(
    document: Path,
    rules: Annotated[Path, typer.Option(...)],
    ocr: str = "liteparse",
    tier: str = "agentic",
    parser_version: str = "latest",
    engine: str = "jev",
    model: str | None = None,
    no_cache: bool = False,
    output: Path | None = None,
    overwrite: bool = False,
):
    """Classify a file, or emit one JSONL success/error per file in a directory."""
    from .classify import classify_document

    try:
        config = load_rules(rules)
        if document.is_dir():
            files = sorted(
                p for p in document.iterdir() if p.suffix.lower() in {".pdf", ".docx", ".pptx"}
            )
            if not files:
                raise JevDocsError("No PDF, DOCX, or PPTX files found in the directory.")
            rows = []
            failed = False
            for path in files:
                typer.echo(f"Classifying {path.name}", err=True)
                try:
                    result = classify_document(
                        path,
                        config,
                        ocr=ocr,
                        tier=tier,
                        parser_version=parser_version,
                        engine=engine,
                        model=model,
                        use_cache=not no_cache,
                    )
                    rows.append(
                        {
                            "file": path.name,
                            "status": "ok",
                            "result": result.model_dump(mode="json"),
                        }
                    )
                except (JevDocsError, ValueError) as exc:
                    failed = True
                    rows.append({"file": path.name, "status": "error", "error": str(exc)})
            data = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
            if output:
                output.parent.mkdir(parents=True, exist_ok=True)
                with output.open("w" if overwrite else "x") as stream:
                    stream.write(data)
            else:
                typer.echo(data, nl=False)
            if failed:
                raise typer.Exit(1)
        else:
            result = classify_document(
                document,
                config,
                ocr=ocr,
                tier=tier,
                parser_version=parser_version,
                engine=engine,
                model=model,
                use_cache=not no_cache,
            )
            emit(result.model_dump(mode="json"), output, overwrite)
    except (JevDocsError, ValueError, FileExistsError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None


@app.command("split")
def split_command(
    document: Path,
    rules: Annotated[Path, typer.Option(...)],
    ocr: str = "liteparse",
    tier: str = "agentic",
    parser_version: str = "latest",
    engine: str = "jev",
    model: str | None = None,
    no_cache: bool = False,
    boundary_threshold: float = 0.5,
    boundary_review_margin: Annotated[float, typer.Option(min=0, max=0.5, help="Flag boundary scores within this distance of the decision threshold; 0 disables.")] = 0.1,
    output: Path | None = None,
    export_dir: Path | None = None,
    overwrite: bool = False,
):
    """Identify contiguous source documents and optionally export their PDF pages."""
    from .documents import parse_document
    from .export import export_segments
    from .split import split_document

    try:
        config = load_rules(rules)
        parsed = parse_document(
            document, ocr=ocr, tier=tier, parser_version=parser_version, use_cache=not no_cache
        )
        result = split_document(
            parsed, config, engine=engine, model=model, boundary_threshold=boundary_threshold,
            boundary_review_margin=boundary_review_margin,
        )
        if export_dir:
            export_segments(parsed, result, export_dir, overwrite=overwrite)
        emit(result.model_dump(mode="json"), output, overwrite)
    except (JevDocsError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None


@app.command()
def demo(port: int = 8765):
    """Open the local visual demo (requires the demo extra)."""
    try:
        import uvicorn

        from .web.app import create_app
    except ImportError:
        typer.echo("Install docjev[demo] to run the visual demo.", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"DocJev: http://127.0.0.1:{port}", err=True)
    uvicorn.run(create_app(), host="127.0.0.1", port=port)


if __name__ == "__main__":
    app()
