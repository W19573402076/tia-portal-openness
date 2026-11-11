# Workflow examples

All snippets assume `sys.path.insert(0, "<skill>/scripts")` and
`from ladlib import *`.

## 1. FB with start/stop self-hold and a delayed stop

Requirement: press `I0.0` → `Q0.0` on and self-hold; `I0.1` stops; after 60 s `Q0.0` drops.

```python
def build():
    static = [('T60', 'IEC_TIMER')]
    nets = [
        or_selfhold('start/self-hold, stop opens',
                    [[('I0_0',)], [('Q0_0',)]], [('I0_1', True)],
                    'Coil', 'Q0_0'),
        ton_network('run 60 s', 'T60', 'T#60S', [('Q0_0',)]),
        rung('60 s done -> reset Q0.0', [(('T60', 'Q'), False, True)],
             'RCoil', 'Q0_0'),
    ]
    save('FB_Pump.xml', fb_doc('FB_Pump', static, nets))
```

`or_selfhold` builds the `O` gate and the single Powerrail wire with both branch starts. The resulting LAD is one network for the self-hold, one for the timer, one for the reset.

If the start button may be **held** in simulation, use an edge start instead:

```python
nets = [
    pbox_coil('rising edge sets pump', 'I0_0', 'edge', 'SCoil', 'Q0_0'),
    rung('NC stop resets pump', [('I0_1', True)], 'RCoil', 'Q0_0'),
    ton_network('pump run time', 'T60', 'T#60S', [('Q0_0',)]),
    rung('timeout resets pump', [(('T60', 'Q'), False, True)], 'RCoil', 'Q0_0'),
]
static = [('edge', 'Bool'), ('T60', 'IEC_TIMER')]
```

The edge bit `edge` must be a **global M bit** in an OB, or a static Bool in an FB (as above). The S/R latch makes holding the start button harmless.

## 2. Rising-edge analog conversion in one network

```python
conv = {'part': 'Convert',
        'templates': [('SrcType', 'Type', 'Int'), ('DestType', 'Type', 'DInt')],
        'inputs': [('in', ('tag', 'AIW64'))],
        'out': ('local', ('raw',))}
mul = {'part': 'Mul',
       'templates': [('Card', 'Cardinality', '2'), ('SrcType', 'Type', 'DInt')],
       'inputs': [('in1', ('local', ('raw',))), ('in2', ('const', '8000', 'DInt'))],
       'out': ('local', ('scaled',))}
add = {'part': 'Add',
       'templates': [('Card', 'Cardinality', '2'), ('SrcType', 'Type', 'DInt')],
       'inputs': [('in1', ('local', ('scaled',))), ('in2', ('const', '13824', 'DInt'))],
       'out': ('local', ('rounded',))}
div = {'part': 'Div', 'templates': [('SrcType', 'Type', 'DInt')],
       'inputs': [('in1', ('local', ('rounded',))), ('in2', ('const', '27648', 'DInt'))],
       'out': ('local', ('raw',))}
out = {'part': 'Convert',
       'templates': [('SrcType', 'Type', 'DInt'), ('DestType', 'Type', 'Int')],
       'inputs': [('in', ('local', ('raw',)))], 'out': ('tag', 'MW30')}

static = [('edge', 'Bool'), ('raw', 'DInt'), ('scaled', 'DInt'), ('rounded', 'DInt')]
save('FB_Scale.xml',
     fb_doc('FB_Scale', static,
            [chain('I0.2 rising edge: AIW64 -> MW30 in 0.1 C', ('pbox', 'I0_2', 'edge'),
                   [conv, mul, add, div, out])]))
```

Notes:
- Analog `%IW64` should be an **Int** tag for `Convert` (`SrcType=Int`); a `Word` tag is rejected.
- The `+13824` is half of 27648, giving round-to-nearest.

## 3. Compare + set/reset (hysteresis)

