"""输入处理模块。"""

from input.file_router import (
    FileKind,
    build_uploaded_file,
    detect_file_kind,
    format_student_input,
    load_file_for_graph,
    parse_file_text,
)
from input.multimodal_processor import (
    ContentBlock,
    Modality,
    MultimodalProcessor,
    MultimodalResult,
    is_supported_file,
    load_for_graph,
    supported_extensions,
)
from input.pdf_parser import load_pdf_for_graph, parse_pdf_text

__all__ = [
    "ContentBlock",
    "FileKind",
    "Modality",
    "MultimodalProcessor",
    "MultimodalResult",
    "build_uploaded_file",
    "detect_file_kind",
    "format_student_input",
    "is_supported_file",
    "load_file_for_graph",
    "load_for_graph",
    "load_pdf_for_graph",
    "parse_file_text",
    "parse_pdf_text",
    "supported_extensions",
]
