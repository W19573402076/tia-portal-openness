# -*- coding: utf-8 -*-
"""ladlib — build Siemens SimaticML LAD networks/blocks without the TIA GUI.

Validated against TIA Portal V21 (S7-1200). The module only produces XML; use
TiaTool.exe to import it. See references/lad-instructions.md for the pin/template
table and references/workflow-examples.md for end-to-end examples.

Quick demo:
    python ladlib.py demo.xml
"""
import io
import os
import sys

# --------------------------------------------------------------------------- #
# ids / escaping
# --------------------------------------------------------------------------- #
_doc_id = [3]


def reset_doc_ids(start=3):
    """Call before building a block that will be spliced into an exported OB."""
    _doc_id[0] = start


def _nid():
    v = _doc_id[0]
    _doc_id[0] += 1
    return v


def esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


# --------------------------------------------------------------------------- #
# low-level network builder
# --------------------------------------------------------------------------- #
class NB(object):
    """One FlgNet. UIds start at 21 (per-network namespace, like TIA exports)."""

    def __init__(self, start=21):
        self.uid = start
        self.parts = []
        self.wires = []

    def u(self):
        v = self.uid
        self.uid += 1
        return v

    def access(self, *components, **kw):
        v = self.u()
        scope = kw.get('scope', 'GlobalVariable')
        comps = ''.join('<Component Name="%s" />' % esc(c) for c in components)
        self.parts.append('<Access Scope="%s" UId="%d"><Symbol>%s</Symbol></Access>'
                          % (scope, v, comps))
        return v

    def const(self, value, ctype=None):
        v = self.u()
        ct = ('<ConstantType>%s</ConstantType>' % esc(ctype)) if ctype else ''
        self.parts.append('<Access Scope="LiteralConstant" UId="%d"><Constant>%s'
                          '<ConstantValue>%s</ConstantValue></Constant></Access>'
                          % (v, ct, esc(value)))
        return v

    def typed_const(self, value):
        v = self.u()
        self.parts.append('<Access Scope="TypedConstant" UId="%d"><Constant>'
                          '<ConstantValue>%s</ConstantValue></Constant></Access>'
                          % (v, esc(value)))
        return v

    def box(self, name, templates=None, version=None, inner=''):
        v = self.u()
        ver = (' Version="%s"' % version) if version else ''
        tvs = ''.join('<TemplateValue Name="%s" Type="%s">%s</TemplateValue>'
                      % (esc(n), esc(t), esc(val)) for n, t, val in (templates or []))
        self.parts.append('<Part Name="%s"%s UId="%d">%s%s</Part>'
                          % (esc(name), ver, v, inner, tvs))
        return v

    def wire(self, *nodes):
        v = self.u()
        inner = []
        for n in nodes:
            if n[0] == 'P':
                inner.append('<Powerrail />')
            elif n[0] == 'pin':
                inner.append('<NameCon UId="%d" Name="%s" />' % (n[1], n[2]))
            elif n[0] == 'id':
                inner.append('<IdentCon UId="%d" />' % n[1])
            elif n[0] == 'open':
                inner.append('<OpenCon UId="%d" />' % self.u())
        self.wires.append('<Wire UId="%d">%s</Wire>' % (v, ''.join(inner)))

    def open_pin(self, part, pin):
        self.wire(('pin', part, pin), ('open',))


# --------------------------------------------------------------------------- #
# part helpers
# --------------------------------------------------------------------------- #
def _tag_components(tag):
    return tag if isinstance(tag, (tuple, list)) else (tag,)


def add_contact(nb, tag, neg=False, local=False):
    a = nb.access(*_tag_components(tag),
                  scope='LocalVariable' if local else 'GlobalVariable')
    c = nb.u()
    if neg:
        nb.parts.append('<Part Name="Contact" UId="%d"><Negated Name="operand" /></Part>' % c)
    else:
        nb.parts.append('<Part Name="Contact" UId="%d" />' % c)
    nb.wire(('id', a), ('pin', c, 'operand'))
    return c


