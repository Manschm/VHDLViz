from typing import Dict, List, Tuple, Optional
from model import FileInfo, Port

def _strip_outer_parens(s: str) -> str:
    t = s.strip()
    while t.startswith('(') and t.endswith(')'):
        depth = 0; ok = True
        for ch in t:
            if ch == '(': depth += 1
            elif ch == ')':
                depth -= 1
                if depth < 0: ok = False; break
        if ok and depth == 0: t = t[1:-1].strip()
        else: break
    return t

def _split_base_slice(a: str) -> Tuple[str, Optional[str]]:
    a = a.strip()
    if '(' in a and a.endswith(')'):
        base = a[:a.index('(')].strip()
        sl = a[a.index('(')+1:-1].strip()
        if base.isidentifier(): return base, sl
    return (a, None)

def _classify_actual(actual: str, fi: FileInfo) -> Tuple[str, str, Optional[str]]:
    """
    Return (kind, label, bundle_base)
      kind in {'signal','eport','const','expr','open'}
      label is display (keeps slice etc.)
      bundle_base groups e.g. data(3), data(7 downto 0) under 'data'
    """
    a = _strip_outer_parens(actual)
    al = a.lower()
    if al == 'open': return ('open', a, None)
    if al in ('0','1') or al.startswith("'") or al.startswith('"') or al.startswith('x"') or al.startswith('b"'):
        return ('const', a, None)

    names_sig = {s.name for s in fi.signals}
    names_e   = {p.name for p in fi.ports}
    base, sl = _split_base_slice(a)
    if base in names_sig: return ('signal', a, base)
    if base in names_e:   return ('eport', a, base)
    return ('expr', a, None)

