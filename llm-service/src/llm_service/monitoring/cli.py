"""
CLI interface for the monitoring agent.

Provides commands for starting, checking, and reporting.
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click

from .config import MonitoringAgentConfig, TeamsConfig, DatabaseConfig, MCPConfig
from .models import AlertSeverity, HealthStatus
from .storage import MetricsStorage
from .notifier import TeamsNotifier
from .orchestrator import MonitoringOrchestrator


def load_config(config_path: str) -> MonitoringAgentConfig:
    """Load configuration from JSON file."""
    path = Path(config_path)
    if not path.exists():
        raise click.ClickException(f"Config file not found: {config_path}")
    
    with open(path) as f:
        data = json.load(f)
    
    return MonitoringAgentConfig(**data)


def create_components(config: MonitoringAgentConfig):
    """Create storage, notifier, and orchestrator from config."""
    storage = MetricsStorage(config.database)
    
    notifier = None
    if config.teams and config.teams.webhook_url:
        notifier = TeamsNotifier(config.teams)
    
    orchestrator = MonitoringOrchestrator(config, storage, notifier)
    
    return storage, notifier, orchestrator


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Monitoring Agent CLI - Monitor infrastructure health."""
    pass


@cli.command()
@click.option(
    "-c", "--config",
    type=click.Path(exists=True),
    required=True,
    help="Path to configuration JSON file",
)
@click.option(
    "--once",
    is_flag=True,
    help="Run all checks once and exit",
)
def start(config: str, once: bool):
    """Start the monitoring agent."""
    click.echo(f"Loading configuration from {config}...")
    
    try:
        cfg = load_config(config)
    except Exception as e:
        raise click.ClickException(f"Failed to load config: {e}")
    
    click.echo(f"Configured {len(cfg.checks)} service checks")
    
    storage, notifier, orchestrator = create_components(cfg)
    
    async def run():
        if once:
            click.echo("Running all checks once...")
            results = await orchestrator.run_all_checks()
            
            for result in results:
                status_icon = {
                    HealthStatus.HEALTHY: "✅",
                    HealthStatus.WARNING: "⚠️",
                    HealthStatus.CRITICAL: "🔴",
                    HealthStatus.ERROR: "❌",
                    HealthStatus.UNKNOWN: "❓",
                }.get(result.status, "❓")
                
                click.echo(
                    f"  {status_icon} {result.check_name} ({result.service}): "
                    f"{result.status.value} - {len(result.metrics)} metrics"
                )
                
                for alert in result.alerts:
                    click.echo(f"    ⚠ Alert: {alert.title}")
            
            # Summary
            summary = await orchestrator.get_summary()
            click.echo(
                f"\nSummary: {summary.healthy_checks} healthy, "
                f"{summary.warning_checks} warning, "
                f"{summary.critical_checks} critical"
            )
        else:
            click.echo("Starting polling loop (Ctrl+C to stop)...")
            try:
                await orchestrator.start_polling()
            except KeyboardInterrupt:
                click.echo("\nStopping...")
                orchestrator.stop_polling()
    
    asyncio.run(run())


@cli.command()
@click.option(
    "-c", "--config",
    type=click.Path(exists=True),
    required=True,
    help="Path to configuration JSON file",
)
@click.argument("check_name")
def check(config: str, check_name: str):
    """Run a single service check by name."""
    cfg = load_config(config)
    
    # Find the check
    check_config = None
    for c in cfg.checks:
        if c.name == check_name:
            check_config = c
            break
    
    if not check_config:
        raise click.ClickException(
            f"Check '{check_name}' not found. "
            f"Available: {', '.join(c.name for c in cfg.checks)}"
        )
    
    storage, notifier, orchestrator = create_components(cfg)
    
    async def run():
        click.echo(f"Running check: {check_name}")
        result = await orchestrator.run_check(check_config)
        
        # Display result
        click.echo(f"\nStatus: {result.status.value}")
        click.echo(f"Duration: {result.duration_seconds:.2f}s")
        
        if result.metrics:
            click.echo("\nMetrics:")
            for metric in result.metrics:
                click.echo(
                    f"  - {metric.metric_name}: {metric.value:.2f}"
                    f"{metric.unit or ''} ({metric.status.value})"
                )
        
        if result.alerts:
            click.echo("\nAlerts:")
            for alert in result.alerts:
                click.echo(f"  - [{alert.severity.value}] {alert.title}")
                click.echo(f"    {alert.message}")
        
        if result.health_check.error:
            click.echo(f"\nError: {result.health_check.error}")
    
    asyncio.run(run())


@cli.command()
@click.option(
    "-c", "--config",
    type=click.Path(exists=True),
    required=True,
    help="Path to configuration JSON file",
)
@click.option(
    "--hours",
    default=24,
    help="Hours to include in report (default: 24)",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Output as JSON",
)
def report(config: str, hours: int, as_json: bool):
    """Generate a monitoring report."""
    cfg = load_config(config)
    storage, _, _ = create_components(cfg)
    
    summary = storage.get_summary(hours=hours)
    
    if as_json:
        click.echo(summary.model_dump_json(indent=2))
    else:
        click.echo("=" * 50)
        click.echo(f"Monitoring Report ({hours}h)")
        click.echo("=" * 50)
        
        status_icon = {
            HealthStatus.HEALTHY: "✅",
            HealthStatus.WARNING: "⚠️",
            HealthStatus.CRITICAL: "🔴",
            HealthStatus.ERROR: "❌",
            HealthStatus.UNKNOWN: "❓",
        }.get(summary.overall_status, "❓")
        
        click.echo(f"\nOverall Status: {status_icon} {summary.overall_status.value}")
        click.echo(f"\nChecks:")
        click.echo(f"  Total: {summary.total_checks}")
        click.echo(f"  Healthy: {summary.healthy_checks}")
        click.echo(f"  Warning: {summary.warning_checks}")
        click.echo(f"  Critical: {summary.critical_checks}")
        click.echo(f"  Error: {summary.error_checks}")
        
        click.echo(f"\nAlerts:")
        click.echo(f"  Active: {summary.active_alerts}")
        click.echo(f"  Unacknowledged: {summary.unacknowledged_alerts}")
        
        if summary.service_status:
            click.echo(f"\nService Status:")
            for service, status in summary.service_status.items():
                icon = status_icon if status == summary.overall_status else {
                    HealthStatus.HEALTHY: "✅",
                    HealthStatus.WARNING: "⚠️",
                    HealthStatus.CRITICAL: "🔴",
                }.get(status, "❓")
                click.echo(f"  {icon} {service}: {status.value}")


