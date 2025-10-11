import re

FLAGS = re.IGNORECASE | re.DOTALL | re.MULTILINE

# ENTITY with optional PORT section
ENTITY_RE = re.compile(
    r"\bentity\s+(?P<name>\w+)\s+is\s*"
    r"(?:.*?\bport\s*\((?P<ports>.*?)\)\s*;\s*)?"
    r"end\s+(?:entity\s+)?(?P=name)\s*;",
    FLAGS,
)

# Individual port lines inside the PORT(...) group
# Roughly: name[s] : [in|out|inout|buffer|linkage] type [; or )]
PORT_LINE_RE = re.compile(
    r"(?P<names>[\w,\s]+?)\s*:\s*(?P<dir>inout|in|out|buffer|linkage)\s+(?P<dtype>[^;]+?)(?:;|$)",
    re.IGNORECASE,
)

# SIGNAL declarations (top-level architecture only for v0.1)
SIGNAL_RE = re.compile(
    r"(?<!\w)\bsignal\s+(?P<name>\w+)\s*:\s*(?P<dtype>[^;]+);",
    FLAGS,
)

# Component-style instantiation: u1 : my_comp (generic map ...)? port map (...)
COMP_INST_RE = re.compile(
    r"(?P<label>\w+)\s*:\s*(?P<comp>\w+)\s*"
    r"(?:generic\s+map\s*\((?P<gmap>.*?)\)\s*)?"
    r"port\s+map\s*\((?P<pmap>.*?)\)\s*;",
    FLAGS,
)

# Direct entity instantiation: u1 : entity work.my_ent ... port map (...)
ENTITY_INST_RE = re.compile(
    r"(?P<label>\w+)\s*:\s*entity\s+(?P<lib>\w+)\s*\.\s*(?P<ent>\w+)\s*"
    r"(?:\((?P<arch>\w+)\))?\s*"
    r"(?:generic\s+map\s*\((?P<gmap>.*?)\)\s*)?"
    r"port\s+map\s*\((?P<pmap>.*?)\)\s*;",
    FLAGS,
)

# Port map assignments: formal => actual
PMAP_KV_RE = re.compile(
    r"(?P<formal>\w+)\s*=>\s*(?P<actual>[^,()]+)(?:,|$)",
    re.IGNORECASE,
)