```python
nets = [
    cmp_network('> 5000 (500.0 C) sets fan', 'Gt', ('tag', 'Temp'),
                ('const', '5000', 'Int'), 'SCoil', 'Q0_0'),
    cmp_network('< 4500 (450.0 C) resets fan', 'Lt', ('tag', 'Temp'),
                ('const', '4500', 'Int'), 'RCoil', 'Q0_0'),
]
save('FB_Fan.xml', fb_doc('FB_Fan', [], nets))
```

## 4. Timer/counter slip detection

```python
static = [('pulse', 'Bool'), ('edge', 'Bool'), ('timing', 'Bool'),
          ('resetCnt', 'Bool'), ('T4', 'IEC_TIMER'), ('T5', 'IEC_TIMER'),
          ('C1', 'IEC_COUNTER')]
nets = [
    or_selfhold('run latch', [[('I0_1',)], [('Q0_0',)]],
                [('I0_2', True), (('T5', 'Q'), True, True)], 'Coil', 'Q0_0'),
    pbox_coil('pulse edge', 'I0_0', 'edge', 'Coil', 'pulse', True),
    ctu_network('4 pulses = group', 'C1', 4,
                [('Q0_0', False, False), ('pulse', False, True)],
                ('Coil', 'resetCnt', True), ('local', ('resetCnt',))),
    or_selfhold('group timing', [[('Q0_0',), ('pulse', False, True)],
                                  [('timing', False, True)]],
                [('resetCnt', True, True), ('Q0_0', True)], 'Coil', 'timing', True),
    ton_network('4 s window', 'T4', 'T#4S', [('timing', False, True)]),
    ton_network('5 s without pulse', 'T5', 'T#5S',
                [('Q0_0',), ('pulse', True, True)]),
    rung('slip alarm', [(('T4', 'Q'), False, True)], 'Coil', 'Q0_1'),
]
save('FB_Slip.xml', fb_doc('FB_Slip', static, nets))
```

Always add a run condition to a latched timing flag's reset path; otherwise the timer can stay pending after a protective stop and the alarm remains on.

## 5. Editing an existing OB (splice)

```python
from ladlib import reset_doc_ids
reset_doc_ids(100)          # avoid IDs already used by the exported OB

nets = ''.join([net1, net2, net3, net4])
src = open('Main.xml', encoding='utf-8-sig').read()
first = src.find('<SW.Blocks.CompileUnit')
last_end = src.rfind('</SW.Blocks.CompileUnit>') + len('</SW.Blocks.CompileUnit>')
open('Main_new.xml', 'w', encoding='utf-8-sig').write(src[:first] + nets + src[last_end:])
```

This preserves the OB's interface, `MemoryLayout`, block title, and comment. Do not reuse IDs that already exist in the OB (e.g. a block-level Title with ID 12).

## 6. End-to-end shell sequence

```bash
set TIA_PROJECT=E:\project\demo.ap21
python "<skill>\scripts\build_tiatool.py"

TiaTool.exe inspect
TiaTool.exe tags MyTags tags.csv
TiaTool.exe importxml FB1.xml FB2.xml
TiaTool.exe compile
TiaTool.exe titles titles.tsv
TiaTool.exe exportmany . FB1 FB2
```

Check `tia_output.txt` after each step. A successful run ends with `errors=0`; import failures print the exact SimaticML error and continue with the next file.

## 7. Screenshot-friendly consolidation

- One independent condition/rung per network is mandatory, but you can merge:
  - start/stop/hold into one `or_selfhold` network;
  - a whole math chain into one `chain` network using ENO;
  - multiple stop conditions into series NC contacts;
  - multiple start/stop buttons into parallel branches.
- A network with a long ENO chain is wide, not tall; a self-hold network with an `O` gate is compact.
- Prefer actual outputs (`Q0.0`) as state flags when the program is standalone; each exercise block is usually simulated separately.
- Set per-network comments in Chinese so the screenshot is self-explanatory; `network_parts(nb, '说明')` stores them in the network Comment field.