def add_coil(nb, kind, tag, local=False):
    a = nb.access(*_tag_components(tag),
                  scope='LocalVariable' if local else 'GlobalVariable')
    c = nb.u()
    nb.parts.append('<Part Name="%s" UId="%d" />' % (kind, c))
    nb.wire(('id', a), ('pin', c, 'operand'))
    return c


def add_box(nb, name, templates=None, version=None, instance=None,
            instance_scope='LocalVariable', extra_inner=''):
    inner = extra_inner
    if instance:
        iu = nb.u()
        inner = ('<Instance Scope="%s" UId="%d"><Component Name="%s" /></Instance>'
                 % (instance_scope, iu, esc(instance))) + inner
    return nb.box(name, templates, version, inner)


def typed_time(nb, value):
    return nb.typed_const(value)


def add_ref(nb, ref):
    kind = ref[0]
    if kind == 'tag':
        return nb.access(ref[1], scope='GlobalVariable')
    if kind == 'local':
        return nb.access(*_tag_components(ref[1]), scope='LocalVariable')
    if kind == 'const':
        return nb.const(ref[1], ref[2])
    raise ValueError('bad ref: %r' % (ref,))


def series(nb, specs):
    """Create a chain of contacts from the power rail; return the last contact UId.

    spec = (tag[, neg[, local]]).
    """
    prev = None
    for spec in specs:
        tag = spec[0]
        neg = spec[1] if len(spec) > 1 else False
        local = spec[2] if len(spec) > 2 else False
        c = add_contact(nb, tag, neg, local)
        if prev is None:
            nb.wire(('P',), ('pin', c, 'in'))
        else:
            nb.wire(('pin', prev, 'out'), ('pin', c, 'in'))
        prev = c
    return prev


def apply_out(nb, part, out, out_pin='out'):
    if out is None:
        nb.wire(('pin', part, out_pin), ('open',))
        return
    if out[0] == 'coil':
        q = add_coil(nb, out[1], out[2], out[3] if len(out) > 3 else False)
        nb.wire(('pin', part, out_pin), ('pin', q, 'in'))
    else:
        u = add_ref(nb, out)
        nb.wire(('pin', part, out_pin), ('id', u))


# --------------------------------------------------------------------------- #
# network patterns
# --------------------------------------------------------------------------- #
def rung(comment, specs, kind, out, out_local=False):
    nb = NB()
    last = series(nb, specs)
    q = add_coil(nb, kind, out, out_local)
    nb.wire(('pin', last, 'out'), ('pin', q, 'in'))
    return network_parts(nb, comment)


def or_selfhold(comment, branches, stops, kind, out, out_local=False):
    """(branch1 OR branch2 ...) AND stop1 AND stop2 ... -> coil.

    branches: list of contact chains, e.g. [[('Start',)], [('Run',)]]
    stops:    list of contact specs in series, e.g. [('Stop', True)]
    """
    nb = NB()
    firsts, lasts = [], []
    for br in branches:
        prev = None
        for spec in br:
            c = add_contact(nb, spec[0],
                            spec[1] if len(spec) > 1 else False,
                            spec[2] if len(spec) > 2 else False)
            if prev is None:
                firsts.append(c)
            else:
                nb.wire(('pin', prev, 'out'), ('pin', c, 'in'))
            prev = c
        lasts.append(prev)
    og = add_box(nb, 'O', [('Card', 'Cardinality', str(len(branches)))])
    for i, last in enumerate(lasts):
        nb.wire(('pin', last, 'out'), ('pin', og, 'in%d' % (i + 1)))
    nb.wire(*([('P',)] + [('pin', f, 'in') for f in firsts]))
    prev = None
    for spec in stops:
        c = add_contact(nb, spec[0],
                        spec[1] if len(spec) > 1 else False,
                        spec[2] if len(spec) > 2 else False)
        if prev is None:
            nb.wire(('pin', og, 'out'), ('pin', c, 'in'))
        else:
            nb.wire(('pin', prev, 'out'), ('pin', c, 'in'))
        prev = c
    q = add_coil(nb, kind, out, out_local)
    src = og if prev is None else prev
    nb.wire(('pin', src, 'out'), ('pin', q, 'in'))
    return network_parts(nb, comment)


