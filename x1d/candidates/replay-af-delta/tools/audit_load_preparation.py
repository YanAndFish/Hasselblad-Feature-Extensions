"""固定 ARM ELF 元数据读取，仅保留本修订的依赖审计助手。"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/"x1d/tools"))
from binary import ArmElf

def metadata(data):
    elf = ArmElf(data).elf
    dynamic = elf.get_section_by_name(".dynamic")
    tags = list(dynamic.iter_tags()) if dynamic else []
    return {
        "needed": [t.needed for t in tags if t.entry.d_tag == "DT_NEEDED"],
        "interpreter": [s.get_interp_name() for s in elf.iter_segments() if s["p_type"] == "PT_INTERP"],
        "searchPaths": [getattr(t, "rpath", getattr(t, "runpath", "")) for t in tags
                        if t.entry.d_tag in ("DT_RPATH", "DT_RUNPATH")],
    }


def symbols(data):
    elf = ArmElf(data).elf
    versions, version_needs = {}, []
    sec = elf.get_section_by_name(".gnu.version_r")
    if sec:
        for item, auxiliaries in sec.iter_versions():
            for aux in auxiliaries:
                versions[aux["vna_other"] & 0x7fff] = aux.name
                version_needs.append({"library": item.name, "version": aux.name})
    sec = elf.get_section_by_name(".gnu.version_d")
    definitions = set()
    if sec:
        for item, auxiliaries in sec.iter_versions():
            names = [aux.name for aux in auxiliaries]
            versions[item["vd_ndx"]] = names[0]
            definitions.add(names[0])
    versym = elf.get_section_by_name(".gnu.version")
    imports, exports = [], []
    for index, sym in enumerate(elf.get_section_by_name(".dynsym").iter_symbols()):
        if not sym.name: continue
        vi = versym.get_symbol(index)["ndx"] if versym else "VER_NDX_GLOBAL"
        hidden = isinstance(vi, int) and bool(vi & 0x8000)
        version = versions.get(vi & 0x7fff) if isinstance(vi, int) else None
        entry = {"name": sym.name, "version": version, "default": not hidden,
                 "weak": sym["st_info"]["bind"] == "STB_WEAK"}
        if sym["st_shndx"] == "SHN_UNDEF": imports.append(entry)
        elif sym["st_info"]["bind"] in ("STB_GLOBAL", "STB_WEAK", "STB_GNU_UNIQUE", "STB_LOOS") and sym["st_other"]["visibility"] in ("STV_DEFAULT", "STV_PROTECTED"):
            exports.append(entry)
    return {"imports": imports, "exports": exports, "versionNeeds": version_needs,
            "versionDefinitions": definitions, **metadata(data)}

