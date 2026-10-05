"""docx パッケージ（OOXML の zip）の読み書き。

レイアウトの正本は原本 docx の XML そのもの。このモジュールの責務は
「触らない部分を一切変えない」ことだけ。

* zip のエントリ順・圧縮方式を保ったまま書き戻す
* document.xml を解析するとき、原本で使われている名前空間プレフィックスを登録する
  （登録しないと ElementTree が ns0: のような機械的な名前を振り、
  mc:Ignorable が参照するプレフィックスと食い違って Word が開けなくなる）
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
DOCUMENT = "word/document.xml"

_XMLNS_RE = re.compile(rb'xmlns:([A-Za-z0-9_.-]+)\s*=\s*"([^"]*)"')
_RESERVED = re.compile(rb"^ns\d+$")   # ET が内部で使う形。登録すると例外になる

# 図形の中でだけ宣言される名前空間は、根に巻き上げられたとき ns5: などになって
# しまう。OOXML で通例のプレフィックスを先に登録しておく。
CANONICAL_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "a14": "http://schemas.microsoft.com/office/drawing/2010/main",
    "wpc": "http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas",
    "wpg": "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup",
    "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
    "wpi": "http://schemas.microsoft.com/office/word/2010/wordprocessingInk",
}


def w(tag: str) -> str:
    """wordprocessingml の修飾名。"""
    return "{%s}%s" % (W, tag)


def register_namespaces(xml: bytes) -> None:
    for prefix, uri in CANONICAL_NS.items():
        ET.register_namespace(prefix, uri)
    for prefix, uri in _XMLNS_RE.findall(xml[:8192]):
        if not _RESERVED.match(prefix):
            ET.register_namespace(prefix.decode(), uri.decode())


class DocxPackage:
    """docx を「エントリ名 → bytes」の辞書として持つ。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.names: list[str] = []
        self.parts: dict[str, bytes] = {}
        self._compress: dict[str, int] = {}
        with zipfile.ZipFile(self.path) as zf:
            for info in zf.infolist():
                self.names.append(info.filename)
                self.parts[info.filename] = zf.read(info.filename)
                self._compress[info.filename] = info.compress_type

    def parse_document(self) -> ET.Element:
        register_namespaces(self.parts[DOCUMENT])
        return ET.fromstring(self.parts[DOCUMENT])

    def set_document(self, root: ET.Element) -> None:
        xml = ET.tostring(root, encoding="UTF-8", xml_declaration=True)
        # Word と同じ宣言（standalone="yes"＋CRLF）にそろえる
        xml = xml.replace(
            b"<?xml version='1.0' encoding='UTF-8'?>\n",
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n', 1)
        self.parts[DOCUMENT] = xml

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as zf:
            for name in self.names:
                zf.writestr(zipfile.ZipInfo(name), self.parts[name],
                            compress_type=self._compress.get(name, zipfile.ZIP_DEFLATED))
        return path