def chain(comment, start, boxes):
    """Boxes chained left-to-right via ENO.

    start: None (power rail), contact specs, or ('pbox', input_tag, edge_bit).
    boxes: dicts with keys part, templates, version, instance, instance_scope,
           inputs=[(pin, ref)], out=ref, out_pin='out', en_pin='en'.
    ref = ('tag', name) | ('local', name) | ('const', value, type)
    """
    nb = NB()
    uids = [add_box(nb, b['part'], b.get('templates'), b.get('version'),
                    b.get('instance'), b.get('instance_scope', 'LocalVariable'),
                    b.get('extra_inner', ''))
            for b in boxes]
    first_en = boxes[0].get('en_pin', 'en')
    if start is None:
        nb.wire(('P',), ('pin', uids[0], first_en))
    elif start[0] == 'pbox':
        c = add_contact(nb, start[1])
        pb = add_box(nb, 'PBox')
        bit = nb.access(start[2], scope='GlobalVariable')
        nb.wire(('P',), ('pin', c, 'in'))
        nb.wire(('pin', c, 'out'), ('pin', pb, 'in'))
        nb.wire(('id', bit), ('pin', pb, 'bit'))
        nb.wire(('pin', pb, 'out'), ('pin', uids[0], first_en))
    else:
        last = series(nb, start)
        nb.wire(('pin', last, 'out'), ('pin', uids[0], first_en))
    for i, b in enumerate(boxes):
        for pin, ref in b.get('inputs', []):
            u = add_ref(nb, ref)
            nb.wire(('id', u), ('pin', uids[i], pin))
        apply_out(nb, uids[i], b.get('out'), b.get('out_pin', 'out'))
        if i + 1 < len(boxes):
            nb.wire(('pin', uids[i], 'eno'),
                    ('pin', uids[i + 1], boxes[i + 1].get('en_pin', 'en')))
        else:
            nb.open_pin(uids[i], 'eno')
    return network_parts(nb, comment)


def box_network(comment, part, templates=None, version=None, instance=None,
                instance_scope='LocalVariable', en=None, inputs=(), out=None,
                out_pin='out', en_pin='en', use_eno=True):
    nb = NB()
    b = add_box(nb, part, templates, version, instance, instance_scope)
    if en is None:
        nb.wire(('P',), ('pin', b, en_pin))
    else:
        last = series(nb, en)
        nb.wire(('pin', last, 'out'), ('pin', b, en_pin))
    for pin, ref in inputs:
        u = add_ref(nb, ref)
        nb.wire(('id', u), ('pin', b, pin))
    apply_out(nb, b, out, out_pin)
    if use_eno:
        nb.open_pin(b, 'eno')
    return network_parts(nb, comment)


def pbox_coil(comment, in_tag, bit, kind, out, out_local=False):
    nb = NB()
    c = add_contact(nb, in_tag)
    pb = add_box(nb, 'PBox')
    b = nb.access(bit, scope='GlobalVariable')
    q = add_coil(nb, kind, out, out_local)
    nb.wire(('P',), ('pin', c, 'in'))
    nb.wire(('pin', c, 'out'), ('pin', pb, 'in'))
    nb.wire(('id', b), ('pin', pb, 'bit'))
    nb.wire(('pin', pb, 'out'), ('pin', q, 'in'))
    return network_parts(nb, comment)


def call_network(comment, fb_name, db_name):
    """Call an FB from an OB. FlgNet v5 uses a <Call> element, not <Part>."""
    nb = NB()
    uid = nb.u()
    iu = nb.u()
    nb.parts.append(
        '<Call UId="%d"><CallInfo Name="%s" BlockType="FB">'
        '<Instance Scope="GlobalVariable" UId="%d"><Component Name="%s" />'
        '</Instance></CallInfo></Call>' % (uid, esc(fb_name), iu, esc(db_name)))
    nb.wire(('P',), ('pin', uid, 'en'))
    return network_parts(nb, comment)


