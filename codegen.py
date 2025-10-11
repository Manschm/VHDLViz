#!/usr/bin/env python3
"""
vviz (.vviz.json) -> VHDL top-level generator.

Usage:
  python codegen.py path/to/top.vviz.json > top.vhd
"""
import json, sys, re

HEADER = """library ieee;
use ieee.std_logic_1164.all;
-- Add further use clauses as needed (numeric_std, etc.)

"""

def sanitize_ident(name: str) -> str:
    # basic; allow (), <> etc inside types elsewhere
    return re.sub(r'[^A-Za-z0-9_]', '_', name)

def gen_entity(v: dict) -> str:
    name = sanitize_ident(v.get("name","top_level"))
    ports = v.get("ports", [])
    lines = [f"entity {name} is"]
    if ports:
        lines.append("  port (")
        rows = []
        for p in ports:
            rows.append(f"    {p['name']} : {p['dir']} {p['dtype']}")
        lines.append(";\n".join(rows))
        lines.append("  );")
    lines.append(f"end {name};\n")
    return "\n".join(lines)

def gen_signals(v: dict) -> str:
    sigs = v.get("signals", [])
    if not sigs: return ""
    rows = [f"  signal {s['name']} : {s['dtype']};" for s in sigs]
    return "\n".join(rows) + "\n"

def gen_inst(i: dict) -> str:
    """
    Instance dict:
      {"id":"u_core","entity":"core","arch":null,"port_map":{"clk":"clk","rst_n":"rst_n","data_i":"s_data"}}
    """
    label = sanitize_ident(i["id"])
    ent = i["entity"]
    arch = i.get("arch")
    # Prefer direct entity instantiation syntax
    head = f"  {label} : entity work.{ent}" + (f"({arch})" if arch else "")
    pm = i.get("port_map", {}) or {}
    # Keep stable order (sorted by formal)
    items = [f"{k} => {pm[k]}" for k in sorted(pm.keys())]
    body = "    port map (\n      " + ",\n      ".join(items) + "\n    );"
    return head + "\n" + body

def gen_architecture(v: dict) -> str:
    name = sanitize_ident(v.get("name","top_level"))
    lines = [f"architecture rtl of {name} is"]
    sigs = gen_signals(v)
    if sigs:
        lines.append(sigs.rstrip())
    lines.append("begin")
    # concurrent assignments (optional)
    for a in v.get("assignments", []):
        lines.append(f"  {a['target']} <= {a['expr']};")
    # instances
    for i in v.get("instances", []):
        lines.append(gen_inst(i))
    lines.append("end rtl;")
    return "\n".join(lines)

def vviz_to_vhdl(v: dict) -> str:
    return HEADER + gen_entity(v) + gen_architecture(v) + "\n"

def main():
    if len(sys.argv) != 2:
        print("Usage: codegen.py top.vviz.json > top.vhd", file=sys.stderr)
        sys.exit(2)
    data = json.loads(open(sys.argv[1], "r", encoding="utf-8").read())
    sys.stdout.write(vviz_to_vhdl(data))

if __name__ == "__main__":
    main()
