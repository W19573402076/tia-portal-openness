# tia-portal-openness

A Claude Code skill for automating Siemens TIA Portal (博图) projects through Openness and SimaticML.

## What it does

- Inspect projects, devices, blocks, and tags
- Create PLC tags, import/export blocks, compile, set titles/comments
- Generate LAD (梯形图) networks as SimaticML — Openness cannot author LAD directly
- Helpers for TON/CTU, compares, self-hold, FB calls, and instance DBs
- Guidelines for keeping generated LAD compact (fewer networks)

## Requirements

- Windows
- TIA Portal V15.1–V21 with the Openness option installed
- .NET Framework 4.8
- Python 3.8+

## Install

Copy this folder into `%USERPROFILE%\.claude\skills\` and restart the Claude Code session.

Build the helper executable once:

```bash
python scripts/build_tiatool.py
```

## Configuration

Defaults on the original machine target `E:\TIA_V21\coding\Portal V21`. Override with:

- `TIA_API_DIR` — Openness assemblies directory
- `TIA_PROJECT` — path to the `.ap2x` project
- `TIA_TOOL_LOG` — log file path

## Structure

- `SKILL.md` — main skill instructions
- `references/lad-instructions.md` — validated LAD part names, pins, templates, errors
- `references/openness-setup.md` — assembly resolution, locking, save behavior
- `references/workflow-examples.md` — generator, splicing, and shell examples
- `scripts/TiaTool.cs` — Openness command-line helper
- `scripts/ladlib.py` — SimaticML LAD builder
- `scripts/build_tiatool.py` — C# build script
