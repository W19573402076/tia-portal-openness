# SimaticML LAD — validated part names, pins, templates

Validated on TIA Portal V21, CPU 1214C (S7-1200). FlgNet namespace:
`http://www.siemens.com/automation/Openness/SW/NetworkSource/FlgNet/v5`.

## Minimal FB document

```xml
<?xml version="1.0" encoding="utf-8"?>
<Document>
  <Engineering version="V21" />
  <SW.Blocks.FB ID="0">
    <AttributeList>
      <AutoNumber>true</AutoNumber>
      <Interface>
        <Sections xmlns="http://www.siemens.com/automation/Openness/SW/Interface/v5">
          <Section Name="Input" />
          <Section Name="Output" />
          <Section Name="InOut" />
          <Section Name="Static">
            <Member Name="edge" Datatype="Bool" />
            <Member Name="T1" Datatype="IEC_TIMER" />
          </Section>
          <Section Name="Temp" />
          <Section Name="Constant" />
        </Sections>
      </Interface>
      <MemoryLayout>Optimized</MemoryLayout>
      <Name>FB_Name</Name>
      <Namespace />
      <Number>0</Number>
      <ProgrammingLanguage>LAD</ProgrammingLanguage>
      <SetENOAutomatically>false</SetENOAutomatically>
    </AttributeList>
    <ObjectList>
      <!-- one SW.Blocks.CompileUnit per network -->
    </ObjectList>
  </SW.Blocks.FB>
</Document>
```

`ladlib.fb_doc()` produces exactly this.

## Parts

| Part | Key attributes | Pins | Notes |
|---|---|---|---|
| `Contact` | `<Negated Name="operand"/>` = NC | `in`, `out` (power); `operand` | operand from an `Access` |
| `Call` | FlgNet **v5** element, not `Part`: `<Call UId="21"><CallInfo Name="FB" BlockType="FB"><Instance Scope="GlobalVariable" UId="22"><Component Name="DB"/></Instance></CallInfo></Call>` | `en`, `eno`, plus FB params | wire only `Powerrail → en`; `eno` may be left unwired |
| `Coil` / `SCoil` / `RCoil` | — | `in` (power); `operand` | normal / set / reset |
| `O` | `TemplateValue Card=2..N` | `in1..inN`, `out` | Boolean OR of parallel branches |
| `PBox` | — | `in`, `out` (power); `bit` | rising-edge one-shot; `bit` is a retentive Bool (M bit in OB, static in FB) |
| `TON` | `Version="1.0"`, `Instance`, `TemplateValue time_type=Time` | `IN`, `PT`, `Q`, `ET` | `Q` can drive a coil or be read by a contact; open unused pins |
| `CTU` | `Version="1.0"`, `Instance`, `TemplateValue value_type=Int` | `CU`, `R`, `PV`, `Q`, `CV` | `CU` is power; `R`, `PV` are operands; `Q` power |
| `Move` | `TemplateValue Card=1` | `en`, `in`, `out`, `eno` | works Int→Byte, Byte→Byte |
| `Convert` | `SrcType`, `DestType` | `en`, `in`, `out`, `eno` | `SrcType=Int, DestType=DInt/Real/USInt`; `DestType=Int` (from DInt) works; `Word` source / `Word`/`Byte` destination rejected |
| `Mul` / `Add` | `Card=2`, `SrcType` | `en`, `in1`, `in2`, `out`, `eno` | `Int`, `DInt` OK; `Byte` rejected |
| `Div` / `Mod` | `SrcType` (no `Card`) | `en`, `in1`, `in2`, `out`, `eno` | fixed two inputs |
| `Normalize` | `SrcType`, `DestType` | `en`, `MIN`, `VALUE`, `MAX`, `OUT`, `eno` | this is SCL `NORM_X` |
| `Scale_X` | `SrcType=Real`, `DestType=Real` | `en`, `MIN`, `VALUE`, `MAX`, `OUT`, `eno` | `VALUE` must be REAL 0..1 |
| `SHL` / `SHR` | `SrcType` | `en`, `IN`, `N`, `OUT`, `eno` | Byte works |
| `Gt` / `Lt` / `Eq` / `Ge` / `Le` / `Ne` | `SrcType` | `pre`, `in1`, `in2`, `out` | compare is contact-like: **`pre` is power in**, no `en`/`eno` |

`ladlib.add_box()` adds the `Instance` block automatically when `instance=` is set.

## Instances

```xml
<Part Name="TON" Version="1.0" UId="31">
  <Instance Scope="LocalVariable" UId="32">
    <Component Name="T1" />
  </Instance>
  <TemplateValue Name="time_type" Type="Type">Time</TemplateValue>
</Part>
```

