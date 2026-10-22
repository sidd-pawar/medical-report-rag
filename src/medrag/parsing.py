"""
parsing.py - reads PDF documents into plain text, keeping track of where text came from.

This is the first step of the AI pipeline: before an LLM can read a report, or before
we can search it, we need its text. We also keep each page separately and record
which patient and document it came from, so every answer can later cite its source,
e.g. "Lab report, 2 Jan 2025, page 1".

The document's details (patient, type, date) come from the folder and file name:
    <patients folder>/<patient_id>/<YYYY-MM-DD>_lab_report_<lab>.pdf
    <patients folder>/<patient_id>/<YYYY-MM-DD>_prescription.pdf
    <patients folder>/<patient_id>/<YYYY-MM-DD>_clinic_note.pdf

In a real app these details would be stored when a user uploads a file. Here the
naming convention plays that role.

Main functions:
    parse_pdf(path)                  -> one ParsedDocument
    load_documents(folder, patient)  -> all ParsedDocuments for one or all patients
"""

import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

# A "regular expression" describing valid file names (without the .pdf ending).
#   ^ and $             the whole name must match, start to end
#   (?P<date>...)       a named group called "date": 4 digits - 2 digits - 2 digits
#   (?P<kind>a|b|c)     a named group called "kind": one of the three document types
#   (?:_(?P<issuer>\w+))?   optionally "_" followed by the lab's key, e.g. "_kestrel"
_FILENAME = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})_(?P<kind>lab_report|prescription|clinic_note)(?:_(?P<issuer>\w+))?$"
)

# Short codes used in document IDs, e.g. "P001-LAB-2025-01-02".
# These match the IDs generate.py writes into the answer key.
_DOC_CODE = {"lab_report": "LAB", "prescription": "RX", "clinic_note": "NOTE"}


@dataclass(frozen=True)
class ParsedPage:
    """
    The text of one page.

    Fields:
        page_number: Counting from 1, the way a person would cite it ("page 1").
        text:        The cleaned-up text of the page.
    """
    page_number: int
    text: str


@dataclass(frozen=True)
class ParsedDocument:
    """
    One PDF turned into text, with the details needed to cite it.

    Fields:
        doc_id:     Unique ID, e.g. "P001-LAB-2025-01-02". Matches the answer key.
        patient_id: Whose document it is, e.g. "P001".
        doc_type:   "lab_report", "prescription" or "clinic_note".
        date:       Date from the file name, as "YYYY-MM-DD".
        path:       Where the PDF file is.
        pages:      The text of each page, in order.
    """
    doc_id: str
    patient_id: str
    doc_type: str
    date: str
    path: Path
    pages: tuple[ParsedPage, ...]   # a tuple (not a list) so the object can't be changed

    @property
    def text(self) -> str:
        """All pages joined into one string, for when page numbers don't matter."""
        return "\n".join(page.text for page in self.pages)


def parse_pdf(path: Path) -> ParsedDocument:
    """
    Read one patient PDF and return its text and details.

    Args:
        path: The PDF file, inside a folder named after the patient,
              e.g. data/synthetic/patients/P001/2025-01-02_lab_report_bluegum.pdf

    Returns:
        A ParsedDocument.

    Raises:
        ValueError: If the file name doesn't follow the naming convention, so we
                    can't tell what kind of document it is.
    """
    path = Path(path)
    match = _FILENAME.match(path.stem)   # .stem is the file name without ".pdf"
    if not match:
        raise ValueError(
            f"Unexpected file name: {path.name}. Expected YYYY-MM-DD_lab_report_<lab>.pdf, "
            "YYYY-MM-DD_prescription.pdf or YYYY-MM-DD_clinic_note.pdf"
        )

    patient_id = path.parent.name        # the folder the file is in, e.g. "P001"
    doc_type = match["kind"]
    doc_date = match["date"]

    # pypdf reads the PDF; extract_text() pulls the text out of each page.
    # "or ''" handles a page with no text (e.g. a scanned image) without crashing.
    reader = PdfReader(path)
    pages = tuple(
        ParsedPage(page_number=i, text=_clean(page.extract_text() or ""))
        for i, page in enumerate(reader.pages, start=1)
    )

    return ParsedDocument(
        doc_id=f"{patient_id}-{_DOC_CODE[doc_type]}-{doc_date}",
        patient_id=patient_id,
        doc_type=doc_type,
        date=doc_date,
        path=path,
        pages=pages,
    )


def load_documents(patients_folder: Path, patient_id: str | None = None) -> list[ParsedDocument]:
    """
    Read every PDF for one patient, or for all patients.

    Args:
        patients_folder: The folder holding one sub-folder per patient,
                         e.g. data/synthetic/patients
        patient_id:      e.g. "P001" for one patient. Leave out (None) for everyone.

    Returns:
        A list of ParsedDocuments, sorted by patient then date (oldest first).
    """
    if patient_id:
        folders = [patients_folder / patient_id]
    else:
        folders = sorted(f for f in patients_folder.iterdir() if f.is_dir())

    documents = [parse_pdf(pdf) for folder in folders for pdf in sorted(folder.glob("*.pdf"))]
    return sorted(documents, key=lambda d: (d.patient_id, d.date, d.doc_type))


def _clean(text: str) -> str:
    """
    Tidy up text extracted from a PDF.

    - Replaces non-breaking spaces with normal spaces (PDFs often contain them).
    - Collapses runs of spaces/tabs into a single space.
    - Strips spaces from the start and end of each line, and drops empty lines.
    """
    text = text.replace("\xa0", " ")           # \xa0 is a non-breaking space
    text = re.sub(r"[ \t]+", " ", text)        # many spaces/tabs -> one space
    lines = (line.strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)