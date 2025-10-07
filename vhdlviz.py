#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path
from collections import defaultdict

# Import regex patterns and tiny helpers from a single place
try:
    from patterns import RX
except Exception as e:
    print("[vhdlviz] Failed to import patterns.py:", e, file=sys.stderr)
    sys.exit(1)


# ---------- Models ----------
class Instance:
    __slots__ = ("label", "type", "kind", "ports")

    def __init__(self, label, type_, kind, ports):
        self.label = label  # instance label in VHDL
        self.type = type_  # entity/component name
        self.kind = kind  # "entity" | "component" | "unknown"
        self.ports = ports or {}  # {formal: actual}


class FileModel:
    __slots__ = ("path", "entities", "signals", "instances")

    def __init__(self, path):
        self.path = str(path)
        self.entities = set()  # entity names defined here
        self.signals = {}  # name -> type string
        self.instances = []  # list[Instance]


# ---------- Parsing ----------


def parse_vhdl_text(text):
    # Normalize comments out to simplify parsing (keep line count roughly)
    no_sl_comment = RX["LINE_COMMENT"].sub("", text)
    core = RX["BLOCK_COMMENT"].sub(
        lambda m: "\n" * m.group(0).count("\n"), no_sl_comment
    )

    entities = set(n for n in RX["ENTITY_DEF"].findall(core))

    # Signals declared at architecture declarative region or globally in package bodies
    signals = {}
    for name, typ in RX["SIGNAL_DECL"].findall(core):
        signals[name] = RX["WS"].sub(" ", typ.strip())

    instances = []
    for m in RX["COMP_OR_ENTITY_INST"].finditer(core):
        label = m.group("label")
        type_ = m.group("type")
        kind = (
            "entity"
            if (m.group("is_entity") or "").strip().lower().startswith("entity")
            else "component"
        )
        ports_txt = m.group("ports") or ""
        ports = {}
        for f, a in RX["PORT_ASSOC"].findall(ports_txt):
            ports[f] = a.strip()
        instances.append(Instance(label, type_, kind, ports))

    return entities, signals, instances


def parse_file(path: Path) -> FileModel:
    try:
        txt = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        txt = path.read_text(encoding="latin-1", errors="ignore")
    model = FileModel(path)
    ents, sigs, insts = parse_vhdl_text(txt)
    model.entities = set(ents)
    model.signals = sigs
    model.instances = insts
    return model


# ---------- Graph building ----------


def build_index(files):
    entity_to_file = {}
    for f in files:
        for e in f.entities:
            entity_to_file[e] = f.path
    return entity_to_file


def build_dependencies(files, entity_to_file):
    deps = []  # edges: {source: fileA, target: fileB, via: entity}
    for f in files:
        for inst in f.instances:
            # prefer entity mapping; if component with same name as entity exists, it will match too
            tgt = entity_to_file.get(inst.type)
            if tgt and tgt != f.path:
                deps.append({"source": f.path, "target": tgt, "via": inst.type})
    return deps


# ---------- Export ----------


def collect_payload(files, deps):
    # Shape payload with all details needed by the HTML template
    files_payload = []
    structures = {}

    for f in files:
        files_payload.append(
            {
                "path": f.path,
                "entities": sorted(list(f.entities)),
                "num_signals": len(f.signals),
                "num_instances": len(f.instances),
            }
        )
        instances = []
        for inst in f.instances:
            instances.append(
                {
                    "label": inst.label,
                    "type": inst.type,
                    "kind": inst.kind,
                    "ports": inst.ports,
                }
            )
        structures[f.path] = {
            "signals": f.signals,  # name -> type
            "instances": instances,  # list
        }

    return {
        "files": files_payload,
        "deps": deps,
        "structures": structures,
    }


def write_html(output_path: Path, payload: dict, template_path: Path):
    html = template_path.read_text(encoding="utf-8")
    injected = html.replace("/*__DATA__*/", json.dumps(payload))
    output_path.write_text(injected, encoding="utf-8")


# ---------- CLI ----------


def find_vhdl_files(root_paths):
    exts = {".vhd", ".vhdl"}
    files = []
    for root in root_paths:
        root_p = Path(root)
        if root_p.is_file() and root_p.suffix.lower() in exts:
            files.append(root_p)
        elif root_p.is_dir():
            for p in root_p.rglob("*"):
                if p.is_file() and p.suffix.lower() in exts:
                    files.append(p)
    return sorted(files)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="VHDL Visualizer – export interactive HTML of dependencies + in-file structure"
    )
    ap.add_argument(
        "-i",
        "--inputs",
        nargs="+",
        required=True,
        help="Folders and/or .vhd/.vhdl files to scan",
    )
    ap.add_argument("-o", "--output", required=True, help="Output HTML path")
    ap.add_argument(
        "--template",
        default=str(Path(__file__).with_name("template.html")),
        help="Path to template.html",
    )
    args = ap.parse_args(argv)

    inputs = args.inputs
    out = Path(args.output)
    template = Path(args.template)

    vhdl_paths = find_vhdl_files(inputs)
    if not vhdl_paths:
        print("[vhdlviz] No VHDL files found in given inputs.", file=sys.stderr)
        return 2

    print(f"[vhdlviz] Scanning {len(vhdl_paths)} VHDL files…")
    models = []
    for p in vhdl_paths:
        m = parse_file(p)
        models.append(m)

    idx = build_index(models)
    deps = build_dependencies(models, idx)
    payload = collect_payload(models, deps)

    out.parent.mkdir(parents=True, exist_ok=True)
    write_html(out, payload, template)
    print(f"[vhdlviz] Wrote {out}  (open in a browser)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