@cli.command()
@click.option(
    "-c", "--config",
    type=click.Path(exists=True),
    required=True,
    help="Path to configuration JSON file",
)
@click.option(
    "--active",
    is_flag=True,
    help="Show only active alerts",
)
@click.option(
    "--severity",
    type=click.Choice(["info", "warning", "critical"]),
    help="Filter by severity",
)
def alerts(config: str, active: bool, severity: Optional[str]):
    """List alerts."""
    cfg = load_config(config)
    storage, _, _ = create_components(cfg)
    
    severity_filter = AlertSeverity(severity) if severity else None
    
    alert_list = storage.get_alerts(
        is_active=True if active else None,
        severity=severity_filter,
        limit=50,
    )
    
    if not alert_list:
        click.echo("No alerts found.")
        return
    
    click.echo(f"Found {len(alert_list)} alerts:\n")
    
    for alert in alert_list:
        severity_icon = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.CRITICAL: "🔴",
        }.get(alert.severity, "❓")
        
        status = "🔔 Active" if alert.is_active else "✅ Resolved"
        ack = "📬 Ack'd" if alert.acknowledged else "📭 Unack'd"
        
        click.echo(f"[{alert.id}] {severity_icon} {alert.title}")
        click.echo(f"    Service: {alert.service} | Check: {alert.check_name}")
        click.echo(f"    Status: {status} | {ack}")
        click.echo(f"    Value: {alert.current_value:.2f} (threshold: {alert.threshold_value:.2f})")
        click.echo(f"    Created: {alert.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        click.echo()


@cli.command()
@click.option(
    "-c", "--config",
    type=click.Path(exists=True),
    required=True,
    help="Path to configuration JSON file",
)
@click.argument("alert_id", type=int)
@click.option(
    "--by",
    default="cli-user",
    help="Who is acknowledging (default: cli-user)",
)
def ack(config: str, alert_id: int, by: str):
    """Acknowledge an alert."""
    cfg = load_config(config)
    storage, _, _ = create_components(cfg)
    
    storage.acknowledge_alert(alert_id, acknowledged_by=by)
    click.echo(f"Alert {alert_id} acknowledged by {by}")


@cli.command()
@click.option(
    "-c", "--config",
    type=click.Path(exists=True),
    required=True,
    help="Path to configuration JSON file",
)
@click.argument("alert_id", type=int)
def resolve(config: str, alert_id: int):
    """Manually resolve an alert."""
    cfg = load_config(config)
    storage, _, _ = create_components(cfg)
    
    storage.resolve_alert(alert_id)
    click.echo(f"Alert {alert_id} resolved")


@cli.command()
@click.option(
    "-c", "--config",
    type=click.Path(exists=True),
    required=True,
    help="Path to configuration JSON file",
)
def cleanup(config: str):
    """Clean up old data based on retention policy."""
    cfg = load_config(config)
    storage, _, _ = create_components(cfg)
    
    click.echo(f"Cleaning up data older than {cfg.database.retention_days} days...")
    
    deleted = storage.cleanup_old_data()
    
    click.echo(f"Deleted:")
    click.echo(f"  - {deleted['metrics']} metrics")
    click.echo(f"  - {deleted['health_checks']} health checks")
    click.echo(f"  - {deleted['alerts']} resolved alerts")
    
    click.echo("Running VACUUM...")
    storage.vacuum()
    click.echo("Done!")


@cli.command()
@click.option(
    "-c", "--config",
    type=click.Path(exists=True),
    required=True,
    help="Path to configuration JSON file",
)
def test_teams(config: str):
    """Test Teams webhook connection."""
    cfg = load_config(config)
    
    if not cfg.teams or not cfg.teams.webhook_url:
        raise click.ClickException("Teams webhook not configured")
    
    notifier = TeamsNotifier(cfg.teams)
    
    async def run():
        click.echo("Sending test message to Teams...")
        success = await notifier.test_connection()
        
        if success:
            click.echo("✅ Test message sent successfully!")
        else:
            click.echo("❌ Failed to send test message")
    
    asyncio.run(run())


@cli.command()
@click.option(
    "-o", "--output",
    type=click.Path(),
    default="monitoring-config.json",
    help="Output path for sample config",
)
def init(output: str):
    """Generate a sample configuration file."""
    from .config import SAMPLE_CONFIG
    
    path = Path(output)
    
    if path.exists():
        if not click.confirm(f"{output} already exists. Overwrite?"):
            return
    
    with open(path, "w") as f:
        json.dump(SAMPLE_CONFIG, f, indent=2)
    
    click.echo(f"Sample configuration written to {output}")
    click.echo("Edit this file to configure your monitoring checks.")


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
