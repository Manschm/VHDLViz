from typing import Dict, List, Tuple, Optional
from model import FileInfo, Port, Instance

def _port_dir_map_for_entity(entity_ports: List[Port]) -> Dict[str, str]:
    return {p.name: p.direction.lower() for p in entity_ports}

def _strip_outer_parens(s: str) -> str:
    t = s.strip()
    while t.startswith('(') and t.endswith(')'):
        # naive check to avoid stripping mismatched cases
        depth = 0
        ok = True
        for i, ch in enumerate(t):
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth < 0:
                    ok = False; break
        if ok and depth == 0:
            t = t[1:-1].strip()
        else:
            break
    return t

def _classify_actual(actual: str, fi: FileInfo) -> Tuple[str, str]:
    """
    Return (kind, name) where kind in:
      - 'signal' (internal signal)
      - 'eport'  (entity port name)
      - 'const'  (literals, e.g. '0', '1', "'0'", "x\"AA\"")
      - 'expr'   (everything else: slices, casts, ops, concatenations)
      - 'open'   (explicit open)
    """
    a = _strip_outer_parens(actual)
    al = a.lower()

    if al == 'open':
        return ('open', a)

    # crude literal detection
    if al in ('0', '1') or al.startswith("'") or al.startswith('"') or al.startswith('x"') or al.startswith('b"'):
        return ('const', a)

    # match by name to internal signals or entity ports
    names_sig = {s.name for s in fi.signals}
    names_eports = {p.name for p in fi.ports}

    # token up to first space, allow slices like name(7 downto 0)
    base = a.split()[0]
    base_id = base.split('(')[0]

    if base_id in names_sig:
        return ('signal', base_id)
    if base_id in names_eports:
        return ('eport', base_id)

    # otherwise expression (slice/cast/unary/bus concat/etc.)
    return ('expr', a)

