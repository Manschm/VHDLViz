from typing import Dict, List, Tuple, Optional
from model import FileInfo, Port

def _port_dir_map_for_entity(entity_ports: List[Port]) -> Dict[str, str]:
    return {p.name: p.direction.lower() for p in entity_ports}

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
    # name(7 downto 0) | name(i) | name
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
      label is display
      bundle_base helps group e.g. data(3), data(7 downto 0) under 'data'
    """
    a = _strip_outer_parens(actual)
    al = a.lower()
    if al == 'open': return ('open', a, None)
    if al in ('0','1') or al.startswith("'") or al.startswith('"') or al.startswith('x"') or al.startswith('b"'):
        return ('const', a, None)

    names_sig = {s.name for s in fi.signals}
    names_e = {p.name for p in fi.ports}

    base, sl = _split_base_slice(a)
    if base in names_sig:
        return ('signal', a, base)
    if base in names_e:
        return ('eport', a, base)
    return ('expr', a, None)

def build_wiring(fi: FileInfo,
                 entity_port_db: Dict[str, Dict[str, Port]]) -> Dict:
    """Return dict with nodes, edges; edges include meta for tooltips and bundling indices."""
    # Instance port directions when entity known
    inst_port_dirs: Dict[str, Dict[str, str]] = {}
    for inst in fi.instances:
        ent = inst.entity_ref or inst.component_name
        if ent and ent in entity_port_db:
            inst_port_dirs[inst.label] = {n: p.direction.lower() for n, p in entity_port_db[ent].items()}
        else:
            inst_port_dirs[inst.label] = {}

    eport_dirs = _port_dir_map_for_entity(fi.ports)

    # Collect nets: key -> {'label':..., 'eps':[...], 'bundle_base': optional}
    # ep forms:
    #   ('entity', port_name)
    #   ('inst', inst_label, formal_port)
    #   ('const', value)
    #   ('expr', text)
    nets: Dict[str, Dict] = {}

    def add_ep(netkey: str, label: str, ep, bundle_base: Optional[str]=None):
        if netkey not in nets:
            nets[netkey] = {'label': label, 'eps': [], 'bundle_base': bundle_base}
        nets[netkey]['eps'].append(ep)

    # Instance portmaps
    for inst in fi.instances:
        for formal, actual in (inst.port_map or {}).items():
            kind, label, base = _classify_actual(actual, fi)
            if kind == 'open': continue
            if kind in ('signal','eport'):
                k = f"{kind}::{label}"
                add_ep(k, label, ('inst', inst.label, formal), base)
            elif kind == 'const':
                k = f"const::{label}"
                add_ep(k, label, ('inst', inst.label, formal), None)
            else:
                k = f"expr::{label}"
                add_ep(k, label, ('inst', inst.label, formal), None)

    # Top-entity ports participate on their own net
    for p in fi.ports:
        k = f"eport::{p.name}"
        add_ep(k, p.name, ('entity', p.name), p.name)

    # Concurrent assignments (drivers for internal signals)
    for a in fi.assignments:
        # driver is the expression; target is the net (signal)
        k = f"sig::{a.target}"
        add_ep(k, a.target, ('expr', a.expr), a.target)

    # Node inventory
    nodes = []
    def node(id_, label, kind):
        nodes.append({'id': id_, 'label': label, 'kind': kind})

    # Ports
    for p in fi.ports:
        kind = 'entity_in' if eport_dirs.get(p.name) == 'in' else ('entity_out' if eport_dirs.get(p.name) in ('out','buffer') else 'entity_bi')
        node(f"port::{p.name}", f"{p.name} ({p.direction})", kind)

    # Instances
    for inst in fi.instances:
        title = f"{inst.label} : {(inst.entity_ref or inst.component_name or '?')}"
        node(f"inst::{inst.label}", title, 'instance')

    # Const/expr nodes (created when needed)
    for nk, nd in nets.items():
        if nk.startswith('const::'):
            node(f"const::{nd['label']}", nd['label'], 'const')
        if nk.startswith('expr::') and any(ep[0]=='entity' or ep[0]=='inst' for ep in nd['eps']):
            # only materialize expr nodes if they connect to something meaningful
            node(f"expr::{nd['label']}", nd['label'], 'expr')

    edges: List[Dict] = []

    # Helper to add labeled edge with tooltip meta
    def add_edge(src_id, dst_id, label, src_pin=None, dst_pin=None, base=None):
        edges.append({
            'id': f"e{len(edges)}",
            'source': src_id,
            'target': dst_id,
            'label': label,
            'meta': f"{(src_pin or '')} → {(dst_pin or '')}".strip(" →"),
            'base': base or label
        })

    # Build driver/sink partition and decide hub usage
    for nk, nd in nets.items():
        eps = nd['eps']; label = nd['label']; base = nd.get('bundle_base') or nd.get('label')
        drivers, sinks, unknown = [], [], []

        for ep in eps:
            if ep[0] == 'entity':
                pname = ep[1]; nid = f"port::{pname}"; dir_ = eport_dirs.get(pname, '')
                if dir_ in ('out','buffer'): drivers.append((nid, pname))
                elif dir_ == 'in': sinks.append((nid, pname))
                else: unknown.append((nid, pname))
            elif ep[0] == 'inst':
                il, fport = ep[1], ep[2]; nid = f"inst::{il}"; dir_ = inst_port_dirs.get(il, {}).get(fport, '')
                if dir_ in ('out','buffer'): drivers.append((nid, f"{il}.{fport}"))
                elif dir_ == 'in': sinks.append((nid, f"{il}.{fport}"))
                else: unknown.append((nid, f"{il}.{fport}"))
            elif ep[0] == 'expr':
                nid = f"expr::{ep[1]}"; drivers.append((nid, ep[1]))
            elif ep[0] == 'const':
                nid = f"const::{label}"; drivers.append((nid, label))

        # materialize hub for multi-fan nets
        need_hub = (len(drivers) + len(sinks) + len(unknown) >= 3) or (len(sinks) >= 2 and len(drivers) >= 1) or (len(drivers) >= 2)
        hub_id = None
        if need_hub and (nk.startswith('sig::') or nk.startswith('eport::')):
            hub_id = f"net::{label}"
            # small circular net node
            if not any(n['id'] == hub_id for n in nodes):
                nodes.append({'id': hub_id, 'label': label, 'kind': 'net'})

        if hub_id:
            # drivers -> hub ; hub -> sinks ; unknown chain via hub
            for d_id, d_pin in (drivers or unknown[:1] or []):
                add_edge(d_id, hub_id, label, src_pin=d_pin, base=base)
            for s_id, s_pin in (sinks or unknown[1:] if drivers or unknown else []):
                add_edge(hub_id, s_id, label, dst_pin=s_pin, base=base)
        else:
            # No hub: connect each driver to each sink; else chain unknowns
            if drivers and sinks:
                for d_id, d_pin in drivers:
                    for s_id, s_pin in sinks:
                        add_edge(d_id, s_id, label, d_pin, s_pin, base)
            else:
                ids = [drivers, sinks, unknown]
                flat = [x for grp in ids for x in grp]
                uniq = []
                seen = set()
                for nid, pin in flat:
                    if (nid, pin) not in seen:
                        seen.add((nid, pin)); uniq.append((nid, pin))
                for i in range(len(uniq)-1):
                    add_edge(uniq[i][0], uniq[i+1][0], label, uniq[i][1], uniq[i+1][1], base)

    # Bundling indices for edges sharing same (source,target)
    groups: Dict[Tuple[str,str], List[int]] = {}
    for i, e in enumerate(edges):
        key = (e['source'], e['target'])
        groups.setdefault(key, []).append(i)
    for key, idxs in groups.items():
        n = len(idxs)
        for k, ei in enumerate(idxs):
            edges[ei]['bundle_n'] = n
            edges[ei]['bundle_idx'] = k  # 0..n-1

    return {'nodes': nodes, 'edges': edges}