- FB multi-instance: `Member Name="T1" Datatype="IEC_TIMER"` (or `IEC_COUNTER`).
- OB / global instance DB: `Scope="GlobalVariable"` and `Component Name="IEC_Timer_0_DB"`; the DB must exist. `CreateInstanceDB(..., "TON")` does **not** work for system FBs ("Block 'TON' does not exist"); put timers in an FB's Static section and create one instance DB for that FB (`TiaTool.exe mkidb`).
- Multiple independent TONs may share one network when each branch starts at the Powerrail and the network contains no coils (validated with three TONs).
- Read a timer bit with two components:
  `<Access Scope="LocalVariable"><Symbol><Component Name="T1"/><Component Name="Q"/></Symbol></Access>`.

## Constants

| Value | XML |
|---|---|
| Int / DInt | `Access Scope="LiteralConstant"` + `<ConstantType>Int</ConstantType>` + `<ConstantValue>5000</ConstantValue>` |
| Real | same with `ConstantType=Real`, e.g. `45.0` |
| Time | `Access Scope="TypedConstant"` + `<ConstantValue>T#5S</ConstantValue>` (no ConstantType) |

`T#1s` lowercase was rejected in a `LiteralConstant`; `TypedConstant` with `T#1S` works.

## Wiring rules

- A `<Wire>` may contain **one Powerrail and several sinks**:
  ```xml
  <Wire><Powerrail /><NameCon UId="27" Name="in" /><NameCon UId="28" Name="in" /></Wire>
  ```
  This is the legal way to build parallel branches.
- Every other wire has one source and one sink. A pin “out” used as a source twice across wires fails (“used multiple times at the cables”). Build parallel branches from the Powerrail, or merge them with an `O` gate.
- Unused box inputs/outputs must be connected to `<OpenCon>`; an unconnected `OUT` causes “operand required at input or output is missing”.
- Independent rungs with separate coils in one `FlgNet` fail with “elements must be sorted according to current / 必须根据电流进行排序”. Use one `CompileUnit` per independent rung.

## ENO chaining (one wide network instead of many)

Wire `box1.eno` → `box2.en` to force sequential execution in one network:

```python
conv = {'part': 'Convert', 'templates': [('SrcType','Type','Int'), ('DestType','Type','DInt')],
        'inputs': [('in', ('tag','AIW'))], 'out': ('local', ('tmp',))}
mul  = {'part': 'Mul', 'templates': [('Card','Cardinality','2'), ('SrcType','Type','DInt')],
        'inputs': [('in1', ('local',('tmp',))), ('in2', ('const','8000','DInt'))],
        'out': ('local', ('acc',))}
net = chain('rising edge conversion', ('pbox', 'I0.2', 'edge'), [conv, mul])
```

The final box's `eno` is opened automatically. This is how a whole 5-box math chain becomes one program segment.

## Editing an exported OB

1. `TiaTool.exe export Main Main.xml` (compile first if export says *Inconsistent blocks*).
2. Find the first `<SW.Blocks.CompileUnit` and the last `</SW.Blocks.CompileUnit>`; replace that span with your new networks, keeping the OB-level `Comment`/`Title` MultilingualText elements.
3. Set `ladlib.reset_doc_ids(100)` (or above the existing max) to avoid duplicate SimaticML IDs.
4. `importxml Main_new.xml`, then `compile`.

## Error → cause

| Message | Cause |
|---|---|
| `An instruction with the name 'X' cannot be found` | wrong Part name (case-sensitive: `Move`, `Mul`, `Div`, `Normalize`, `Scale_X`, `SHL`, `Gt`…) |
| `TemplateValue ... is invalid/missing` | missing/wrong `Card`, `SrcType`, `DestType`, `CmpType` (compare has no `CmpType`) |
| `connection named 'en' ... does not exist` | compare boxes use `pre`, not `en` |
| `elements must be sorted according to current` | unrelated rungs/coils in one network |
| `operand required at the input or output is missing` | box `out`/`eno` left dangling (use a real operand or OpenCon) |
| `data type byte is not allowed` | `Add/Mul/Convert` with Byte; use Int/DInt then `Move` |
| `Duplicate Simatic ML ID` | spliced networks reuse existing IDs; reset document IDs |
| `Inconsistent blocks ... cannot be exported` | compile first; export requires up-to-date blocks |
| `used multiple times at the cables` | 同一个 `out`/`eno` 引脚被两根线引用；分叉改用独立支路或 `O` 门 |
| `Part ... CallInfo 无效` | v5 的 FB 调用是顶层 `<Call>` 元素，不是 `<Part Name="Call">` |
