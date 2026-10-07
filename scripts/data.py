#!/usr/bin/env python

"""Unified CLI for managing data assets stored in GitHub Releases.

Subcommands:
    check    - Compare local data against the latest release checksums.
    fetch    - Download and extract data assets from the latest release.
    compress - Create .tar.gz archives and checksums for local data.
    publish  - Create a new GitHub release with compressed archives.

Usage:
    python data.py check
    python data.py fetch [ASSETS...]
    python data.py compress
    python data.py publish
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tarfile
import tempfile
import tomllib
from pathlib import Path
from typing import TypedDict

import rich_click as click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

click.rich_click.USE_RICH_MARKUP = True
click.rich_click.USE_MARKDOWN = False
click.rich_click.SHOW_ARGUMENTS = True
click.rich_click.GROUP_ARGUMENTS_OPTIONS = True
click.rich_click.STYLE_COMMANDS_TABLE_COLUMN_WIDTH_RATIO = (1, 2)
click.rich_click.STYLE_ERRORS_SUGGESTION = "dim"
click.rich_click.ERRORS_SUGGESTION = (
    "Try running '[bold]data.py --help[/]' for available commands."
)
click.rich_click.COMMAND_GROUPS = {
    "data.py": [
        {
            "name": "Workflow Commands",
            "commands": ["check", "fetch", "compress", "publish"],
        },
    ],
}


MANIFEST_NAME: str = "manifest.json"
CHECKSUMS_NAME: str = "checksums.json"

console = Console()
err_console = Console(stderr=True)


class Manifest(TypedDict):
    repo: str
    assets: dict[str, str]


def find_project_root() -> Path:
    """Walk up from CWD to find the directory containing manifest.json."""
    current = Path(__file__).resolve()
    for directory in [current, *current.parents]:
        if (directory / MANIFEST_NAME).exists():
            return directory
    err_console.print(
        f"[bold red]Error:[/] Could not find [cyan]{MANIFEST_NAME}[/] "
        "in any parent directory."
    )
    raise SystemExit(1)


def load_manifest() -> Manifest:
    """Load and validate manifest.json from the project root."""
    root = find_project_root()
    manifest_path = root / MANIFEST_NAME
    with open(manifest_path, "r") as f:
        config = json.load(f)

    for key in ("repo", "assets"):
        if key not in config:
            err_console.print(
                f"[bold red]Error:[/] {MANIFEST_NAME} is missing required "
                f"key [cyan]'{key}'[/]."
            )
            raise SystemExit(1)

    return config


def calculate_md5(target_path: Path) -> str | None:
    """Return the MD5 hex-digest for a file or directory, or None if missing.

    For directories the hash is deterministic: file relative paths and their
    contents are both fed into the hasher so that renames are detected.
    """
    if not target_path.exists():
        return None

    hasher = hashlib.md5()

    if target_path.is_file():
        _hash_file(target_path, hasher)
    elif target_path.is_dir():
        for file_path in sorted(target_path.rglob("*")):
            if file_path.is_file():
                rel = file_path.relative_to(target_path)
                hasher.update(str(rel).encode())
                _hash_file(file_path, hasher)

    return hasher.hexdigest()


def _hash_file(file_path: Path, hasher: hashlib._Hash) -> None:
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)


def get_project_version() -> str:
    """Read the workspace version from pixi.toml."""
    root = find_project_root()
    pixi_path = root / "pixi.toml"
    if not pixi_path.exists():
        err_console.print(
            "[bold red]Error:[/] [cyan]pixi.toml[/] not found in the project root."
        )
        raise SystemExit(1)

    with open(pixi_path, "rb") as f:
        return tomllib.load(f)["workspace"]["version"]


def truncated_hash(h: str | None) -> str:
    """Truncate a hex digest for display, or return a dash if None."""
    return h[:12] + "..." if h else "—"


def warn_empty_assets() -> None:
    console.print("[yellow]No assets defined in manifest.json — nothing to do.[/]")


@click.group()
def cli():
    """
    Manage data assets stored in GitHub Releases.

    This tool provides a complete workflow for versioning and distributing
    data files via GitHub Releases. Assets are defined in [cyan]manifest.json[/].

    \b
    Typical workflow:
      1. [bold]check[/]    → See if local data differs from the latest release
      2. [bold]compress[/] → Archive assets and generate checksums
      3. [bold]publish[/]  → Push a new GitHub release
      4. [bold]fetch[/]    → Pull assets on another machine
    """


@cli.command()
def check():
    """Compare local data against the latest release checksums.

    Downloads [cyan]checksums.json[/] from the most recent GitHub release and
    compares each asset's MD5 against the local copy. Exits with code 1 if
    any differences are found.
    """
    config = load_manifest()
    repo = config["repo"]
    assets = config["assets"]

    if not assets:
        warn_empty_assets()
        return

    with console.status("Fetching latest checksums from GitHub..."):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            try:
                subprocess.run(
                    [
                        "gh",
                        "release",
                        "download",
                        "--repo",
                        repo,
                        "--pattern",
                        CHECKSUMS_NAME,
                        "--dir",
                        str(tmp_path),
                        "--clobber",
                    ],
                    check=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError:
                err_console.print(
                    "[bold red]Error:[/] No previous release found or unable "
                    "to download checksums."
                )
                raise SystemExit(1)

            with open(tmp_path / CHECKSUMS_NAME, "r") as f:
                remote_checksums = json.load(f)

    # Build comparison table.
    table = Table(title="Data Integrity Check", show_lines=False)
    table.add_column("Status", justify="center", width=10)
    table.add_column("Asset", style="cyan")
    table.add_column("Target Path", style="dim")
    table.add_column("Local Hash", style="dim", max_width=16, no_wrap=True)
    table.add_column("Remote Hash", style="dim", max_width=16, no_wrap=True)

    differences = False

    for archive_name, target_path_str in assets.items():
        target_path = Path(target_path_str)
        local_hash = calculate_md5(target_path)
        remote_hash = remote_checksums.get(target_path_str)

        if local_hash is None:
            status = Text("MISSING", style="bold red")
            differences = True
        elif local_hash != remote_hash:
            status = Text("CHANGED", style="bold yellow")
            differences = True
        else:
            status = Text("MATCH", style="bold green")

        table.add_row(
            status,
            archive_name,
            target_path_str,
            truncated_hash(local_hash),
            truncated_hash(remote_hash),
        )

    console.print()
    console.print(table)
    console.print()

    if differences:
        console.print(
            Panel(
                "[yellow]Changes detected — you should cut a new release soon.[/]",
                border_style="yellow",
            )
        )
        raise SystemExit(1)
    else:
        console.print(
            Panel(
                "[green]Local data matches the latest release. No action needed.[/]",
                border_style="green",
            )
        )


@cli.command()
@click.argument("assets", nargs=-1)
@click.option(
    "--verify/--no-verify",
    default=True,
    help="Verify checksums after extraction (default: enabled).",
)
def fetch(assets: tuple[str, ...], verify: bool):
    """Download and extract data assets from the latest release.

    Pass one or more [bold]ASSETS[/] names to fetch selectively, or omit to
    fetch all assets defined in [cyan]manifest.json[/]. Archives are extracted
    in place and then removed.
    """
    config = load_manifest()
    repo = config["repo"]
    manifest_assets: dict[str, str] = config["assets"]
    available = list(manifest_assets.keys())

    if not available:
        warn_empty_assets()
        return

    targets = list(assets) if assets else available

    # Download remote checksums for post-fetch verification.
    remote_checksums: dict[str, str] = {}
    if verify:
        with console.status("Downloading checksums for verification..."):
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                try:
                    subprocess.run(
                        [
                            "gh",
                            "release",
                            "download",
                            "--repo",
                            repo,
                            "--pattern",
                            CHECKSUMS_NAME,
                            "--dir",
                            str(tmp_path),
                            "--clobber",
                        ],
                        check=True,
                        capture_output=True,
                    )
                    with open(tmp_path / CHECKSUMS_NAME, "r") as f:
                        remote_checksums = json.load(f)
                except (subprocess.CalledProcessError, FileNotFoundError):
                    console.print(
                        "[yellow]Warning:[/] Could not download checksums — "
                        "skipping verification."
                    )
                    verify = False

    # Results table built incrementally.
    table = Table(title="Fetch Results", show_lines=False)
    table.add_column("Asset", style="cyan")
    table.add_column("Target", style="dim")
    table.add_column("Download", justify="center")
    table.add_column("Extract", justify="center")
    table.add_column("Verify", justify="center")

    for archive_name in targets:
        if archive_name not in available:
            console.print(
                f"[yellow]Warning:[/] [cyan]{archive_name}[/] is not in the "
                "manifest. Skipping."
            )
            continue

        target_path_str = manifest_assets[archive_name]
        target_path = Path(target_path_str)
        extract_dir = target_path.parent
        extract_dir.mkdir(parents=True, exist_ok=True)
        archive_path = extract_dir / archive_name

        # Download
        dl_ok = True
        with console.status(f"Downloading [cyan]{archive_name}[/] ..."):
            try:
                subprocess.run(
                    [
                        "gh",
                        "release",
                        "download",
                        "--repo",
                        repo,
                        "--pattern",
                        archive_name,
                        "--dir",
                        str(extract_dir),
                        "--clobber",
                    ],
                    check=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError:
                dl_ok = False

        # Extract
        ext_ok = True
        if dl_ok:
            with console.status(f"Extracting [cyan]{archive_name}[/] ..."):
                try:
                    with tarfile.open(archive_path, "r:gz") as tar:
                        tar.extractall(path=extract_dir)
                    archive_path.unlink()
                except Exception:
                    ext_ok = False

        # Verify
        verify_display = Text("—", style="dim")
        if dl_ok and ext_ok and verify and target_path_str in remote_checksums:
            expected = remote_checksums[target_path_str]
            actual = calculate_md5(target_path)
            if actual == expected:
                verify_display = Text("✓", style="bold green")
            else:
                verify_display = Text("✗ mismatch", style="bold red")
                # Add the row before exiting so the table still renders.
                table.add_row(
                    archive_name,
                    target_path_str,
                    Text("✓", style="bold green"),
                    Text("✓", style="bold green"),
                    verify_display,
                )
                console.print()
                console.print(table)
                console.print()
                err_console.print(
                    f"[bold red]Error:[/] Checksum mismatch for "
                    f"[cyan]{target_path_str}[/].\n"
                    f"  Expected: [dim]{expected}[/]\n"
                    f"  Got:      [dim]{actual}[/]"
                )
                raise SystemExit(1)
        elif dl_ok and ext_ok and verify:
            verify_display = Text("skip", style="dim")

        table.add_row(
            archive_name,
            target_path_str,
            Text("✓", style="bold green") if dl_ok else Text("✗", style="bold red"),
            Text("✓", style="bold green") if ext_ok else Text("✗", style="bold red"),
            verify_display,
        )

    console.print()
    console.print(table)
    console.print()
    console.print(Panel("[bold green]Data fetch complete.[/]", border_style="green"))


@cli.command()
def compress():
    """Create [cyan].tar.gz[/] archives and a checksums file for each asset.

    Reads assets from [cyan]manifest.json[/], computes MD5 checksums, and
    writes compressed archives alongside the original targets. A
    [cyan]checksums.json[/] file is saved to the project root.
    """
    config = load_manifest()
    assets = config["assets"]

    if not assets:
        warn_empty_assets()
        return

    root = find_project_root()
    checksums_path = root / CHECKSUMS_NAME

    table = Table(title="Compression Results", show_lines=False)
    table.add_column("Asset", style="cyan")
    table.add_column("Target", style="dim")
    table.add_column("Archive", style="dim")
    table.add_column("MD5", style="dim", max_width=16, no_wrap=True)
    table.add_column("Status", justify="center")

    checksums: dict[str, str] = {}

    for archive_name, target_path_str in assets.items():
        target_path = Path(target_path_str)

        if not target_path.exists():
            err_console.print(
                f"[bold red]Error:[/] Target [cyan]{target_path}[/] does not exist."
            )
            raise SystemExit(1)

        with console.status(f"Compressing [cyan]{archive_name}[/] ..."):
            md5 = calculate_md5(target_path)
            if md5:
                checksums[target_path_str] = md5

            archive_path = target_path.parent / archive_name
            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(target_path, arcname=target_path.name)

        table.add_row(
            archive_name,
            target_path_str,
            str(archive_path),
            truncated_hash(md5),
            Text("✓", style="bold green"),
        )

    with open(checksums_path, "w") as f:
        json.dump(checksums, f, indent=2)

    console.print()
    console.print(table)
    console.print()
    console.print(
        Panel(
            f"[bold green]Compression complete.[/] "
            f"Checksums written to [cyan]{checksums_path}[/].",
            border_style="green",
        )
    )


@cli.command()
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be published without actually creating a release.",
)
def publish(dry_run: bool):
    """Create a new GitHub release with compressed archives.

    Reads the version from [cyan]pixi.toml[/], tags the release as
    [bold]vX.Y.Z[/], and uploads all archives plus [cyan]checksums.json[/].
    Run [bold]compress[/] first to generate the required files.
    """
    config = load_manifest()
    repo = config["repo"]
    assets = config["assets"]
    root = find_project_root()

    version = get_project_version()
    tag = f"v{version}"

    checksums_path = root / CHECKSUMS_NAME
    files_to_upload: list[Path] = [checksums_path]
    for archive_name, target_path_str in assets.items():
        archive_path = Path(target_path_str).parent / archive_name
        files_to_upload.append(archive_path)

    # Build the file listing table.
    title_suffix = " [cyan](dry run)[/]" if dry_run else ""
    table = Table(title=f"Release [bold]{tag}[/]{title_suffix}", show_lines=False)
    table.add_column("File", style="cyan")
    table.add_column("Exists", justify="center")
    table.add_column("Size", justify="right", style="dim")

    missing = []
    for f in files_to_upload:
        exists = f.exists()
        if not exists:
            missing.append(f)
        size = f"{f.stat().st_size / 1024:.1f} KB" if exists else "—"
        table.add_row(
            str(f),
            Text("✓", style="bold green") if exists else Text("✗", style="bold red"),
            size,
        )

    console.print()
    console.print(table)
    console.print()

    if missing:
        err_console.print(
            "[bold red]Error:[/] Some expected files are missing. "
            "Did you run [cyan]data.py compress[/] first?"
        )
        raise SystemExit(1)

    if dry_run:
        console.print(
            Panel(
                f"[cyan]Dry run complete.[/] Would create release "
                f"[bold]{tag}[/] on [dim]{repo}[/].",
                border_style="cyan",
            )
        )
        return

    with console.status(f"Creating GitHub release [bold]{tag}[/] ..."):
        gh_command = (
            ["gh", "release", "create", tag]
            + [str(f) for f in files_to_upload]
            + [
                "--repo",
                repo,
                "--title",
                tag,
                "--notes",
                f"Automated release for version {version}.",
            ]
        )
        subprocess.run(gh_command, check=True)

    console.print("Cleaning up local archives...")
    for f in files_to_upload:
        f.unlink()

    console.print()
    console.print(
        Panel(
            f"[bold green]Successfully published {tag}[/] to [dim]{repo}[/].",
            border_style="green",
        )
    )


if __name__ == "__main__":
    cli()
