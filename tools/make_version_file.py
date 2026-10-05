"""Writes build/version_info.txt (the version shown in the exe's Properties) from openadder.__version__."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from openadder import __version__  # noqa: E402

numbers = tuple(int(n) for n in __version__.split(".")) + (0,)
text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={numbers}, prodvers={numbers}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'OpenAdder contributors'),
      StringStruct('FileDescription', 'OpenAdder - settings for the Razer DeathAdder V2'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', 'OpenAdder'),
      StringStruct('LegalCopyright', 'GPL-2.0-or-later'),
      StringStruct('OriginalFilename', 'OpenAdder.exe'),
      StringStruct('ProductName', 'OpenAdder'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
out = ROOT / "build" / "version_info.txt"
out.parent.mkdir(exist_ok=True)
out.write_text(text, encoding="utf-8")
print(f"wrote {out} for version {__version__}")
