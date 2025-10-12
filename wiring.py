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
    -> (kind, display_label, base_for_grouping)
       kind in {'signal','eport','const','expr','open'}
       display_label keeps slices (e.g., 'data(0)')
       base_for_grouping e.g. 'data' for eport/signal; None for const/expr/open
    """
    a = _strip_outer_parens(actual)
    al = a.lower()
    if al == 'open': return ('open', a, None)
    if al in ('0','1') or al.startswith("'") or al.startswith('"') or al.startswith('x"') or al.startswith('b"'):
        return ('const', a, None)

    sig_names = {s.name for s in fi.signals}
    eport_names = {p.name for p in fi.ports}
    base, _ = _split_base_slice(a)

    if base in sig_names:   return ('signal', a, base)
    if base in eport_names: return ('eport', a, base)
    return ('expr', a, None)

def build_wiring(fi: FileInfo,
                 entity_port_db: Dict[str, Dict[str, Port]]) -> Dict:
    """
    Build nodes (with pin lists) and edges. Entity INs are drivers; OUTs are sinks.
    Nets for eports/signals are keyed by base name so slices connect correctly.
    """
    # Instance port dirs (if entity known)
    inst_port_dirs: Dict[str, Dict[str, str]] = {}
    for inst in fi.instances:
        ent = inst.entity_ref or inst.component_name
        if ent and ent in entity_port_db:
            inst_port_dirs[inst.label] = {n: p.direction.lower() for n, p in entity_port_db[ent].items()}
        else:
            inst_port_dirs[inst.label] = {}

    eport_dirs = {p.name: p.direction.lower() for p in fi.ports}

    # Nets: (kind, base) -> {'base':base, 'eps': [(ep, label)]}
    # ep = ('entity', port) | ('inst', label, formal) | ('const', val) | ('expr', text)
    nets: Dict[Tuple[str, str], Dict] = {}

    def add_ep(kind: str, base: str, ep, label: str):
        key = (kind, base)
        if key not in nets:
            nets[key] = {'base': base, 'eps': []}
        nets[key]['eps'].append((ep, label))

    # Instances port maps
    for inst in fi.instances:
        for formal, actual in (inst.port_map or {}).items():
            kind, label, base = _classify_actual(actual, fi)
            if kind == 'open': continue
            if kind in ('signal', 'eport') and base is not None:
                add_ep(kind, base, ('inst', inst.label, formal), label)
            elif kind == 'const':
                add_ep('const', label, ('inst', inst.label, formal), label)
            else:
                add_ep('expr', label, ('inst', inst.label, formal), label)

    # Top entity ports (key by base=port name)
    for p in fi.ports:
        add_ep('eport', p.name, ('entity', p.name), p.name)

    # Concurrent assignments: target may be sliced; driver is expr
    for a in getattr(fi, "assignments", []):
        tbase, _ = _split_base_slice(a["target"] if isinstance(a, dict) else a.target)
        label = a["target"] if isinstance(a, dict) else a.target
        expr  = a["expr"]   if isinstance(a, dict) else a.expr
        if tbase:
            # include kind/meta in label for sidebar/tooltip clarity
            tagged = expr
            if isinstance(a, dict):
                k = a.get("kind","")
                if k == "cond":
                    tagged += "  -- conditional"
                elif k == "select":
                    tagged += "  -- with-select"
                elif k == "proc":
                    tagged += "  -- process"
            add_ep('signal', tbase, ('expr', tagged), label)

    # Nodes
    nodes: List[Dict] = []

    def node(id_, label, kind, inputs=None, outputs=None):
        n = {'id': id_, 'label': label, 'kind': kind}
        if inputs is not None:  n['inputs'] = inputs
        if outputs is not None: n['outputs'] = outputs
        nodes.append(n)

    # Entity ports
    for p in fi.ports:
        if eport_dirs.get(p.name) == 'in':
            kind = 'entity_in'
        elif eport_dirs.get(p.name) in ('out','buffer'):
            kind = 'entity_out'
        else:
            kind = 'entity_bi'
        node(f"port::{p.name}", f"{p.name} ({p.direction})", kind)

    # Instances with pin lists
    for inst in fi.instances:
        title = f"{inst.label} : {(inst.entity_ref or inst.component_name or '?')}"
        pin_dirs = inst_port_dirs.get(inst.label, {})
        formals = list((inst.port_map or {}).keys())
        ins  = [fp for fp in formals if pin_dirs.get(fp, 'in') == 'in']  # unknown -> left
        outs = [fp for fp in formals if pin_dirs.get(fp) in ('out','buffer')]
        node(f"inst::{inst.label}", title, 'instance', inputs=ins, outputs=outs)

    # Const/expr nodes (only when connected)
    for (kind, base), nd in nets.items():
        if kind == 'const':
            node(f"const::{base}", base, 'const')
        if kind == 'expr' and any(ep[0] in ('entity','inst') for ep,_ in nd['eps']):
            node(f"expr::{base}", base, 'expr')

    # Edges
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

    for (kind, base), nd in nets.items():
        drivers: List[Tuple[str, str, str]] = []  # (node_id, pinlabel, ep_label)
        sinks:   List[Tuple[str, str, str]] = []
        unknown: List[Tuple[str, str, str]] = []

        for ep, ep_label in nd['eps']:
            if ep[0] == 'entity':
                pname = ep[1]; nid = f"port::{pname}"; dir_ = eport_dirs.get(pname, '')
                # FLIPPED semantics: IN = driver, OUT/BUFFER = sink
                if dir_ == 'in':
                    drivers.append((nid, pname, ep_label))
                elif dir_ in ('out','buffer'):
                    sinks.append((nid, pname, ep_label))
                else:
                    unknown.append((nid, pname, ep_label))
            elif ep[0] == 'inst':
                il, fport = ep[1], ep[2]; nid = f"inst::{il}"
                dir_ = inst_port_dirs.get(il, {}).get(fport, '')
                if dir_ in ('out','buffer'):
                    drivers.append((nid, f"{il}.{fport}", ep_label))
                elif dir_ == 'in':
                    sinks.append((nid, f"{il}.{fport}", ep_label))
                else:
                    unknown.append((nid, f"{il}.{fport}", ep_label))
            elif ep[0] == 'expr':
                nid = f"expr::{ep[1]}"
                drivers.append((nid, ep[1], ep_label))
            elif ep[0] == 'const':
                nid = f"const::{base}"
                drivers.append((nid, base, ep_label))

        if drivers and sinks:
            for d_id, d_pin, d_lab in drivers:
                for s_id, s_pin, s_lab in sinks:
                    # Prefer sink label (slice) for edge text; fallback to driver label; else base
                    lab = s_lab or d_lab or base
                    add_edge(d_id, s_id, lab, base=base, src_pin=d_pin, dst_pin=s_pin)
        else:
            # Conservative chain
            flat = drivers + sinks + unknown
            uniq = []
            seen = set()
            for nid, pin, lab in flat:
                if (nid, pin) not in seen:
                    seen.add((nid, pin)); uniq.append((nid, pin, lab))
            for i in range(len(uniq)-1):
                lab = uniq[i+1][2] or uniq[i][2] or base
                add_edge(uniq[i][0], uniq[i+1][0], lab, base=base,
                         src_pin=uniq[i][1], dst_pin=uniq[i+1][1])

    # Bundle indices for (source,target)
    groups: Dict[Tuple[str,str], List[int]] = {}
    for i, e in enumerate(edges):
        key = (e['source'], e['target'])
        groups.setdefault(key, []).append(i)
    for key, idxs in groups.items():
        n = len(idxs)
        for k, ei in enumerate(idxs):
            edges[ei]['bundle_n']  = n
            edges[ei]['bundle_idx'] = k

    return {'nodes': nodes, 'edges': edges}