def ton_network(comment, instance, pt, en_specs, q_action=None,
                instance_scope='LocalVariable'):
    nb = NB()
    t = add_box(nb, 'TON', [('time_type', 'Type', 'Time')], '1.0',
                instance, instance_scope)
    p = typed_time(nb, pt)
    nb.wire(('id', p), ('pin', t, 'PT'))
    last = series(nb, en_specs)
    nb.wire(('pin', last, 'out'), ('pin', t, 'IN'))
    if q_action:
        kind, tag, local = q_action
        q = add_coil(nb, kind, tag, local)
        nb.wire(('pin', t, 'Q'), ('pin', q, 'in'))
    else:
        nb.open_pin(t, 'Q')
    nb.open_pin(t, 'ET')
    return network_parts(nb, comment)


def ctu_network(comment, instance, pv, en_specs, q_action, r_ref,
                instance_scope='LocalVariable'):
    nb = NB()
    c = add_box(nb, 'CTU', [('value_type', 'Type', 'Int')], '1.0',
                instance, instance_scope)
    p = add_ref(nb, ('const', str(pv), 'Int'))
    nb.wire(('id', p), ('pin', c, 'PV'))
    last = series(nb, en_specs)
    nb.wire(('pin', last, 'out'), ('pin', c, 'CU'))
    r = add_ref(nb, r_ref)
    nb.wire(('id', r), ('pin', c, 'R'))
    kind, tag, local = q_action
    q = add_coil(nb, kind, tag, local)
    nb.wire(('pin', c, 'Q'), ('pin', q, 'in'))
    nb.open_pin(c, 'CV')
    return network_parts(nb, comment)


def cmp_network(comment, part, in1, in2, kind, out, out_local=False):
    """part = 'Gt' | 'Lt' | 'Eq' | 'Ge' | 'Le' | 'Ne'; compare uses pre/in1/in2/out."""
    nb = NB()
    g = add_box(nb, part, [('SrcType', 'Type', 'Int')])
    a1 = add_ref(nb, in1)
    a2 = add_ref(nb, in2)
    nb.wire(('id', a1), ('pin', g, 'in1'))
    nb.wire(('id', a2), ('pin', g, 'in2'))
    nb.wire(('P',), ('pin', g, 'pre'))
    q = add_coil(nb, kind, out, out_local)
    nb.wire(('pin', g, 'out'), ('pin', q, 'in'))
    return network_parts(nb, comment)


# --------------------------------------------------------------------------- #
# block documents
# --------------------------------------------------------------------------- #
def network_parts(nb, comment=''):
    cu, c1, c2, t1, t2 = _nid(), _nid(), _nid(), _nid(), _nid()
    return ('<SW.Blocks.CompileUnit ID="%X" CompositionName="CompileUnits">'
            '<AttributeList><NetworkSource>'
            '<FlgNet xmlns="http://www.siemens.com/automation/Openness/SW/NetworkSource/FlgNet/v5">'
            '<Parts>%s</Parts><Wires>%s</Wires></FlgNet></NetworkSource>'
            '<ProgrammingLanguage>LAD</ProgrammingLanguage></AttributeList>'
            '<ObjectList><MultilingualText ID="%X" CompositionName="Comment"><ObjectList>'
            '<MultilingualTextItem ID="%X" CompositionName="Items"><AttributeList>'
            '<Culture>zh-CN</Culture><Text>%s</Text></AttributeList></MultilingualTextItem>'
            '</ObjectList></MultilingualText>'
            '<MultilingualText ID="%X" CompositionName="Title"><ObjectList>'
            '<MultilingualTextItem ID="%X" CompositionName="Items"><AttributeList>'
            '<Culture>zh-CN</Culture><Text /></AttributeList></MultilingualTextItem>'
            '</ObjectList></MultilingualText></ObjectList></SW.Blocks.CompileUnit>'
            % (cu, ''.join(nb.parts), ''.join(nb.wires), c1, c2, esc(comment), t1, t2))