def build_wiring(fi: FileInfo,
                 entity_port_db: Dict[str, Dict[str, Port]]) -> Dict:
    """
    Build a wiring model for a single file (architecture scope).
    entity_port_db: entity_name -> {port_name: Port}
    Returns a dict: { 'nodes': [...], 'edges': [...] }
    Node ids:
      - port::<name>
      - inst::<label>
      - const::<value>
      - expr::<expr>
    """
    # Map instance label -> (entity_name, port_dir_map)
    inst_dirs: Dict[str, Dict[str, str]] = {}
    for inst in fi.instances:
        ent = inst.entity_ref or inst.component_name
        pmap = {}
        if ent and ent in entity_port_db:
            pmap = {n: p.direction.lower() for n, p in entity_port_db[ent].items()}
        inst_dirs[inst.label] = pmap

    # Build net participation: net_key -> list of endpoints
    # Endpoint as tuple ('entity', name) or ('inst', label, portname) or ('const', val) or ('expr', expr)
    nets: Dict[str, Dict] = {}

    def add_endpoint(netkey: str, label: str, ep):
        if netkey not in nets:
            nets[netkey] = {'label': label, 'eps': []}
        nets[netkey]['eps'].append(ep)

    # 1) entity ports create their own "net" names (so a port can directly connect)
    eport_dirs = {p.name: p.direction.lower() for p in fi.ports}

    # 2) instances port maps
    for inst in fi.instances:
        ent = inst.entity_ref or inst.component_name
        for formal, actual in (inst.port_map or {}).items():
            kind, name = _classify_actual(actual, fi)
            if kind == 'open':
                continue
            if kind == 'signal':
                netkey = f"sig::{name}"
                add_endpoint(netkey, name, ('inst', inst.label, formal))
                # Also add entity port endpoints if the same signal name equals a top-level port
                # (not necessary: connections via eports are added by their own net below)
            elif kind == 'eport':
                netkey = f"eport::{name}"
                add_endpoint(netkey, name, ('inst', inst.label, formal))
            elif kind == 'const':
                netkey = f"const::{name}"
                add_endpoint(netkey, name, ('inst', inst.label, formal))
            else:  # expr
                netkey = f"expr::{name}"
                add_endpoint(netkey, name, ('inst', inst.label, formal))

    # 3) entity ports net participation from the perspective of the top entity itself
    for p in fi.ports:
        netkey = f"eport::{p.name}"
        add_endpoint(netkey, p.name, ('entity', p.name))

    # Produce nodes
    nodes = []
    def node(id_, label, kind):
        nodes.append({'id': id_, 'label': label, 'kind': kind})

    # Entity input/output nodes
    for p in fi.ports:
        k = 'entity_in' if p.direction.lower() in ('in',) else ('entity_out' if p.direction.lower() in ('out', 'buffer') else 'entity_bi')
        node(f"port::{p.name}", f"{p.name} ({p.direction})", k)

    # Instance nodes
    for inst in fi.instances:
        title = f"{inst.label} : {(inst.entity_ref or inst.component_name or '?')}"
        node(f"inst::{inst.label}", title, 'instance')

    # Const / expr nodes will be created lazily only if used as standalone drivers (no need if they only feed into an inst alongside an entity port)
    # But for clarity, add them now when they appear as nets with no eport endpoints.
    for netkey, nd in list(nets.items()):
        if netkey.startswith('const::'):
            node(f"const::{nd['label']}", nd['label'], 'const')
        if netkey.startswith('expr::'):
            node(f"expr::{nd['label']}", nd['label'], 'expr')

    # Build edges (driver -> sink), default to left->right chain if unknown
    edges = []
    def add_edge(src_id, dst_id, label):
        edges.append({'id': f"e{len(edges)}", 'source': src_id, 'target': dst_id, 'label': label})

    for netkey, nd in nets.items():
        eps = nd['eps']
        label = nd['label']
        # Determine drivers/sinks
        drivers = []
        sinks = []
        unknown = []

        for ep in eps:
            if ep[0] == 'entity':
                pname = ep[1]
                dir_ = eport_dirs.get(pname, '')
                nid = f"port::{pname}"
                if dir_ in ('out', 'buffer'):
                    drivers.append((nid, f"{pname}"))
                elif dir_ == 'in':
                    sinks.append((nid, f"{pname}"))
                else:
                    unknown.append((nid, f"{pname}"))
            elif ep[0] == 'inst':
                ilabel, fport = ep[1], ep[2]
                nid = f"inst::{ilabel}"
                dir_ = inst_dirs.get(ilabel, {}).get(fport, '')
                if dir_ in ('out', 'buffer'):
                    drivers.append((nid, f"{ilabel}.{fport}"))
                elif dir_ == 'in':
                    sinks.append((nid, f"{ilabel}.{fport}"))
                else:
                    unknown.append((nid, f"{ilabel}.{fport}"))
            elif ep[0] == 'const':
                nid = f"const::{label}"
                drivers.append((nid, label))
            elif ep[0] == 'expr':
                nid = f"expr::{label}"
                drivers.append((nid, label))

        if drivers and sinks:
            src = drivers[0][0]
            for dst, _ in sinks:
                add_edge(src, dst, label)
            # connect remaining drivers to first driver (to visualize multi-driver nets)
            for d2, _ in drivers[1:]:
                add_edge(d2, src, label)
        else:
            # unknown topology: connect in a simple chain left->right across endpoints
            ids = [ (f"port::{ep[1]}", ep) if ep[0]=='entity'
                    else (f"inst::{ep[1]}", ep) if ep[0]=='inst'
                    else (f"{ep[0]}::{label}", ep)
                    for ep in eps ]
            # dedup
            seen, order = set(), []
            for nid, _ in ids:
                if nid not in seen:
                    seen.add(nid); order.append(nid)
            for i in range(len(order)-1):
                add_edge(order[i], order[i+1], label)

    return {'nodes': nodes, 'edges': edges}
