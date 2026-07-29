"""Section-based Markdown chunking for financial reports.

Financial reports have clear section structure (资产负债表, 利润表, etc.).
Chunking on section boundaries preserves semantic coherence for search.
"""

import re
from dataclasses import dataclass

# Matches ATX headings: ## 资产负债表, ### 流动资产, etc.
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


@dataclass
class Chunk:
    """A single searchable text segment."""

    text: str
    section_title: str      # The closest heading (e.g. "资产负债表")
    section_path: str       # Full breadcrumb (e.g. "财务报表 > 资产负债表 > 流动资产")
    char_start: int
    char_end: int


def chunk_markdown(
    md_text: str,
    max_chars: int = 1500,
    overlap: int = 200,
) -> list[Chunk]:
    """Split Markdown text into semantically coherent chunks.

    Algorithm:
        1. Parse into (heading_path, content) sections.
        2. Sections under max_chars become one chunk.
        3. Over-long sections split at paragraph boundaries with overlap.
        4. Each chunk inherits its parent section's heading breadcrumb.

    Args:
        md_text: Full Markdown text.
        max_chars: Soft maximum characters per chunk.
        overlap: Characters of overlap between consecutive chunks of the same section.

    Returns:
        Ordered list of Chunk objects.
    """
    sections = _parse_sections(md_text)
    chunks: list[Chunk] = []

    for heading_path, content, start_offset in sections:
        # Skip headings with no body text (e.g. a ## section whose content
        # lives entirely in child ### sub-sections).
        if not content.strip():
            continue

        section_title = heading_path[-1] if heading_path else ""
        section_path_str = " > ".join(heading_path) if heading_path else ""

        if len(content) <= max_chars:
            chunks.append(
                Chunk(
                    text=content.strip(),
                    section_title=section_title,
                    section_path=section_path_str,
                    char_start=start_offset,
                    char_end=start_offset + len(content),
                )
            )
            continue

        # Over-long section — split at paragraph boundaries
        paragraphs = re.split(r"\n{2,}", content)
        current = ""
        current_start = start_offset

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if not current:
                current = para
                continue

            if len(current) + len(para) + 2 <= max_chars:
                current += "\n\n" + para
            else:
                # Flush current chunk
                chunks.append(
                    Chunk(
                        text=current.strip(),
                        section_title=section_title,
                        section_path=section_path_str,
                        char_start=current_start,
                        char_end=current_start + len(current),
                    )
                )
                # Start new chunk with overlap from previous
                if overlap > 0 and len(current) > overlap:
                    overlap_text = current[-overlap:]
                    current = overlap_text + "\n\n" + para
                else:
                    current = para
                current_start = current_start + len(current) - len(para)

        # Final paragraph(s)
        if current.strip():
            chunks.append(
                Chunk(
                    text=current.strip(),
                    section_title=section_title,
                    section_path=section_path_str,
                    char_start=current_start,
                    char_end=current_start + len(current),
                )
            )

    return chunks


def _parse_sections(
    md_text: str,
) -> list[tuple[list[str], str, int]]:
    """Parse Markdown into a list of (heading_breadcrumb, body_text, char_offset).

    Each element is a tuple:
        heading_path: list of heading texts forming the breadcrumb (e.g. ["财务报表", "资产负债表"])
        body_text: the text content under that heading (up to the next heading of same or higher level)
        char_offset: starting character position in the original text
    """
    matches = list(_HEADING_PATTERN.finditer(md_text))
    if not matches:
        return [([], md_text, 0)]

    sections: list[tuple[list[str], str, int]] = []
    # Stack of (level, heading_text); level = number of # characters
    heading_stack: list[tuple[int, str]] = []

    for i, match in enumerate(matches):
        level = len(match.group(1))
        heading_text = match.group(2).strip()

        # Pop headings that are at same or deeper level
        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        heading_stack.append((level, heading_text))

        # Content runs from end of this heading line to start of next heading
        content_start = match.end()
        if i + 1 < len(matches):
            content_end = matches[i + 1].start()
        else:
            content_end = len(md_text)

        body = md_text[content_start:content_end]
        path = [h[1] for h in heading_stack]

        sections.append((path, body, content_start))

    return sections
