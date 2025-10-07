import re

RX = {}

# Whitespace for cleaning
RX["WS"] = re.compile(r"\s+", re.MULTILINE)

# Comments
RX['LINE_COMMENT']  = re.compile(r"--.*?$", re.MULTILINE)
RX["BLOCK_COMMENT"] = re.compile(
    r"/\*.*?\*/", re.DOTALL
)  # rarely used in VHDL, but harmless to strip

# entity <name> is … end [entity] <name>;
RX["ENTITY_DEF"] = re.compile(
    r"(?i)\bentity\s+(?P<name>\w+)\s+is[\s\S]*?end\s+(?:entity\s+)?(?P=name)\s*;"
)

# signal foo : std_logic;  |  signal a,b : std_logic_vector(7 downto 0);
RX["SIGNAL_DECL"] = re.compile(
    r"(?is)\bsignal\s+([a-zA-Z_]\w*(?:\s*,\s*[a-zA-Z_]\w*)*)\s*:\s*([^;]+);"
)

# label: entity work.some_entity [generic map(...)] port map (...);
# or   label: some_component port map(...);
RX["COMP_OR_ENTITY_INST"] = re.compile(
    r"(?is)\b(?P<label>[a-zA-Z_]\w*)\s*:\s*(?P<is_entity>entity\s+\w+\.)?(?P<type>[a-zA-Z_]\w*)"
    r"(?:\s*generic\s*map\s*\((?P<generics>.*?)\))?\s*port\s*map\s*\((?P<ports>.*?)\)\s*;"
)

# formal => actual pairs inside port map
RX["PORT_ASSOC"] = re.compile(r"(?is)\b([a-zA-Z_]\w*)\s*=>\s*([^,\)]+)")