def fb_doc(name, static=None, networks=None, number=0, auto_number=True,
           engineering_version='V21'):
    members = ''.join('<Member Name="%s" Datatype="%s" />' % (esc(n), esc(t))
                      for n, t in (static or []))
    return ('<?xml version="1.0" encoding="utf-8"?>\n<Document>\n'
            '  <Engineering version="%s" />\n'
            '  <SW.Blocks.FB ID="0">\n    <AttributeList>\n'
            '      <AutoNumber>%s</AutoNumber>\n'
            '      <Interface>\n'
            '        <Sections xmlns="http://www.siemens.com/automation/Openness/SW/Interface/v5">\n'
            '          <Section Name="Input" />\n          <Section Name="Output" />\n'
            '          <Section Name="InOut" />\n'
            '          <Section Name="Static">%s</Section>\n'
            '          <Section Name="Temp" />\n          <Section Name="Constant" />\n'
            '        </Sections>\n      </Interface>\n'
            '      <MemoryLayout>Optimized</MemoryLayout>\n'
            '      <Name>%s</Name>\n      <Namespace />\n      <Number>%d</Number>\n'
            '      <ProgrammingLanguage>LAD</ProgrammingLanguage>\n'
            '      <SetENOAutomatically>false</SetENOAutomatically>\n'
            '    </AttributeList>\n    <ObjectList>%s</ObjectList>\n'
            '  </SW.Blocks.FB>\n</Document>\n'
            % (engineering_version, 'true' if auto_number else 'false', members,
               esc(name), number, ''.join(networks or [])))


def ob_doc(name, number, networks, secondary_type='ProgramCycle',
           engineering_version='V21'):
    """Build a minimal OB. Prefer splicing into an exported OB for existing projects."""
    head = ('<?xml version="1.0" encoding="utf-8"?>\n<Document>\n'
            '  <Engineering version="%s" />\n'
            '  <SW.Blocks.OB ID="0">\n    <AttributeList>\n'
            '      <Interface>\n'
            '        <Sections xmlns="http://www.siemens.com/automation/Openness/SW/Interface/v5">\n'
            '          <Section Name="Input">\n'
            '            <Member Name="Initial_Call" Datatype="Bool" Informative="true" />\n'
            '            <Member Name="Remanence" Datatype="Bool" Informative="true" />\n'
            '          </Section>\n'
            '          <Section Name="Temp" />\n'
            '          <Section Name="Constant" />\n'
            '        </Sections>\n      </Interface>\n'
            '      <MemoryLayout>Optimized</MemoryLayout>\n'
            '      <Name>%s</Name>\n      <Namespace />\n      <Number>%d</Number>\n'
            '      <ProgrammingLanguage>LAD</ProgrammingLanguage>\n'
            '      <SecondaryType>%s</SecondaryType>\n'
            '      <SetENOAutomatically>false</SetENOAutomatically>\n'
            '    </AttributeList>\n    <ObjectList>%s</ObjectList>\n'
            '  </SW.Blocks.OB>\n</Document>\n'
            % (engineering_version, esc(name), number, esc(secondary_type),
               ''.join(networks)))
    return head


def save(path, xml):
    with io.open(path, 'w', encoding='utf-8-sig') as f:
        f.write(xml)
    print('written %s' % path)


# --------------------------------------------------------------------------- #
# demo / self-test
# --------------------------------------------------------------------------- #
def demo(path='lad_demo.xml'):
    static = [('edge', 'Bool'), ('T1', 'IEC_TIMER')]
    nets = []
    nets.append(chain('Start rising edge: copy Init -> Lamp',
                      ('pbox', 'Start', 'edge'),
                      [{'part': 'Move', 'templates': [('Card', 'Cardinality', '1')],
                        'inputs': [('in', ('tag', 'Init'))],
                        'out': ('tag', 'Lamp')}]))
    nets.append(or_selfhold('Run self-hold',
                            [[('Start',)], [('Run',)]], [('Stop', True)],
                            'Coil', 'Run'))
    nets.append(ton_network('Run 5 s', 'T1', 'T#5S', [('Run',)]))
    nets.append(rung('Timer done stops the run', [(('T1', 'Q'), False, True)],
                     'RCoil', 'Run'))
    save(path, fb_doc('FB_Demo', static, nets))


if __name__ == '__main__':
    demo(sys.argv[1] if len(sys.argv) > 1 else 'lad_demo.xml')
