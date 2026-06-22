"""CLI entry point for contract Q&A agent."""

from __future__ import annotations

import typer

from agent.agent import ContractAgent

app = typer.Typer(help="Ask questions about extracted contract data")


@app.command()
def main() -> None:
    typer.echo("WriteWise Contract Q&A Agent")
    typer.echo("Type 'exit' or Ctrl+C to quit.\n")
    agent = ContractAgent()
    while True:
        try:
            question = typer.prompt("You")
        except (EOFError, KeyboardInterrupt):
            typer.echo("\nGoodbye.")
            raise typer.Exit(0) from None
        if question.strip().lower() in {"exit", "quit"}:
            typer.echo("Goodbye.")
            raise typer.Exit(0)
        answer = agent.ask(question)
        typer.echo(f"\nAgent: {answer}\n")


if __name__ == "__main__":
    app()
