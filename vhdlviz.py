#!/usr/bin/env python3
import argparse, json, sys, os, pathlib
from parser import parse_vhdl_file
from model import DesignDB, FileInfo
from visualize import write_dependency_html, write_block_html
from typing import Dict
from model import Port

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
    # entity name -> file path (first wins, warn on duplicates)
    idx = {}
    for fi in file_infos:
        if fi.entity_name:
            if fi.entity_name in idx and str(idx[fi.entity_name]) != str(fi.path):
                print(f"[warn] Duplicate entity '{fi.entity_name}' "
                      f"in {idx[fi.entity_name]} and {fi.path}", file=sys.stderr)
            idx.setdefault(fi.entity_name, fi.path)
    return idx

def compute_dependencies(file_infos, entity_index):
    # Dependency edges: file A -> file B if A instantiates entity whose file is B
    deps = []
    for fi in file_infos:
        targets = set()
        for inst in fi.instances:
            # prefer explicit entity target if present
            target_entity = inst.entity_ref or inst.component_name
            if target_entity and target_entity in entity_index:
                tgt_path = pathlib.Path(entity_index[target_entity]).resolve()
                if tgt_path != fi.path:
                    targets.add(tgt_path)
        for tgt in targets:
            deps.append((str(fi.path), str(tgt)))
    return sorted(set(deps))

def main():
    ap = argparse.ArgumentParser(description="VHDL Visualizer (v0.1)")
    ap.add_argument("--roots", nargs="+", required=True,
                    help="Folders to scan for .vhd/.vhdl files")
    ap.add_argument("--out", default="build", help="Output folder")
    ap.add_argument("--open", action="store_true", help="Try to open index.html after generation")
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

    # Build DB
    db = DesignDB.from_files(file_infos, deps)
    db_json_path = outdir / "design_db.json"
    db_json_path.write_text(json.dumps(db.to_json(), indent=2), encoding="utf-8")
    
    entity_port_db: Dict[str, Dict[str, Port]] = {}
    for fi in file_infos:
        if fi.entity_name:
            entity_port_db[fi.entity_name] = {p.name: p for p in fi.ports}

    # Write dependency graph HTML
    index_path = outdir / "index.html"
    write_dependency_html(index_path, db)

    # Write per-file block views
    for fi in file_infos:
        # Note: we use entity name if present, else filename stem
        label = fi.entity_name or fi.path.stem
        p = block_dir / f"{label}.html"
        write_block_html(p, fi, entity_port_db)

    print(f"[ok] Generated:\n- {index_path}\n- {db_json_path}\n- {block_dir}/<file>.html")
    if args.open:
        try:
            import webbrowser
            webbrowser.open(index_path.as_uri())
        except Exception as e:
            print(f"[warn] Could not open in browser: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
