# Openness setup, locks, and helper tool

## Version discovery

Each TIA project folder contains `ProjectInfo.txt`:

```yaml
TiaPortal:
  MinimumRequired:
  - Version: V21.0
  LastUsed:
  - Version: V21
UsedProducts:
- Name: STEP 7 Basic
  Version: V21
```

Use it to choose the PublicAPI folder and the `<Engineering version="V21" />` value in XML. For an older project (e.g. V16), the API path is
`<TIA install>\PublicAPI\V16\net48` (check what exists) and the XML engineering version should match.

## Openness assemblies

Default: `E:\TIA_V21\coding\Portal V21\PublicAPI\V21\net48`

- V21 exposes the API through `Siemens.Engineering.Base.dll` + `Siemens.Engineering.Step7.dll`.
- Older versions may have `Siemens.Engineering.dll` as the main assembly; reference it instead.
- **Do not copy the assemblies next to the executable.** Openness checks this and fails with:
  > Unable to connect to TIA Portal. Please ensure that “Copy Local” is set to false…

`TiaTool.cs` keeps them outside the exe directory and resolves them at runtime:

```csharp
string apiDir = Environment.GetEnvironmentVariable("TIA_API_DIR")
             ?? @"E:\TIA_V21\coding\Portal V21\PublicAPI\V21\net48";
AppDomain.CurrentDomain.AssemblyResolve += (s, e) => {
    string p = Path.Combine(apiDir, new AssemblyName(e.Name).Name + ".dll");
    return File.Exists(p) ? Assembly.LoadFrom(p) : null;
};
```

The alternative is an `app.config` / `TiaTool.exe.config` with `codeBase` entries for each assembly. The runtime resolver is simpler and works without a config file.

## Build

```bash
python "<skill>/scripts/build_tiatool.py"
# or manually:
"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe" -nologo -codepage:65001 ^
  -platform:x64 -target:exe -out:bin\TiaTool.exe ^
  -r:"E:\TIA_V21\coding\Portal V21\PublicAPI\V21\net48\Siemens.Engineering.Base.dll" ^
  -r:"E:\TIA_V21\coding\Portal V21\PublicAPI\V21\net48\Siemens.Engineering.Step7.dll" ^
  TiaTool.cs
```

`-codepage:65001` is only needed if the source contains Chinese literals. `-platform:x64` matches Openness.

## Project lock

- Openness **cannot open** a project that a TIA Portal GUI has open:
  > 无法访问项目/库 … 它已在计算机 … 上被用户 … 打开。
- Ask the user to close TIA, or close it yourself if authorized. After a crash, a stale lock can last about 2 minutes; an orphaned `Siemens.Automation.Portal` process can be killed.
- Always let the helper call `project.Save()` and `project.Close()` / `tia.Dispose()`; otherwise later sessions cannot connect.

## Openness access dialog

The first time a new `TiaTool.exe` build connects, TIA shows an **Openness 访问权限** dialog (process ID, application path) with 是 / 全部确定 / 否. This is the normal allowlist. The user must approve it; `全部确定` allows the current application. Rebuilding changes the hash, so a new prompt may appear. Do not attempt to bypass the dialog.

## Commands and environment

```bash
set TIA_PROJECT=E:\path\proj.ap21
set TIA_API_DIR=E:\TIA_V21\coding\Portal V21\PublicAPI\V21\net48   # optional
set TIA_TOOL_LOG=C:\temp\tia.log                                   # optional
TiaTool.exe inspect
```

Every command saves the project on exit. To experiment, copy the entire project folder (the `.ap21` plus `System/`, `IM/`, `XRef/`, `AdditionalFiles/`, …) and point `TIA_PROJECT` at the copy.

## Tag CSV

UTF-8, comma or tab separated, `#` comments allowed:

```csv
name,type,address
Start,Bool,%I0.0
Stop,Bool,%I0.1
Pump,Bool,%Q0.0
Temp,Int,%MW30
Freq,Real,%MD34
Lamp,Byte,%QB0
```

`TiaTool.exe tags <table> <csv>` creates the table if needed; an existing tag of the same name is deleted and recreated (references follow the name, so blocks stay valid after a compile).

## Titles TSV

UTF-8, tab separated, `block<TAB>title<TAB>comment`:

```
FB4_HoistSlip	第4题 提升机从动辊打滑检测	4个脉冲超过4s报警，5s无脉冲停机。
```

`TiaTool.exe titles titles.tsv` sets every language item of `PlcBlock.Title` and `PlcBlock.Comment`.

## Compile before export

`Block.Export` refuses a block that is new/modified:
> Inconsistent blocks and PLC data types (UDT) cannot be exported.

Run `compile` first. Conversely, after changing only titles, export may fail until another compile reports “all blocks are up-to-date”; retry export in a fresh session.

## Hardware-address warnings

Compile warnings like “Inputs or outputs are used that do not exist in the configured hardware” come from tags outside the configured CPU/module I/O (e.g. `%Q2.0`/`%IW96` on a 1214C). They do not block screenshotting or block import. If the user needs simulation, either configure the matching module or move the tags to valid addresses.
