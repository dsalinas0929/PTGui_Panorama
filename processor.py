#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = SCRIPT_DIR / "WEST.pts"
DEFAULT_DATASET_DIR = SCRIPT_DIR / "dataset" / "TEST__20230821_20241031_WEST"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"
DEFAULT_PROJECTS_DIR = SCRIPT_DIR / "generated_pts"
DEFAULT_PTGUI_PATH = Path("/Applications/PTGui.app/Contents/MacOS/PTGui")
PAIR_PATTERN = re.compile(r"(?P<prefix>.+)_(?P<side>LEFT|RIGHT)\.jpg$", re.IGNORECASE)



@dataclass(frozen=True)
class ImagePair:
    prefix: str
    left: Path
    right: Path


def format_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(SCRIPT_DIR))
    except ValueError:
        return str(path.resolve())


def print_divider() -> None:
    print("-" * 72)


def format_duration(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    minutes, secs = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def build_progress_bar(done: int, total: int, width: int = 28) -> str:
    if total <= 0:
        total = 1
    ratio = min(max(done / total, 0), 1)
    filled = int(round(width * ratio))
    return f"[{'#' * filled}{'-' * (width - filled)}]"


def build_activity_bar(tick: int, width: int = 20) -> str:
    if width < 3:
        width = 3

    chars = ["-"] * width
    position = tick % width
    chars[position] = ">"
    return f"[{''.join(chars)}]"


def print_batch_progress(done: int, total: int) -> None:
    percent = int((done / total) * 100) if total else 100
    print(f"Overall progress: {build_progress_bar(done, total)} {done}/{total} ({percent}%)")


def print_intro(
    *,
    template_path: Path,
    dataset_dir: Path,
    output_dir: Path,
    pairs: list[ImagePair],
    dry_run: bool,
    overwrite: bool,
) -> None:
    print_divider()
    print("(^_^) Panorama processing started")
    print_divider()
    print("Batch overview:")
    print(f"  Template      : {format_path(template_path)}")
    print(f"  Source folder : {format_path(dataset_dir)}")
    print(f"  Save folder   : {format_path(output_dir)}")
    print(f"  Photo sets    : {len(pairs)} ready")
    if dry_run:
        print("  Run mode      : Preview only - nothing will be created")
    elif overwrite:
        print("  Run mode      : Replace panoramas if they already exist")
    else:
        print("  Run mode      : Keep existing panoramas and skip finished ones")
    print()
    print("What will happen for each photo set:")
    print("  1. Prepare the PTGui stitch settings")
    print("  2. Set the final panorama filename")
    print("  3. Render the final panorama image")
    print_divider()
    print_batch_progress(0, len(pairs))
    print_divider()


def print_pair_header(index: int, total: int, pair: ImagePair, output_path: Path) -> None:
    print()
    print(f"Photo set {index} of {total}")
    print(f"  ID             : {pair.prefix}")
    print(f"  LEFT image     : {pair.left.name}")
    print(f"  RIGHT image    : {pair.right.name}")
    print(f"  Panorama file  : {format_path(output_path)}")


def extract_error_text(stdout: str | None, stderr: str | None) -> str:
    for stream in (stderr, stdout):
        if not stream:
            continue
        cleaned = stream.replace("\r", "\n")
        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        if lines:
            return lines[-1]
    return ""


def print_summary(
    *,
    processed: int,
    skipped: int,
    failed: list[str],
    dry_run: bool,
    output_dir: Path,
) -> None:
    print()
    print_divider()
    if failed:
        print("(x_x) Batch finished with a few items to review")
    elif dry_run:
        print("(^_^) Preview finished")
    else:
        print("***** All done *****")
    print_divider()
    processed_label = "Would make" if dry_run else "Created"
    print("Summary:")
    print(f"  {processed_label:<12}: {processed}")
    print(f"  {'Skipped':<12}: {skipped}")
    print(f"  {'Need review':<12}: {len(failed)}")
    print(f"  {'Save folder':<12}: {format_path(output_dir)}")
    if failed:
        print(f"  {'Check IDs':<12}: {', '.join(failed)}")
    print_divider()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create PTGui projects from LEFT/RIGHT image pairs using WEST.pts as a template, "
            "then stitch panoramas into the output folder."
        )
    )
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE, help="Template .pts file.")
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=DEFAULT_DATASET_DIR,
        help="Folder containing xxxxxx_LEFT.jpg and xxxxxx_RIGHT.jpg files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Folder where stitched panoramas will be written as xxxxxx.jpg.",
    )
    parser.add_argument(
        "--projects-dir",
        type=Path,
        default=DEFAULT_PROJECTS_DIR,
        help="Folder where generated PTGui project files will be stored.",
    )
    parser.add_argument(
        "--ptgui-path",
        type=Path,
        default=DEFAULT_PTGUI_PATH,
        help="Path to the PTGui executable.",
    )
    parser.add_argument(
        "--prefix",
        action="append",
        default=[],
        help="Only process the given prefix. Repeat the flag to process multiple prefixes.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite panoramas that already exist in the output folder.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the work that would be done without calling PTGui or writing files.",
    )
    return parser.parse_args()


