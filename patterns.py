import re

FLAGS = re.IGNORECASE | re.DOTALL | re.MULTILINE

# Conditional concurrent assignment:   a <= e1 when cond else e2;
COND_ASSIGN_RE = re.compile(
    r"(?<!\S)(?P<lhs>\w+(?:\s*\([^)]*\))?)\s*<=\s*(?P<e_true>[^;]*?)\s+when\s+(?P<cond>[^;]*?)\s+else\s+(?P<e_false>[^;]*?);",
    FLAGS
)

# Selected signal assignment:
#   with sel select a <= e0 when c0, e1 when c1, others;
WITH_SELECT_RE = re.compile(
    r"(?<!\S)with\s+(?P<sel>[^;]+?)\s+select\s+(?P<lhs>\w+(?:\s*\([^)]*\))?)\s*<=\s*(?P<body>.*?);",
    FLAGS
)
# Split the body: "e when c, e2 when c2, others"
WHEN_ITEM_RE = re.compile(
    r"(?P<expr>[^,]+?)\s+when\s+(?P<choice>[^,]+?)(?:,|$)",
    FLAGS
)

# Very light process-style (combinational) assignments:
#   process(...) begin ...  a <= b;  ... end process;
PROCESS_BLOCK_RE = re.compile(
    r"(?<!\S)process\s*(?:\([^\)]*\))?\s*begin(?P<body>.*?)end\s+process\s*;?",
    FLAGS
)

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

# Simple concurrent assignment:   a <= b;
ASSIGN_RE = re.compile(
    r"(?<!\S)(?P<lhs>\w+(?:\s*\([^)]*\))?)\s*<=\s*(?P<expr>.*?);",
    FLAGS
)
