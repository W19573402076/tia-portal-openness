---
name: tia-portal-openness
description: Automate Siemens TIA Portal (博图) projects with Openness and SimaticML — inspect projects, create PLC tags, generate or modify LAD (梯形图) program blocks, import blocks, compile, and export for verification. Use this skill whenever the user mentions 博图 / TIA Portal / 西门子PLC / S7-1200 / S7-1500, a .ap15–.ap21 project, 梯形图 / LAD / SCL 程序块, SimaticML / Openness, or asks to add, fix, convert, or screenshot PLC programs in a TIA project — even if they only give a textbook exercise and a project path.
compatibility: Windows, TIA Portal V15.1–V21 with the Openness option installed, .NET Framework 4.8, Python 3.8+.
---

# TIA Portal Openness + LAD generation

Use this skill for any task that edits PLC programs inside a Siemens TIA Portal project, especially when the user wants **梯形图 (LAD)** rather than SCL.

## The one core idea

The Openness API can open projects, create tags, compile, import, and export — but **it cannot author LAD networks**. There is no `CreateNetwork` / `AddContact` API. The reliable route is:

1. Generate a **SimaticML XML** block (or edit an exported one).
2. `plc.BlockGroup.Blocks.Import(file, ImportOptions.Override)`.
3. Compile; fix import/compile errors; export again to verify.

SCL external sources are easier to generate but usually do not satisfy a request for LAD. Do not silently substitute SCL when the user asks for 梯形图.

## Minimize networks (程序段)

When generating LAD, aim for the fewest networks that still compile and stay readable:

- **Prefer one cycle timer + time compares** over one timer/transition network per step. Six phases can be 1 timer network + 6 output networks.
- **Drive outputs directly from the time compares**; do not add step flags unless the sequence genuinely needs them.
- **Flash without a separate flag network:** two free-running 500 ms TONs give 1 Hz; reference `FL1.Q` directly in the output branches.
- **Merge independent timers into one network** when each branch starts at the Powerrail and the network has no coils (validated: three TONs in one network).
- **Merge parallel conditions with `O` gates, chain boxes with ENO**; independent coils must stay in separate networks.
- Benchmark: a six-phase traffic-light cycle can be done in **7 networks** (1 timer + 6 outputs).

## Environment

Defaults on this machine (override with env vars when different):

| Item | Default |
|---|---|
| TIA install | `E:\TIA_V21\coding\Portal V21` |
| Openness assemblies | `E:\TIA_V21\coding\Portal V21\PublicAPI\V21\net48` |
| C# compiler | `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe` |
| Python | `python` (3.11) |

- Read `<project>\ProjectInfo.txt` to learn the exact TIA version before doing anything.
- `TIA_API_DIR` overrides the Openness folder; `TIA_PROJECT` passes the `.ap2x` path to the helper tool; `TIA_TOOL_LOG` overrides the log file.
- Openness assemblies must **not** sit next to the executable. `TiaTool.cs` resolves them via `AssemblyResolve` from `TIA_API_DIR`; the alternative is an `app.config` with `codeBase` entries (see `references/openness-setup.md`).

## Workflow

1. **Close the TIA Portal GUI.** A project opened in the GUI is locked; Openness fails with “已被用户打开”. If a stale lock remains after a crash, wait ~2 minutes or kill the orphaned `Siemens.Automation.Portal` process.
2. **Work on a copy for experiments.** Copy the whole project folder next to the `.ap2x` file, not just the project file. Only write to the real project once the XML is known-good.
3. **Build the helper** (first use only, or after editing it):
   ```bash
   python "<skill>/scripts/build_tiatool.py"
   ```
4. **Inspect** the project: device/CPU, blocks, tags, external sources.
   ```bash
   TIA_PROJECT="E:\path\proj.ap21" "<skill>/scripts/bin/TiaTool.exe" inspect
   ```
5. **Create tags before importing blocks.** LAD XML references tags by symbolic name, so every name must exist first. Use a UTF-8 CSV:
   ```csv
   name,type,address
   Start,Bool,%I0.0
   Temp,Int,%MW30
   ```
   ```bash
   TIA_PROJECT="..." TiaTool.exe tags MyTagTable tags.csv
   ```
6. **Generate LAD XML** with `scripts/ladlib.py`, or export an existing block and splice it. See `references/workflow-examples.md`.
7. **Import, compile, read messages, fix, repeat.**
   ```bash
   TIA_PROJECT="..." TiaTool.exe importxml FB4.xml
   TIA_PROJECT="..." TiaTool.exe compile
   ```
8. **Set titles/comments** (blocks and networks) so the project is readable, and export to verify the final structure:
   ```bash
   TIA_PROJECT="..." TiaTool.exe titles titles.tsv
   TIA_PROJECT="..." TiaTool.exe export FB4 FB4_verify.xml
   ```
9. **Save is automatic** at the end of every command. Close TIA only after the last command finishes.

## LAD XML rules that cause most failures

These were learned from real imports; violating them gives cryptic German/Chinese compiler errors.

