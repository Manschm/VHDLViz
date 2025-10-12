#!/usr/bin/env python3
import argparse, json, sys, os, pathlib
from parser import parse_vhdl_file
from model import DesignDB, FileInfo, Port
from visualize import write_dependency_html, write_block_html, write_designer_html

def discover_files(roots):
    exts = {".vhd", ".vhdl"}
    files = []
    for root in roots:
        rootp = pathlib.Path(root)
        if not rootp.exists():
            print(f"[warn] root does not exist: {root}", file=sys.stderr)
            continue
        for p in rootp.rglob("*"):
            if p.is_file() and p.suffix.lower() in exts:
                files.append(p.resolve())
    return sorted(set(files))

def build_entity_index(file_infos):
    idx = {}
    for fi in file_infos:
        if fi.entity_name:
            if fi.entity_name in idx and str(idx[fi.entity_name]) != str(fi.path):
                print(f"[warn] Duplicate entity '{fi.entity_name}' "
                      f"in {idx[fi.entity_name]} and {fi.path}", file=sys.stderr)
            idx.setdefault(fi.entity_name, fi.path)
    return idx

def compute_dependencies(file_infos, entity_index):
    deps = []
    for fi in file_infos:
        targets = set()
        for inst in fi.instances:
            target_entity = inst.entity_ref or inst.component_name
            if target_entity and target_entity in entity_index:
                tgt_path = pathlib.Path(entity_index[target_entity]).resolve()
                if tgt_path != fi.path:
                    targets.add(tgt_path)
        for tgt in targets:
            deps.append((str(fi.path), str(tgt)))
    return sorted(set(deps))

def main():
    ap = argparse.ArgumentParser(description="VHDL Visualizer (v0.3 designer skeleton)")
    ap.add_argument("--roots", nargs="+", required=True, help="Folders to scan for .vhd/.vhdl files")
    ap.add_argument("--out", default="build", help="Output folder")
    ap.add_argument("--open", action="store_true", help="Open dependency graph after generation")
    ap.add_argument("--designer", action="store_true", help="Open the designer after generation")
    args = ap.parse_args()

    outdir = pathlib.Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    block_dir = outdir / "blocks"
    block_dir.mkdir(parents=True, exist_ok=True)

    files = discover_files(args.roots)
    if not files:
        print("[err] No VHDL files found.", file=sys.stderr)
        sys.exit(2)

    file_infos = []
    for f in files:
        try:
            text = pathlib.Path(f).read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"[warn] Cannot read {f}: {e}", file=sys.stderr)
            continue
        fi = parse_vhdl_file(pathlib.Path(f), text)
        file_infos.append(fi)

    entity_index = build_entity_index(file_infos)
    deps = compute_dependencies(file_infos, entity_index)

    # DB
    db = DesignDB.from_files(file_infos, deps)
    db_json_path = outdir / "design_db.json"
    db_json_path.write_text(json.dumps(db.to_json(), indent=2), encoding="utf-8")

    # Dependency graph
    index_path = outdir / "index.html"
    write_dependency_html(index_path, db)

    # Block views
    # Build entity_port_db for pin directions
    entity_port_db = {}
    for fi in file_infos:
        if fi.entity_name:
            entity_port_db[fi.entity_name] = {p.name: p for p in fi.ports}

    for fi in file_infos:
        label = fi.entity_name or fi.path.stem
        p = block_dir / f"{label}.html"
        write_block_html(p, fi, entity_port_db)

    # Designer
    designer_path = outdir / "designer.html"
    write_designer_html(designer_path, db)

    print(f"[ok] Generated:\n- {index_path}\n- {db_json_path}\n- {block_dir}/<file>.html\n- {designer_path}")
    if args.open:
        try:
            import webbrowser
            webbrowser.open(index_path.as_uri())
        except Exception as e:
            print(f"[warn] Could not open index: {e}", file=sys.stderr)
    if args.designer:
        try:
            import webbrowser
            webbrowser.open(designer_path.as_uri())
        except Exception as e:
            print(f"[warn] Could not open designer: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