def resolve_path(path: Path) -> Path:
    return path.expanduser().resolve()


def validate_inputs(template: Path, dataset_dir: Path, ptgui_path: Path) -> None:
    if not template.is_file():
        raise FileNotFoundError(f"Template not found: {template}")
    if not dataset_dir.is_dir():
        raise FileNotFoundError(f"Dataset folder not found: {dataset_dir}")
    if not ptgui_path.is_file():
        raise FileNotFoundError(f"PTGui executable not found: {ptgui_path}")


def discover_pairs(dataset_dir: Path) -> list[ImagePair]:
    grouped: dict[str, dict[str, Path]] = {}

    for image_path in sorted(dataset_dir.iterdir()):
        if not image_path.is_file():
            continue

        match = PAIR_PATTERN.fullmatch(image_path.name)
        if not match:
            continue

        prefix = match.group("prefix")
        side = match.group("side").upper()
        grouped.setdefault(prefix, {})[side] = image_path.resolve()

    pairs: list[ImagePair] = []
    for prefix in sorted(grouped):
        sides = grouped[prefix]
        if "LEFT" not in sides or "RIGHT" not in sides:
            continue
        pairs.append(ImagePair(prefix=prefix, left=sides["LEFT"], right=sides["RIGHT"]))

    return pairs


def run_command(command: list[str], dry_run: bool, step_name: str) -> None:
    print(f"  {step_name}")
    if dry_run:
        print("    Preview only: this step is ready")
        return

    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stdout_file, tempfile.TemporaryFile(
        mode="w+t", encoding="utf-8"
    ) as stderr_file:
        process = subprocess.Popen(
            command,
            stdout=stdout_file,
            stderr=stderr_file,
        )

        start_time = time.time()
        tick = 0
        next_log_at = 10

        while process.poll() is None:
            elapsed = time.time() - start_time
            if sys.stdout.isatty():
                sys.stdout.write(
                    f"\r    {build_activity_bar(tick)} Working... {format_duration(elapsed)}"
                )
                sys.stdout.flush()
                tick += 1
            elif elapsed >= next_log_at:
                print(f"    Still working... {format_duration(elapsed)}")
                next_log_at += 10
            time.sleep(0.5)

        elapsed = time.time() - start_time
        if sys.stdout.isatty():
            sys.stdout.write("\r" + " " * 72 + "\r")
            sys.stdout.flush()

        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout_text = stdout_file.read()
        stderr_text = stderr_file.read()
        return_code = process.returncode

    if return_code != 0:
        detail = extract_error_text(stdout_text, stderr_text)
        if detail:
            raise RuntimeError(f"{step_name} failed: {detail}")
        raise RuntimeError(f"{step_name} failed with exit code {return_code}")

    print(f"    {build_progress_bar(1, 1, width=20)} Done in {format_duration(elapsed)}")


