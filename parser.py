from pathlib import Path
from typing import List
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

def _parse_portmap(pmap_blob: str):
    pm = {}
    if not pmap_blob:
        return pm
    for kv in patterns.PMAP_KV_RE.finditer(pmap_blob):
        pm[kv.group("formal").strip()] = kv.group("actual").strip()
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
