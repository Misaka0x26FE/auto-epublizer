"""EPUB 3 写入：构建 OPF/container/nav/NCX + zip 打包（确定性）。"""

from __future__ import annotations

import html
import zipfile
from pathlib import Path

from auto_common.workspace import Publication
from .html import slug_file

_MIMETYPE = 'application/epub+zip'


def _esc(text: str) -> str:
    """XML 文本节点转义（& < >）。"""
    return html.escape(str(text), quote=False)


class BuildError(RuntimeError):
    """EPUB 构建失败。"""


def _render_nav(entries: list[dict], *, lang: str) -> str:
    lis = '\n'.join(
        '      <li><a href="' + slug_file(e['id']) + '.xhtml">' + _esc(e['title']) + '</a></li>'
        for e in entries
    )
    out = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<!DOCTYPE html>',
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
        'xml:lang="' + lang + '" lang="' + lang + '">',
        '<head>',
        '<meta charset="utf-8"/>',
        '<title>目录</title>',
        '</head>',
        '<body>',
        '<nav epub:type="toc" id="toc">',
        '<h1>目录</h1>',
        '<ol>',
        lis,
        '</ol>',
        '</nav>',
        '</body>',
        '</html>',
        '',
    ]
    return '\n'.join(out)


def _render_landmarks(entries: list[dict]) -> str:
    body = next((e for e in entries if e['region'] == 'body'), None)
    front = next((e for e in entries if e['region'] == 'frontmatter'), None)
    back = next((e for e in entries if e['region'] == 'backmatter'), None)
    mapping = {'frontmatter': front, 'bodymatter': body, 'backmatter': back}
    labels = {'frontmatter': '前言', 'bodymatter': '正文', 'backmatter': '后附'}
    parts = []
    for region, label in labels.items():
        entry = mapping[region]
        if entry:
            parts.append(
                '<li><a epub:type="' + region + '" href="' + slug_file(entry['id'])
                + '.xhtml">' + label + '</a></li>'
            )
    lis = '\n'.join('      ' + p for p in parts)
    out = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<!DOCTYPE html>',
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">',
        '<head>',
        '<meta charset="utf-8"/>',
        '<title>导航</title>',
        '</head>',
        '<body>',
        '<nav epub:type="landmarks" id="landmarks">',
        '<h2>导航</h2>',
        '<ol>',
        lis,
        '</ol>',
        '</nav>',
        '</body>',
        '</html>',
        '',
    ]
    return '\n'.join(out)


def _identifier(pub: Publication) -> str:
    meta = pub.meta
    return meta.identifier.uri or meta.identifier.isbn or pub.slug


def _render_ncx(entries: list[dict], *, identifier: str) -> str:
    points = []
    for i, e in enumerate(entries, start=1):
        points.append(
            '    <navPoint id="navpoint-' + str(i) + '" playOrder="' + str(i) + '">\n'
            '      <navLabel><text>' + _esc(e['title']) + '</text></navLabel>\n'
            '      <content src="' + slug_file(e['id']) + '.xhtml"/>\n'
            '    </navPoint>'
        )
    navmap = '\n'.join(points)
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">',
        '  <head>',
        '    <meta name="dtb:uid" content="' + identifier + '"/>',
        '    <meta name="dtb:depth" content="1"/>',
        '    <meta name="dtb:totalPageCount" content="0"/>',
        '    <meta name="dtb:maxPageNumber" content="0"/>',
        '  </head>',
        '  <docTitle><text>目录</text></docTitle>',
        '  <navMap>',
        navmap,
        '  </navMap>',
        '</ncx>',
        '',
    ]
    return '\n'.join(out)


def _render_opf(pub: Publication, entries: list[dict], *, lang: str, modified: str) -> str:
    meta = pub.meta
    manifest_lines = []
    for e in entries:
        manifest_lines.append(
            '    <item id="' + slug_file(e['id']) + '" href="' + slug_file(e['id'])
            + '.xhtml" media-type="application/xhtml+xml"/>'
        )
    manifest_lines.append(
        '    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
    )
    manifest_lines.append(
        '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
        'properties="nav"/>'
    )
    manifest = '\n'.join(manifest_lines) + '\n'
    spine = ''.join(
        '    <itemref idref="' + slug_file(e['id']) + '"/>\n' for e in entries
    )
    ident = _identifier(pub)
    dc_lines = [
        '    <dc:identifier id="pub-id">' + _esc(ident) + '</dc:identifier>',
        '    <dc:title>' + _esc(meta.title) + '</dc:title>',
        '    <dc:language>' + _esc(lang) + '</dc:language>',
    ]
    if meta.creator:
        dc_lines.append('    <dc:creator>' + _esc(meta.creator) + '</dc:creator>')
    if meta.publisher:
        dc_lines.append('    <dc:publisher>' + _esc(meta.publisher) + '</dc:publisher>')
    if meta.date:
        dc_lines.append('    <dc:date>' + _esc(meta.date) + '</dc:date>')
    if meta.rights:
        dc_lines.append('    <dc:rights>' + _esc(meta.rights) + '</dc:rights>')
    dc = '\n'.join(dc_lines) + '\n'
    package = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'unique-identifier="pub-id">',
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">',
        dc.rstrip('\n'),
        '    <meta property="dcterms:modified">' + modified + '</meta>',
        '  </metadata>',
        '  <manifest>',
        manifest.rstrip('\n'),
        '  </manifest>',
        '  <spine toc="ncx">',
        spine.rstrip('\n'),
        '  </spine>',
        '</package>',
        '',
    ]
    return '\n'.join(package)


def _render_container() -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        '  <rootfiles>\n'
        '    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>\n'
        '  </rootfiles>\n'
        '</container>\n'
    )


def build_epub(
    pub: Publication,
    entries: list[dict],
    content_files: list[tuple[str, str]],
    *,
    lang: str,
    modified: str,
    out_path: str | Path,
) -> Path:
    """把结构化单元与导航封装为 EPUB 文件。"""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not lang:
        lang = pub.meta.target_language or pub.meta.language or 'zh-CN'

    with zipfile.ZipFile(out, 'w') as zf:
        zinfo = zipfile.ZipInfo('mimetype')
        zinfo.compress_type = zipfile.ZIP_STORED
        zinfo.external_attr = 0o600 << 16
        zf.writestr(zinfo, _MIMETYPE)
        zf.writestr('META-INF/container.xml', _render_container(), compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr('OEBPS/content.opf', _render_opf(pub, entries, lang=lang, modified=modified),
                    compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr('OEBPS/nav.xhtml', _render_nav(entries, lang=lang),
                    compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr('OEBPS/toc.ncx', _render_ncx(entries, identifier=_identifier(pub)),
                    compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr('OEBPS/landmarks.xhtml', _render_landmarks(entries),
                    compress_type=zipfile.ZIP_DEFLATED)
        for filename, content in content_files:
            zf.writestr('OEBPS/' + filename, content, compress_type=zipfile.ZIP_DEFLATED)
    return out