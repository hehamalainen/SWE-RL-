"""
Command-line interface for SSR Studio.

Provides commands for:
- Running the API server
- Managing environments
- Running episodes
- Viewing metrics
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional
from uuid import UUID

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

app = typer.Typer(
    name="ssr",
    help="SSR Studio - Self-Play SWE-RL Demo & Research Platform",
    add_completion=False,
)

console = Console()


# =============================================================================
# Server Commands
# =============================================================================

@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload"),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of workers"),
):
    """Start the SSR Studio API server."""
    import uvicorn
    
    console.print(f"[bold green]Starting SSR Studio server on {host}:{port}[/]")
    
    uvicorn.run(
        "ssr_studio.api:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers,
    )


# =============================================================================
# Environment Commands
# =============================================================================

@app.command()
def env_list():
    """List all registered environments."""
    from ssr_studio.database import async_session_factory, EnvironmentDB
    from sqlalchemy import select
    
    async def _list():
        async with async_session_factory() as db:
            result = await db.execute(
                select(EnvironmentDB).order_by(EnvironmentDB.created_at.desc())
            )
            environments = result.scalars().all()
            
            if not environments:
                console.print("[yellow]No environments registered[/]")
                return
            
            table = Table(title="Environments")
            table.add_column("ID", style="dim")
            table.add_column("Name", style="cyan")
            table.add_column("Image", style="green")
            table.add_column("Language", style="magenta")
            table.add_column("Created", style="blue")
            
            for env in environments:
                table.add_row(
                    str(env.env_id)[:8],
                    env.name,
                    env.docker_image_ref[:40] + "..." if len(env.docker_image_ref) > 40 else env.docker_image_ref,
                    env.language_hint,
                    env.created_at.strftime("%Y-%m-%d %H:%M"),
                )
            
            console.print(table)
    
    asyncio.run(_list())


@app.command()
def env_add(
    name: str = typer.Argument(..., help="Environment name"),
    image: str = typer.Argument(..., help="Docker image reference"),
    language: str = typer.Option("unknown", "--language", "-l", help="Language hint"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Notes"),
):
    """Register a new environment."""
    from ssr_studio.database import async_session_factory, EnvironmentDB
    
    async def _add():
        async with async_session_factory() as db:
            env = EnvironmentDB(
                name=name,
                docker_image_ref=image,
                language_hint=language,
                notes=notes,
            )
            db.add(env)
            await db.commit()
            await db.refresh(env)
            
            console.print(f"[green]✓[/] Environment created: [cyan]{env.env_id}[/]")
    
    asyncio.run(_add())


@app.command()
def env_remove(
    env_id: str = typer.Argument(..., help="Environment ID"),
):
    """Remove an environment."""
    from ssr_studio.database import async_session_factory, EnvironmentDB
    from sqlalchemy import select
    
    async def _remove():
        async with async_session_factory() as db:
            result = await db.execute(
                select(EnvironmentDB).where(EnvironmentDB.env_id == UUID(env_id))
            )
            env = result.scalar_one_or_none()
            
            if not env:
                console.print(f"[red]Environment not found: {env_id}[/]")
                raise typer.Exit(1)
            
            await db.delete(env)
            await db.commit()
            
            console.print(f"[green]✓[/] Environment removed: [cyan]{env.name}[/]")
    
    asyncio.run(_remove())


# =============================================================================
# Episode Commands
# =============================================================================

@app.command()
def run(
    env_id: str = typer.Argument(..., help="Environment ID"),
    strategy: str = typer.Option("removal_only", "--strategy", "-s", help="Injection strategy"),
    attempts: int = typer.Option(4, "--attempts", "-a", help="Solver attempts per bug"),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait for completion"),
):
    """Run a self-play episode."""
    from ssr_studio.database import async_session_factory, EpisodeDB, EnvironmentDB
    from ssr_studio.models import EpisodeConfig, EpisodeStatus, InjectionStrategy
    from ssr_studio.orchestrator import EpisodeOrchestrator
    from sqlalchemy import select
    
    async def _run():
        async with async_session_factory() as db:
            # Verify environment
            result = await db.execute(
                select(EnvironmentDB).where(EnvironmentDB.env_id == UUID(env_id))
            )
            env = result.scalar_one_or_none()
            
            if not env:
                console.print(f"[red]Environment not found: {env_id}[/]")
                raise typer.Exit(1)
            
            # Create episode
            config = EpisodeConfig(
                injection_strategy=InjectionStrategy(strategy),
                solver_attempts=attempts,
            )
            
            episode = EpisodeDB(
                env_id=UUID(env_id),
                config=config.model_dump(),
                status=EpisodeStatus.PENDING.value,
            )
            db.add(episode)
            await db.commit()
            await db.refresh(episode)
            
            console.print(f"[green]✓[/] Episode created: [cyan]{episode.episode_id}[/]")
            
            if wait:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    task = progress.add_task("Running episode...", total=None)
                    
                    orchestrator = EpisodeOrchestrator(db)
                    await orchestrator.run_episode(episode.episode_id)
                    
                    await db.refresh(episode)
                    
                    progress.update(task, description=f"Status: {episode.status}")
                
                # Print results
                console.print()
                console.print(f"[bold]Episode Results[/]")
                console.print(f"  Status: [{'green' if episode.status == 'complete' else 'red'}]{episode.status}[/]")
                console.print(f"  Artifact Valid: {'✓' if episode.artifact_id else '✗'}")
                
                if episode.solve_rate is not None:
                    console.print(f"  Solve Rate: {episode.solve_rate:.1%}")
                if episode.r_inject is not None:
                    console.print(f"  Injector Reward: {episode.r_inject:.3f}")
                if episode.r_solve_avg is not None:
                    console.print(f"  Solver Reward (avg): {episode.r_solve_avg:.3f}")
    
    asyncio.run(_run())


@app.command()
def episodes(
    env_id: Optional[str] = typer.Option(None, "--env", "-e", help="Filter by environment"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of episodes to show"),
):
    """List episodes."""
    from ssr_studio.database import async_session_factory, EpisodeDB, EnvironmentDB
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    
    async def _list():
        async with async_session_factory() as db:
            query = select(EpisodeDB).options(selectinload(EpisodeDB.environment))
            
            if env_id:
                query = query.where(EpisodeDB.env_id == UUID(env_id))
            if status:
                query = query.where(EpisodeDB.status == status)
            
            query = query.order_by(EpisodeDB.created_at.desc()).limit(limit)
            
            result = await db.execute(query)
            episodes = result.scalars().all()
            
            if not episodes:
                console.print("[yellow]No episodes found[/]")
                return
            
            table = Table(title="Episodes")
            table.add_column("ID", style="dim")
            table.add_column("Environment", style="cyan")
            table.add_column("Status", style="green")
            table.add_column("Strategy", style="magenta")
            table.add_column("Solve Rate", style="blue")
            table.add_column("r_inject", style="yellow")
            table.add_column("Created", style="dim")
            
            for ep in episodes:
                config = ep.config or {}
                status_style = "green" if ep.status == "complete" else (
                    "red" if ep.status == "failed" else "yellow"
                )
                
                table.add_row(
                    str(ep.episode_id)[:8],
                    ep.environment.name if ep.environment else "-",
                    f"[{status_style}]{ep.status}[/]",
                    config.get("injection_strategy", "-")[:10],
                    f"{ep.solve_rate:.1%}" if ep.solve_rate is not None else "-",
                    f"{ep.r_inject:.2f}" if ep.r_inject is not None else "-",
                    ep.created_at.strftime("%Y-%m-%d %H:%M"),
                )
            
            console.print(table)
    
    asyncio.run(_list())


@app.command()
def show(
    episode_id: str = typer.Argument(..., help="Episode ID"),
):
    """Show episode details."""
    from ssr_studio.database import async_session_factory, EpisodeDB
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    
    async def _show():
        async with async_session_factory() as db:
            result = await db.execute(
                select(EpisodeDB)
                .options(
                    selectinload(EpisodeDB.environment),
                    selectinload(EpisodeDB.artifact),
                    selectinload(EpisodeDB.validation_report),
                    selectinload(EpisodeDB.solver_attempts),
                )
                .where(EpisodeDB.episode_id == UUID(episode_id))
            )
            episode = result.scalar_one_or_none()
            
            if not episode:
                console.print(f"[red]Episode not found: {episode_id}[/]")
                raise typer.Exit(1)
            
            console.print(f"\n[bold]Episode {episode.episode_id}[/]\n")
            
            # Basic info
            console.print(f"  Environment: [cyan]{episode.environment.name if episode.environment else '-'}[/]")
            console.print(f"  Status: [{_status_color(episode.status)}]{episode.status}[/]")
            console.print(f"  Created: {episode.created_at}")
            
            if episode.error_message:
                console.print(f"  Error: [red]{episode.error_message}[/]")
            
            # Configuration
            config = episode.config or {}
            console.print(f"\n[bold]Configuration[/]")
            console.print(f"  Strategy: {config.get('injection_strategy', '-')}")
            console.print(f"  Solver Attempts: {config.get('solver_attempts', 4)}")
            console.print(f"  Min Passing Tests: {config.get('min_passing_tests', 10)}")
            
            # Validation
            if episode.validation_report:
                vr = episode.validation_report
                console.print(f"\n[bold]Validation[/]")
                console.print(f"  Valid: {'[green]✓[/]' if vr.valid else '[red]✗[/]'}")
                
                for step in vr.steps:
                    icon = "✓" if step["passed"] else "✗"
                    color = "green" if step["passed"] else "red"
                    console.print(f"    [{color}]{icon}[/] {step['name']}")
                    if step.get("error_message"):
                        console.print(f"      [dim]{step['error_message']}[/]")
            
            # Solver attempts
            if episode.solver_attempts:
                console.print(f"\n[bold]Solver Attempts[/]")
                for attempt in episode.solver_attempts:
                    icon = "✓" if attempt.success else "✗"
                    color = "green" if attempt.success else "red"
                    console.print(f"  [{color}]{icon}[/] Attempt {attempt.attempt_number}")
                    console.print(f"      Steps: {attempt.total_tool_steps}, Tokens: {attempt.total_tokens_used}")
            
            # Rewards
            if episode.solve_rate is not None:
                console.print(f"\n[bold]Results[/]")
                console.print(f"  Solve Rate: {episode.solve_rate:.1%}")
                console.print(f"  r_inject: {episode.r_inject:.3f}")
                console.print(f"  r_solve (avg): {episode.r_solve_avg:.3f}")
    
    asyncio.run(_show())


# =============================================================================
# Metrics Commands
# =============================================================================

@app.command()
def metrics(
    env_id: Optional[str] = typer.Option(None, "--env", "-e", help="Filter by environment"),
):
    """Show aggregated metrics."""
    from ssr_studio.database import async_session_factory, EpisodeDB
    from sqlalchemy import select
    
    async def _metrics():
        async with async_session_factory() as db:
            query = select(EpisodeDB)
            if env_id:
                query = query.where(EpisodeDB.env_id == UUID(env_id))
            
            result = await db.execute(query)
            episodes = result.scalars().all()
            
            if not episodes:
                console.print("[yellow]No episodes found[/]")
                return
            
            # Compute metrics
            total = len(episodes)
            complete = sum(1 for e in episodes if e.status == "complete")
            failed = sum(1 for e in episodes if e.status == "failed")
            valid = sum(1 for e in episodes if e.artifact_id is not None)
            
            solve_rates = [e.solve_rate for e in episodes if e.solve_rate is not None]
            r_injects = [e.r_inject for e in episodes if e.r_inject is not None]
            r_solves = [e.r_solve_avg for e in episodes if e.r_solve_avg is not None]
            
            console.print("\n[bold]Metrics Summary[/]\n")
            
            # Episode counts
            console.print(f"  Total Episodes: {total}")
            console.print(f"  Complete: [green]{complete}[/]")
            console.print(f"  Failed: [red]{failed}[/]")
            console.print(f"  Pending: [yellow]{total - complete - failed}[/]")
            
            # Artifact validity
            console.print(f"\n  Valid Artifacts: {valid} ({valid/total:.1%})")
            
            # Solve rate
            if solve_rates:
                avg_solve = sum(solve_rates) / len(solve_rates)
                console.print(f"\n  Avg Solve Rate: {avg_solve:.1%}")
            
            # Rewards
            if r_injects:
                avg_r_inject = sum(r_injects) / len(r_injects)
                console.print(f"  Avg r_inject: {avg_r_inject:.3f}")
            
            if r_solves:
                avg_r_solve = sum(r_solves) / len(r_solves)
                console.print(f"  Avg r_solve: {avg_r_solve:.3f}")
    
    asyncio.run(_metrics())


# =============================================================================
# Database Commands
# =============================================================================

@app.command()
def init_db():
    """Initialize the database schema."""
    from ssr_studio.database import init_db as _init_db
    
    async def _init():
        await _init_db()
        console.print("[green]✓[/] Database initialized")
    
    asyncio.run(_init())


# =============================================================================
# Helpers
# =============================================================================

def _status_color(status: str) -> str:
    """Get color for status."""
    if status == "complete":
        return "green"
    elif status == "failed":
        return "red"
    elif status in ["injecting", "validating", "solving", "evaluating"]:
        return "yellow"
    else:
        return "dim"


if __name__ == "__main__":
    app()
