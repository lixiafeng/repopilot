from pathlib import Path
import typer
from repo_pilot.config import RepoPilotConfig
from repo_pilot.workflow import BugfixWorkflow

app=typer.Typer(name="repo-pilot")

@app.command()
def run(
    repo:Path=typer.Option(...,"--repo"),
    issue: str=typer.Option(...,"--issue"),
    test_command: str=typer.Option("python -m pytest -q","--test-command"),
    provider: str=typer.Option("fake","--provider"),
    model:str=typer.Option("fake-model","--model"),
    apply_patch:bool=typer.Option(True,"--aplply/--no-apply"),
    max_iterations:int =typer.Option(2,"--max-iterations"),
):
    config=RepoPilotConfig(
        provider=provider,
        model=model,
        apply_patch=apply_patch,
        max_iterations=max_iterations,
    )

    workflow=BugfixWorkflow(config)
    result=workflow.run(
        repo=repo,
        issue=issue,
        test_command=test_command,
    )
    if result.success:
        typer.echo("SUCCESS")
    else:
        typer.echo("FAILURE")
    typer.echo(result.message)


if __name__=="__main__":
    app()


