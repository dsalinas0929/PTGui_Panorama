# Tikee Pro 3 PTGui Panorama Pipeline

This repository supports production stitching of Enlaps Tikee Pro 3 dual-fisheye captures into equirectangular panoramas for 360 degree archive and timelapse workflows.

The project is structured around two primary deliverables:

1. Position-specific PTGui template development
2. Reliable batch processing of large image archives through the PTGui CLI

An optional downstream step is 360 timelapse assembly from the rendered equirectangular image sequence.

## Project Scope

This workflow is intended for long-term construction documentation captured from fixed camera positions.

For each camera position, the objective is to produce a calibrated PTGui template that delivers:

- correct fisheye mapping for the Tikee Pro 3 dual-lens system
- accurate horizon leveling and stable geometry
- clean straight-line rendering where expected
- dependable distortion correction and exposure blending
- equirectangular output suitable for 360 viewing and timelapse assembly

After template validation, the same setup is applied at scale to large archives of paired source images.

## Delivery Structure

### Part 1 - Template Development

Template development is based on sample LEFT/RIGHT image pairs captured:

- from each fixed camera position
- across different times of day
- under varying lighting conditions

The goal is not a single good-looking stitch, but a repeatable PTGui template that remains stable across the dataset.

In this repository, templates such as `WEST.pts` and `NORD.pts` represent position-specific PTGui project templates.

### Part 2 - Batch Processing Pipeline

The batch processor is implemented in `processor_nord.py & processor_west.py`.

It is responsible for:

- detecting complete `xxxxxx_LEFT.jpg` and `xxxxxx_RIGHT.jpg` pairs
- creating a PTGui project from a validated template
- assigning a consistent panorama output filename
- running PTGui stitching from the command line
- preserving generated `.pts` files for inspection and recovery

The current repository provides the core automation for a template-driven PTGui batch workflow.

### Optional - Timelapse Assembly

This repository currently stops at panorama generation.

If required, the stitched equirectangular image sequence can be used downstream for:

- FFmpeg-based timelapse assembly
- DaVinci Resolve finishing
- further color or editorial processing

## Current Repository Status

The current implementation is focused on a validated single-position workflow and is already suitable for controlled batch stitching.

Implemented now:

- template-based PTGui project creation
- automatic pairing of LEFT/RIGHT JPG files
- deterministic output naming as `xxxxxx.jpg`
- intermediate PTGui project generation in `generated_pts/`
- batch stitching through PTGui CLI
- `--dry-run`, `--prefix`, and `--overwrite` controls

Not yet implemented in the current script:

- persistent structured log files
- retry queues for failed stitches
- built-in parallel processing
- direct timelapse video assembly

Those items fit naturally as the next milestone once template stability is confirmed for all positions.

## Workflow

1. Validate a PTGui template per fixed camera position.
2. Place image pairs in a dataset folder using the naming format `xxxxxx_LEFT.jpg` and `xxxxxx_RIGHT.jpg`.
3. Run `processor_west.py` against that dataset and template.
4. Review rendered panoramas and any failed prefixes.
5. Repeat per camera position as needed.

## Folder Structure

```text
.
├── WEST.pts
├── NORD.pts
├── processor_west.py
├── processor_nord.py
├── dataset/
│   └── TEST__20230821_20241031_WEST/
│       ├── 000141_LEFT.jpg
│       ├── 000141_RIGHT.jpg
│       └── ...
├── generated_pts/
└── output/
```

## Requirements

- macOS with PTGui Pro installed
- PTGui executable available at `/Applications/PTGui.app/Contents/MacOS/PTGui`
- Python 3
- a validated PTGui template for the camera position being processed
- source images exported as JPG pairs named `xxxxxx_LEFT.jpg` and `xxxxxx_RIGHT.jpg`

If PTGui is installed in a different location, pass a custom path with `--ptgui-path`.

Note: the current automation expects JPEG inputs. If RAW files are part of the acquisition workflow, RAW development should happen upstream before batch stitching.

## Usage

Run the default WEST dataset with the default WEST template:

```bash
python3 processor_west.py (or processor_nord.py)
```

Preview the batch without creating projects or running PTGui:

```bash
python3 processor_west.py --dry-run
```

Process only selected frames:

```bash
python3 processor_west.py --prefix 000654 --prefix 000655
```

Overwrite panoramas that already exist:

```bash
python3 processor_west.py --overwrite
```

Process another camera position with a different template and folder layout:

```bash
python3 processor_west.py \
  --template path/to/POSITION.pts \
  --dataset-dir path/to/dataset_folder \
  --output-dir output/position_name \
  --projects-dir generated_pts/position_name
```

Use a custom PTGui executable:

```bash
python3 processor_west.py --ptgui-path "/Applications/PTGui.app/Contents/MacOS/PTGui"
```

## Command-Line Options

```text
--template       Template .pts file to apply
--dataset-dir    Source folder containing LEFT/RIGHT image pairs
--output-dir     Folder for final panorama JPG files
--projects-dir   Folder for generated intermediate PTGui project files
--ptgui-path     Path to the PTGui executable
--prefix         Limit processing to one prefix; repeat to include more
--overwrite      Replace existing output panoramas
--dry-run        Print planned actions without calling PTGui
```

## Output Conventions

For a source pair such as:

- `000654_LEFT.jpg`
- `000654_RIGHT.jpg`

the processor creates:

- `generated_pts/000654.pts`
- `output/000654.jpg`

This naming convention is intentionally simple and deterministic so the panoramas remain easy to sort, audit, and hand off for timelapse assembly.

## Operational Notes

- only complete LEFT/RIGHT pairs are processed
- non-matching filenames are ignored
- existing outputs are skipped unless `--overwrite` is used
- generated PTGui project files are retained for traceability
- the current execution model is sequential

For archives in the 5,000-20,000 pair range, a practical production approach is to first lock template quality, then add structured logging and controlled parallel execution once the baseline stitch quality is proven stable.

## Troubleshooting

If the script reports `Template not found`, verify the template path or pass `--template`.

If the script reports `Dataset folder not found`, verify the input folder or pass `--dataset-dir`.

If the script reports `PTGui executable not found`, confirm the PTGui installation path and pass `--ptgui-path`.

If nothing is processed, verify that the dataset contains complete pairs named exactly as `xxxxxx_LEFT.jpg` and `xxxxxx_RIGHT.jpg`.

If stitch quality is inconsistent, revisit the PTGui template first. For fixed-position construction timelapse work, template quality is the primary determinant of batch reliability.

## Implementation Notes

The automation logic lives in `processor_*.py` and uses the following PTGui CLI sequence:

```text
PTGui -createproject LEFT.jpg RIGHT.jpg -output project.pts -template TEMPLATE.pts
PTGui -stitchnogui project.pts
```

After project creation, the script patches each generated `.pts` file so the final panorama is written to the expected `output/xxxxxx.jpg` path.
