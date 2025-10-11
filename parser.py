from pathlib import Path
from typing import List
from model import FileInfo, Port, Signal, Instance, Assignment
import patterns
import re

def _strip_comments(text: str) -> str:
    # VHDL comments are '--' to end of line
    return re.sub(r'--.*?$', '', text, flags=re.MULTILINE)

def _split_assoc_list(s: str) -> List[str]:
    parts, buf, depth = [], [], 0
    in_str = False; quote = ''
    i = 0
    while i < len(s):
        ch = s[i]
        if in_str:
            buf.append(ch)
            if ch == quote:
                in_str = False
            elif ch == '\\' and i+1 < len(s):
                buf.append(s[i+1]); i += 1
        else:
            if ch in ('"', "'"):
                in_str = True; quote = ch; buf.append(ch)
            elif ch in '([{':
                depth += 1; buf.append(ch)
            elif ch in ')]}':
                depth = max(0, depth-1); buf.append(ch)
            elif ch == ',' and depth == 0:
                parts.append(''.join(buf).strip()); buf = []
            else:
                buf.append(ch)
        i += 1
    if buf: parts.append(''.join(buf).strip())
    return [p for p in parts if p]

def _parse_portmap(pmap_blob: str):
    pm = {}
    if not pmap_blob: return pm
    for item in _split_assoc_list(pmap_blob):
        if '=>' not in item: continue
        formal, actual = item.split('=>', 1)
        formal = formal.strip()
        if formal.lower() == 'others': continue
        pm[formal] = actual.strip()
    return pm

def _parse_ports(port_blob: str) -> List[Port]:
    ports: List[Port] = []
    if not port_blob: return ports
    for m in patterns.PORT_LINE_RE.finditer(port_blob):
        names = [n.strip() for n in m.group("names").split(",") if n.strip()]
        direction = m.group("dir").strip()
        dtype = " ".join(m.group("dtype").split())
        for nm in names:
            ports.append(Port(name=nm, direction=direction, dtype=dtype))
    return ports

def parse_vhdl_file(path: Path, raw_text: str) -> FileInfo:
    text = _strip_comments(raw_text)
    entity_name = None
    ports: List[Port] = []
    signals: List[Signal] = []
    instances: List[Instance] = []
    assignments: List[Assignment] = []

    em = patterns.ENTITY_RE.search(text)
    if em:
        entity_name = em.group("name")
        ports = _parse_ports(em.group("ports") or "")

    for sm in patterns.SIGNAL_RE.finditer(text):
        signals.append(Signal(name=sm.group("name"),
                              dtype=" ".join(sm.group("dtype").split())))

    for im in patterns.COMP_INST_RE.finditer(text):
        instances.append(Instance(
            label=im.group("label"),
            component_name=im.group("comp"),
            entity_ref=None,
            port_map=_parse_portmap(im.group("pmap") or "")
        ))

    for im in patterns.ENTITY_INST_RE.finditer(text):
        instances.append(Instance(
            label=im.group("label"),
            component_name=None,
            entity_ref=im.group("ent"),
            port_map=_parse_portmap(im.group("pmap") or "")
        ))

    # NEW: concurrent assignments (naive but effective)
    for am in patterns.ASSIGN_RE.finditer(text):
        lhs = am.group("lhs").strip()
        expr = " ".join(am.group("expr").split())
        if lhs: assignments.append(Assignment(target=lhs, expr=expr))

    return FileInfo(path=path, entity_name=entity_name,
                    ports=ports, signals=signals,
                    instances=instances, assignments=assignments)