def create_project(
    ptgui_path: Path,
    template_path: Path,
    pair: ImagePair,
    project_path: Path,
    dry_run: bool,
) -> None:
    run_command(
        [
            str(ptgui_path),
            "-createproject",
            str(pair.left),
            str(pair.right),
            "-output",
            str(project_path),
            "-template",
            str(template_path),
        ],
        dry_run=dry_run,
        step_name="1/3  Preparing the PTGui stitch file...",
    )


def set_project_output(project_path: Path, output_path: Path) -> None:
    with project_path.open("r", encoding="utf-8") as handle:
        project = json.load(handle)

    # PTGui's -createproject leaves the stitched panorama filename empty.
    project["project"]["panoramaparams"]["outputfile"] = str(output_path)

    with project_path.open("w", encoding="utf-8") as handle:
        json.dump(project, handle, indent=2)
        handle.write("\n")


def stitch_project(ptgui_path: Path, project_path: Path, dry_run: bool) -> None:
    run_command(
        [str(ptgui_path), "-stitchnogui", str(project_path)],
        dry_run=dry_run,
        step_name="3/3  Rendering the panorama image... this may take a little while",
    )


def main() -> int:
    args = parse_args()

    template_path = resolve_path(args.template)
    dataset_dir = resolve_path(args.dataset_dir)
    output_dir = resolve_path(args.output_dir)
    projects_dir = resolve_path(args.projects_dir)
    ptgui_path = resolve_path(args.ptgui_path)
    requested_prefixes = set(args.prefix)

    try:
        validate_inputs(template_path, dataset_dir, ptgui_path)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    pairs = discover_pairs(dataset_dir)
    if requested_prefixes:
        pairs = [pair for pair in pairs if pair.prefix in requested_prefixes]

    if not pairs:
        print("No complete LEFT/RIGHT image pairs found.", file=sys.stderr)
        return 1

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        projects_dir.mkdir(parents=True, exist_ok=True)

    print_intro(
        template_path=template_path,
        dataset_dir=dataset_dir,
        output_dir=output_dir,
        pairs=pairs,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
    )

    created = 0
    skipped = 0
    failed: list[str] = []
    total_pairs = len(pairs)

    for index, pair in enumerate(pairs, start=1):
        output_path = output_dir / f"{pair.prefix}.jpg"
        project_path = projects_dir / f"{pair.prefix}.pts"

        print_pair_header(index, len(pairs), pair, output_path)

        if output_path.exists() and not args.overwrite:
            print("  (-_-) Already finished earlier, so this one will be skipped.")
            skipped += 1
            print_batch_progress(created + skipped + len(failed), total_pairs)
            continue

        try:
            create_project(ptgui_path, template_path, pair, project_path, dry_run=args.dry_run)

            if args.dry_run:
                print(f"  2/3  Preview only: the panorama would be named {output_path.name}")
            else:
                print(f"  2/3  Naming the panorama file as {output_path.name}")
                set_project_output(project_path, output_path)

            stitch_project(ptgui_path, project_path, dry_run=args.dry_run)
            created += 1
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            failed.append(pair.prefix)
            print("  (x_x) This photo set needs attention.", file=sys.stderr)
            print(f"        Reason: {exc}", file=sys.stderr)
        else:
            if args.dry_run:
                print("  (^_^) Preview looks good for this photo set")
            else:
                print(f"  \\(^_^)/ Finished successfully - saved as {output_path.name}")

        print_batch_progress(created + skipped + len(failed), total_pairs)

    print_summary(
        processed=created,
        skipped=skipped,
        failed=failed,
        dry_run=args.dry_run,
        output_dir=output_dir,
    )
    if failed:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