- **One `<Powerrail />` wire per network.** A single Powerrail wire may fan out to several first contacts (`<NameCon ... Name="in"/>` repeated), which is how parallel branches are built. Do not add a second Powerrail wire.
- **One use per output pin.** A contact/box `out` may appear in only one wire; reusing it across wires fails (“used multiple times at the cables”). Build parallel branches from the Powerrail, or merge with an `O` gate.
- **Independent rungs with separate coils cannot share one network.** Putting two unrelated rungs in one FlgNet gives “这些元素必须根据电流进行排序 / elements must be sorted according to current”. Use one network (`CompileUnit`) per independent rung. Consolidate by simplifying logic (self-hold expressions, `O` gates) and by chaining boxes through ENO, not by stacking unrelated coils.
- **Boxes need power on `en` and a real destination on `out`.** An `out` left on `OpenCon` causes “operand required at input or output is missing”. Intermediate boxes chain `eno` → next `en`.
- **Timer/counter instances:** the Part carries `<Instance Scope="LocalVariable|GlobalVariable" UId=".."><Component Name="..."/></Instance>` and a `TemplateValue` (`TON`: `time_type=Time`, `CTU`: `value_type=Int`). Static FB members are `IEC_TIMER` / `IEC_COUNTER`; an OB must use a global instance DB.
- **FB calls in FlgNet v5** are `<Call UId="21"><CallInfo Name="FB" BlockType="FB"><Instance Scope="GlobalVariable" UId="22"><Component Name="DB"/></Instance></CallInfo></Call>` inside `<Parts>` — **not** `<Part Name="Call">` (that fails with “Part … CallInfo 无效”). Only `Powerrail → en` is wired; `eno` is normally left unwired. A single-branch `O` gate is invalid (`Card≥2`); use a plain contact chain instead.
- **Time constants:** use `<Access Scope="TypedConstant"><Constant><ConstantValue>T#1S</ConstantValue>...`. `LiteralConstant` + `ConstantType=Time` was rejected.
- **Compare boxes use `pre` (power in), `in1`, `in2`, `out` — no `en`/`eno`.** `SrcType` is a template value (`Int`, etc.).
- **`Convert` uses `SrcType` + `DestType`.** Word/Byte sources and Word/Byte destinations are not accepted in this position; use an `Int` tag for analog words, and `Move` for Int→Byte output.
- **`Add`/`Mul` need `Card` (number of inputs) + `SrcType`; `Div`/`Mod` only `SrcType`.** Byte arithmetic is not supported.
- **UTF-8 with BOM** for any XML containing Chinese names/comments.
- **Unique XML IDs when splicing into an exported OB.** CompileUnit / MultilingualText IDs are document-wide; network FlgNet UIds may restart at 21 per network. When appending networks to an existing OB, start your document IDs above the existing maximum (e.g. `ladlib._doc_id[0] = 100`).

Full part/pin/template table: `references/lad-instructions.md`.

## Helper commands (`scripts/TiaTool.cs`)

| Command | Purpose |
|---|---|
| `inspect` | devices, software, blocks, tags, sources, types |
| `tags <table> <csv>` | create/recreate tags from UTF-8 CSV |
| `titles <tsv>` | set block title/comment (block, title, comment) |
| `importxml <xml...>` | import SimaticML blocks with Override |
| `importscl <name> <scl>` | create external source and generate blocks |
| `compile` | compile PLC software; logs errors/warnings recursively |
| `export <block> <file>` | export one block |
| `exportmany <dir> <block...>` | export many blocks |
| `delete <block...>` | delete blocks |
| `mkidb <db> <number> <auto 0\|1> <fb>` | create a single-instance DB for an FB |
| `rename <old> <new> ...` | rename tags (TIA updates references) |
| `deltags <name...>` | delete tags |
| `delsource <name...>` | delete external sources |

After a new executable is built, Windows/TIA shows an **Openness access** dialog (访问权限). This is the normal allowlist prompt; the user must authorize it (the 全部确定 button authorizes the app). Do not try to bypass it.

## Verification checklist

- `compile` ends with `errors=0`. Warnings about “inputs or outputs not in configured hardware” are usually pre-existing address choices (e.g. `%IW96`, `%Q2.0` on a 1214C) and do not block screenshotting.
- `inspect` shows every block `Consistent=True`, `Lang=LAD`.
- `export` the block and check the expected networks/parts; a single network can be wide after ENO chaining.
- Beware a **stale TIA GUI session**: if the user had the project open and saves an older copy, it overwrites your Openness changes. Re-export after any user interaction, and tell the user to close old windows before reopening.

## References

- `references/lad-instructions.md` — validated LAD part names, pins, template values, and gotchas.
- `references/openness-setup.md` — assembly resolution, build command, lock/allowlist, save behavior.
- `references/workflow-examples.md` — complete generator and OB-splice examples.
- `scripts/ladlib.py` — `NB` builder plus helpers (`or_selfhold`, `chain`, `ton_network`, `ctu_network`, `call_network`, compare, etc.).
