"""PDF export formatter for Radio & TV Story Segmenter.

Provides a lightweight, self-contained PDF 1.4 vector generator for transcript documents
with support for pagination, Helvetica fonts, speaker headers, timestamps, and comment callouts.
"""
from __future__ import annotations

import io
from typing import Optional


class TranscriptPdfWriter:
    """Lightweight, self-contained PDF 1.4 vector generator for transcript documents.
    Generates fully compliant, paginated PDF documents with Helvetica fonts, headers,
    word-wrapped paragraphs, timestamps, speaker labels, comment callout boxes, and footers."""

    def __init__(self, doc_title="Transcript", page_width=612, page_height=792, margin=54):
        if isinstance(doc_title, (int, float)):
            margin = page_height if isinstance(page_height, (int, float)) and page_height < 100 else margin
            page_height = page_width if isinstance(page_width, (int, float)) else 792.0
            page_width = float(doc_title)
            doc_title = "Transcript"
        self.doc_title = str(doc_title or "Transcript")
        self.width = float(page_width)
        self.height = float(page_height)
        self.margin = float(margin)
        self.content_width = self.width - (2 * self.margin)
        self.pages = []
        self.cur_stream = io.BytesIO()
        self.y = self.height - self.margin
        self.current_page = 1

    def _escape_pdf(self, s: str) -> str:
        out = []
        for ch in s:
            if ch in ('(', ')', '\\'):
                out.append('\\' + ch)
            elif ord(ch) < 32 or ord(ch) > 126:
                try:
                    b = ch.encode('cp1252')
                    for byte in b:
                        out.append(f'\\{byte:03o}')
                except Exception:
                    out.append('?')
            else:
                out.append(ch)
        return ''.join(out)

    def _flush_page(self):
        footer_cmd = (
            f'0.6 0.65 0.7 RG 0.75 w\n'
            f'{self.margin} 42 m {self.width - self.margin} 42 l S\n'
            f'BT /F1 8 Tf 0.45 0.5 0.55 rg\n'
            f'{self.margin} 30 Td (Radio & TV Story Segmenter) Tj\n'
            f'{self.width - self.margin - 55} 30 Td (Page {self.current_page}) Tj\n'
            f'ET\n'
        )
        self.cur_stream.write(footer_cmd.encode('latin1', errors='replace'))
        self.pages.append(self.cur_stream.getvalue())
        self.cur_stream = io.BytesIO()
        self.current_page += 1
        self.y = self.height - self.margin

    def check_space(self, needed_pt: float):
        if self.y - needed_pt < (self.margin + 40):
            self._flush_page()

    def add_header(self, title: str, subtitle: Optional[str] = None):
        self.check_space(60)
        title_esc = self._escape_pdf(title)
        cmd = f'BT /F2 16 Tf 0.1 0.15 0.25 rg {self.margin} {self.y} Td ({title_esc}) Tj ET\n'
        self.cur_stream.write(cmd.encode('latin1', errors='replace'))
        self.y -= 22

        if subtitle:
            sub_esc = self._escape_pdf(subtitle)
            cmd = f'BT /F3 9.5 Tf 0.4 0.45 0.55 rg {self.margin} {self.y} Td ({sub_esc}) Tj ET\n'
            self.cur_stream.write(cmd.encode('latin1', errors='replace'))
            self.y -= 14

        cmd = f'0.2 0.4 0.8 RG 1.5 w\n{self.margin} {self.y} m {self.width - self.margin} {self.y} l S\n'
        self.cur_stream.write(cmd.encode('latin1', errors='replace'))
        self.y -= 16

    def _approx_char_width(self, font_name: str, size: float) -> float:
        return size * (0.56 if 'Bold' in font_name else 0.51)

    def _wrap_text(self, text: str, max_width: float, font_name: str, size: float):
        char_w = self._approx_char_width(font_name, size)
        max_chars = max(10, int(max_width / char_w))
        words = text.split()
        lines = []
        cur_line = []
        cur_len = 0
        for w in words:
            w_len = len(w)
            if cur_len + (1 if cur_line else 0) + w_len <= max_chars:
                cur_line.append(w)
                cur_len += (1 if cur_line else 0) + w_len
            else:
                if cur_line:
                    lines.append(' '.join(cur_line))
                cur_line = [w]
                cur_len = w_len
        if cur_line:
            lines.append(' '.join(cur_line))
        return lines

    def add_paragraph(self, text: str, speaker: str = '', timestamp: str = '', comment: str = ''):
        font_size = 10.0
        line_height = 14.0
        prefix_parts = []
        if timestamp:
            prefix_parts.append(timestamp)
        if speaker:
            prefix_parts.append(f'{speaker}:')
        prefix_str = ' '.join(prefix_parts) + (' ' if prefix_parts else '')

        full_text = prefix_str + text
        lines = self._wrap_text(full_text, self.content_width, 'Helvetica', font_size)

        needed_height = (len(lines) * line_height) + 8
        self.check_space(min(needed_height, 50))

        for line in lines:
            self.check_space(line_height)
            line_esc = self._escape_pdf(line)
            cmd = f'BT /F1 {font_size} Tf 0.15 0.15 0.15 rg {self.margin} {self.y} Td ({line_esc}) Tj ET\n'
            self.cur_stream.write(cmd.encode('latin1', errors='replace'))
            self.y -= line_height

        self.y -= 4

        if comment:
            c_lines = self._wrap_text(comment, self.content_width - 24, 'Helvetica-Oblique', 9.0)
            box_h = (len(c_lines) * 12.5) + 12
            self.check_space(box_h + 4)
            box_y = self.y - box_h + 6
            bg_cmd = (
                f'0.98 0.97 0.93 rg\n'
                f'{self.margin + 12} {box_y} {self.content_width - 12} {box_h} re f\n'
                f'0.85 0.65 0.15 RG 2 w\n'
                f'{self.margin + 12} {box_y} m {self.margin + 12} {box_y + box_h} l S\n'
            )
            self.cur_stream.write(bg_cmd.encode('latin1', errors='replace'))

            text_y = self.y - 4
            lbl_esc = self._escape_pdf('Comment: ')
            cmd = f'BT /F2 9.0 Tf 0.7 0.45 0.05 rg {self.margin + 20} {text_y} Td ({lbl_esc}) Tj ET\n'
            self.cur_stream.write(cmd.encode('latin1', errors='replace'))

            for c_idx, c_l in enumerate(c_lines):
                c_esc = self._escape_pdf(c_l)
                x_off = self.margin + 20 + (50 if c_idx == 0 else 0)
                cmd = f'BT /F3 9.0 Tf 0.45 0.35 0.1 rg {x_off} {text_y} Td ({c_esc}) Tj ET\n'
                self.cur_stream.write(cmd.encode('latin1', errors='replace'))
                text_y -= 12.5
            self.y = box_y - 6

    def finish(self) -> bytes:
        if self.cur_stream.tell() > 0 or not self.pages:
            self._flush_page()

        out = io.BytesIO()
        out.write(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
        offsets = {}

        def write_obj(num, content):
            offsets[num] = out.tell()
            out.write(f'{num} 0 obj\n'.encode('ascii'))
            out.write(content)
            out.write(b'\nendobj\n')

        num_pages = len(self.pages)
        page_obj_ids = [6 + i * 2 for i in range(num_pages)]
        content_obj_ids = [7 + i * 2 for i in range(num_pages)]

        write_obj(1, b'<< /Type /Catalog /Pages 2 0 R >>')
        kids_str = ' '.join(f'{pid} 0 R' for pid in page_obj_ids)
        write_obj(2, f'<< /Type /Pages /Kids [{kids_str}] /Count {num_pages} >>'.encode('ascii'))
        write_obj(3, b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>')
        write_obj(4, b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>')
        write_obj(5, b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique /Encoding /WinAnsiEncoding >>')

        for i, stream_data in enumerate(self.pages):
            p_id = page_obj_ids[i]
            c_id = content_obj_ids[i]
            res = b'<< /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >>'
            page_dict = f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self.width} {self.height}] /Contents {c_id} 0 R /Resources {res.decode("ascii")} >>'.encode('ascii')
            write_obj(p_id, page_dict)
            stream_dict = f'<< /Length {len(stream_data)} >>\nstream\n'.encode('ascii') + stream_data + b'\nendstream'
            write_obj(c_id, stream_dict)

        xref_offset = out.tell()
        total_objs = 5 + num_pages * 2
        out.write(f'xref\n0 {total_objs + 1}\n'.encode('ascii'))
        out.write(b'0000000000 65535 f \n')
        for obj_num in range(1, total_objs + 1):
            offset = offsets.get(obj_num, 0)
            out.write(f'{offset:010d} 00000 n \n'.encode('ascii'))

        out.write(f'trailer\n<< /Size {total_objs + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n'.encode('ascii'))
        return out.getvalue()

    def get_pdf_bytes(self) -> bytes:
        return self.finish()
