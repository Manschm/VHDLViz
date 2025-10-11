from pathlib import Path
from typing import List, Tuple
from model import FileInfo, Port, Signal, Instance
import patterns

def _parse_ports(port_blob: str) -> List[Port]:
    ports: List[Port] = []
    if not port_blob:
        return ports
    for m in patterns.PORT_LINE_RE.finditer(port_blob):
        names = [n.strip() for n in m.group("names").split(",") if n.strip()]
        direction = m.group("dir").strip()
        dtype = " ".join(m.group("dtype").split())  # compact spaces
        for nm in names:
            ports.append(Port(name=nm, direction=direction, dtype=dtype))
    return ports

def _split_assoc_list(s: str) -> List[str]:
    """Split 'a=>b(c,d), x=>y' by commas not inside (), [], {}, or quotes."""
    parts, buf, depth = [], [], 0
    in_str = False
    quote = ''
    i = 0
    while i < len(s):
        ch = s[i]
        if in_str:
            buf.append(ch)
            if ch == quote:
                in_str = False
            elif ch == '\\' and i + 1 < len(s):
                buf.append(s[i+1]); i += 1
        else:
            if ch in ('"', "'"):
                in_str = True; quote = ch; buf.append(ch)
            elif ch in '([{':
                depth += 1; buf.append(ch)
            elif ch in ')]}':
                depth = max(0, depth - 1); buf.append(ch)
            elif ch == ',' and depth == 0:
                parts.append(''.join(buf).strip()); buf = []
            else:
                buf.append(ch)
        i += 1
    if buf:
        parts.append(''.join(buf).strip())
    return [p for p in parts if p]

def _parse_portmap(pmap_blob: str):
    pm = {}
    if not pmap_blob:
        return pm
    for item in _split_assoc_list(pmap_blob):
        if '=>' not in item:
            continue
        formal, actual = item.split('=>', 1)
        formal = formal.strip()
        if formal.lower() == 'others':
            continue
        pm[formal] = actual.strip()
    return pm

def parse_vhdl_file(path: Path, text: str) -> FileInfo:
    entity_name = None
    ports: List[Port] = []
    signals: List[Signal] = []
    instances: List[Instance] = []

    # ENTITY + PORTS
    em = patterns.ENTITY_RE.search(text)
    if em:
        entity_name = em.group("name")
        ports = _parse_ports(em.group("ports") or "")

    # SIGNALS
    for sm in patterns.SIGNAL_RE.finditer(text):
        signals.append(Signal(name=sm.group("name"), dtype=" ".join(sm.group("dtype").split())))

    # COMPONENT-STYLE INSTANCES
    for im in patterns.COMP_INST_RE.finditer(text):
        label = im.group("label")
        comp = im.group("comp")
        pmap = _parse_portmap(im.group("pmap") or "")
        instances.append(Instance(label=label, component_name=comp, entity_ref=None, port_map=pmap))

    # DIRECT ENTITY INSTANCES
    for im in patterns.ENTITY_INST_RE.finditer(text):
        label = im.group("label")
        ent = im.group("ent")
        pmap = _parse_portmap(im.group("pmap") or "")
        instances.append(Instance(label=label, component_name=None, entity_ref=ent, port_map=pmap))

    return FileInfo(path=path, entity_name=entity_name, ports=ports, signals=signals, instances=instances)
