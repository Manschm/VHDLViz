from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from pathlib import Path

@dataclass
class Port:
    name: str
    direction: str   # in|out|inout|buffer|linkage (raw string kept)
    dtype: str       # raw subtype indication, e.g. std_logic_vector(7 downto 0)

@dataclass
class Signal:
    name: str
    dtype: str

@dataclass
class Instance:
    label: str                    # u1, etc.
    component_name: Optional[str] # if "u1 : my_comp"
    entity_ref: Optional[str]     # if "u1 : entity work.my_ent"
    port_map: Dict[str, str]      # formal -> actual expression (raw)

@dataclass
class FileInfo:
    path: Path
    entity_name: Optional[str]
    ports: List[Port] = field(default_factory=list)
    signals: List[Signal] = field(default_factory=list)
    instances: List[Instance] = field(default_factory=list)

    def to_json(self):
        d = asdict(self)
        d["path"] = str(self.path)
        return d

@dataclass
class DesignDB:
    files: List[FileInfo]
    # deps as list of [src_path, dst_path]
    dependencies: List[List[str]] = field(default_factory=list)

    @staticmethod
    def from_files(file_infos: List[FileInfo], deps):
        deps_list = [[src, dst] for (src, dst) in deps]
        return DesignDB(files=file_infos, dependencies=deps_list)

    def to_json(self):
        return {
            "files": [f.to_json() for f in self.files],
            "dependencies": self.dependencies,
        }