def build_wiring(fi: FileInfo,
                 entity_port_db: Dict[str, Dict[str, Port]]) -> Dict:
    """
    Build the wiring model for one file with:
      nodes: [{id,label,kind,inputs?,outputs?}]
      edges: [{id,source,target,label,base,src_pin?,dst_pin?,bundle_n,bundle_idx}]
    Notes:
      - Entity inputs are treated as DRIVERS (flow into the architecture).
      - Entity outputs are SINKS (flow out of the architecture).
      - No net hubs; edges connect drivers -> sinks directly.
    """
    # Instance port directions (if entity is known)
    inst_port_dirs: Dict[str, Dict[str, str]] = {}
    for inst in fi.instances:
        ent = inst.entity_ref or inst.component_name
        if ent and ent in entity_port_db:
            inst_port_dirs[inst.label] = {n: p.direction.lower() for n, p in entity_port_db[ent].items()}
        else:
            inst_port_dirs[inst.label] = {}

    # Top-entity port directions
    eport_dirs = {p.name: p.direction.lower() for p in fi.ports}

    # Nets: key -> {'label':..., 'eps':[...], 'bundle_base': optional}
    # Endpoints:
    #   ('entity', port_name)
    #   ('inst', inst_label, formal_port)
    #   ('const', value)
    #   ('expr', text)
    nets: Dict[str, Dict] = {}

    def add_ep(netkey: str, label: str, ep, bundle_base: Optional[str]=None):
        if netkey not in nets:
            nets[netkey] = {'label': label, 'eps': [], 'bundle_base': bundle_base}
        nets[netkey]['eps'].append(ep)

    # Instances' port maps
    for inst in fi.instances:
        for formal, actual in (inst.port_map or {}).items():
            kind, label, base = _classify_actual(actual, fi)
            if kind == 'open': continue
            if kind in ('signal','eport'):
                add_ep(f"{kind}::{label}", label, ('inst', inst.label, formal), base)
            elif kind == 'const':
                add_ep(f"const::{label}", label, ('inst', inst.label, formal), None)
            else:
                add_ep(f"expr::{label}", label, ('inst', inst.label, formal), None)

    # Top entity ports participate in their own nets
    for p in fi.ports:
        add_ep(f"eport::{p.name}", p.name, ('entity', p.name), p.name)

    # Concurrent assignments: expr drives target signal
    for a in getattr(fi, "assignments", []):
        add_ep(f"sig::{a.target}", a.target, ('expr', a.expr), a.target)

    # Build nodes
    nodes: List[Dict] = []

    def node(id_, label, kind, inputs=None, outputs=None):
        n = {'id': id_, 'label': label, 'kind': kind}
        if inputs is not None:  n['inputs'] = inputs
        if outputs is not None: n['outputs'] = outputs
        nodes.append(n)

    # Entity port nodes
    for p in fi.ports:
        # Flip semantics per user: IN = drivers, OUT/BUFFER = sinks
        if eport_dirs.get(p.name) == 'in':
            kind = 'entity_in'   # visually on the left
        elif eport_dirs.get(p.name) in ('out','buffer'):
            kind = 'entity_out'  # visually on the right
        else:
            kind = 'entity_bi'
        node(f"port::{p.name}", f"{p.name} ({p.direction})", kind)

    # Instance nodes with pin lists
    for inst in fi.instances:
        title = f"{inst.label} : {(inst.entity_ref or inst.component_name or '?')}"
        pin_dirs = inst_port_dirs.get(inst.label, {})
        formals = list((inst.port_map or {}).keys())
        ins  = [fp for fp in formals if pin_dirs.get(fp, 'in') == 'in']  # unknown -> left
        outs = [fp for fp in formals if pin_dirs.get(fp) in ('out','buffer')]
        node(f"inst::{inst.label}", title, 'instance', inputs=ins, outputs=outs)

    # Materialize const/expr nodes only when used
    for nk, nd in nets.items():
        if nk.startswith('const::'):
            node(f"const::{nd['label']}", nd['label'], 'const')
        if nk.startswith('expr::') and any(ep[0] in ('entity','inst') for ep in nd['eps']):
            node(f"expr::{nd['label']}", nd['label'], 'expr')

    # Build edges
    edges: List[Dict] = []

    def add_edge(src_id, dst_id, label, base=None, src_pin=None, dst_pin=None):
        edges.append({
            'id': f"e{len(edges)}",
            'source': src_id,
            'target': dst_id,
            'label': label,
            'base': base or label,
            'src_pin': src_pin or "",
            'dst_pin': dst_pin or ""
        })

    for nk, nd in nets.items():
        eps = nd['eps']; label = nd['label']; base = nd.get('bundle_base') or nd.get('label')

        drivers: List[Tuple[str, str]] = []  # (node_id, pinlabel)
        sinks:   List[Tuple[str, str]] = []
        unknown: List[Tuple[str, str]] = []

        for ep in eps:
            if ep[0] == 'entity':
                pname = ep[1]; nid = f"port::{pname}"
                dir_ = eport_dirs.get(pname, '')
                # FLIPPED: in = driver; out/buffer = sink; inout = unknown
                if dir_ == 'in':
                    drivers.append((nid, pname))
                elif dir_ in ('out','buffer'):
                    sinks.append((nid, pname))
                else:
                    unknown.append((nid, pname))
            elif ep[0] == 'inst':
                il, fport = ep[1], ep[2]; nid = f"inst::{il}"
                dir_ = inst_port_dirs.get(il, {}).get(fport, '')
                if dir_ in ('out','buffer'):  # instance OUT drives outwards
                    drivers.append((nid, f"{il}.{fport}"))
                elif dir_ == 'in':
                    sinks.append((nid, f"{il}.{fport}"))
                else:
                    unknown.append((nid, f"{il}.{fport}"))
            elif ep[0] == 'expr':
                nid = f"expr::{ep[1]}"; drivers.append((nid, ep[1]))
            elif ep[0] == 'const':
                nid = f"const::{label}"; drivers.append((nid, label))

        if drivers and sinks:
            for d_id, d_pin in drivers:
                for s_id, s_pin in sinks:
                    add_edge(d_id, s_id, label, base=base, src_pin=d_pin, dst_pin=s_pin)
        else:
            # Unknown topology: conservative left->right chain
            flat = drivers + sinks + unknown
            uniq = []
            seen = set()
            for nid, pin in flat:
                if (nid, pin) not in seen:
                    seen.add((nid, pin)); uniq.append((nid, pin))
            for i in range(len(uniq)-1):
                add_edge(uniq[i][0], uniq[i+1][0], label, base=base,
                         src_pin=uniq[i][1], dst_pin=uniq[i+1][1])

    # Bundling indices for edges sharing same (source,target)
    groups: Dict[Tuple[str,str], List[int]] = {}
    for i, e in enumerate(edges):
        key = (e['source'], e['target'])
        groups.setdefault(key, []).append(i)
    for key, idxs in groups.items():
        n = len(idxs)
        for k, ei in enumerate(idxs):
            edges[ei]['bundle_n'] = n
            edges[ei]['bundle_idx'] = k

    return {'nodes': nodes, 'edges': edges}
