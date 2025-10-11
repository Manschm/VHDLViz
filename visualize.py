import json, pathlib
from typing import Dict
from model import FileInfo, Port
from wiring import build_wiring

def _load_template(name: str) -> str:
    here = pathlib.Path(__file__).parent
    return (here / "html" / name).read_text(encoding="utf-8")

def write_dependency_html(out_path: pathlib.Path, db):
    tpl = _load_template("dep_template.html")
    nodes = []
    id_for = {}
    for i, f in enumerate(db.files):
        fid = f"f{i}"
        id_for[str(f.path)] = fid
        label = f.entity_name or pathlib.Path(f.path).name
        nodes.append({"data": {"id": fid, "label": label, "path": str(f.path)}})
    edges = []
    for src, dst in db.dependencies:
        if src in id_for and dst in id_for:
            edges.append({"data": {"id": f"e_{id_for[src]}_{id_for[dst]}",
                                   "source": id_for[src], "target": id_for[dst]}})
    payload = {"nodes": nodes, "edges": edges}
    out_path.write_text(tpl.replace("/*__DATA__*/", json.dumps(payload)), encoding="utf-8")

def write_block_html(out_path: pathlib.Path, fi: FileInfo, entity_port_db: Dict[str, Dict[str, Port]]):
    tpl = _load_template("block_template.html")
    graph = build_wiring(fi, entity_port_db)
    payload = {
        "file": {"path": str(fi.path), "entity": fi.entity_name or fi.path.stem},
        "ports": [p.__dict__ for p in fi.ports],
        "signals": [s.__dict__ for s in fi.signals],
        "instances": [
            {
                "label": inst.label,
                "component_name": inst.component_name,
                "entity_ref": inst.entity_ref,
                "port_map": inst.port_map
            } for inst in fi.instances
        ],
        "graph": graph
    }
    out_path.write_text(tpl.replace("/*__BLOCK_DATA__*/", json.dumps(payload)), encoding="utf-8")
