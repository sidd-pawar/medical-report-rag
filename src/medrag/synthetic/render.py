"""
render.py - draws the PDF documents: lab reports, prescriptions and clinic notes.

This file only handles HOW documents look. It doesn't decide any values; generate.py
works out the content and passes it in.

It uses the `reportlab` library. Reportlab builds a PDF from a list of "flowables",
which are blocks like a paragraph, a table or some blank space. We call that list the
"story": you add blocks to it in order, then reportlab lays them out on A4 pages.

There are three document types:
    render_lab_report()    two different lab layouts ("A" and "B"), like real labs
    render_prescription()  a GP prescription listing current medicines
    render_clinic_note()   a GP's written note: reason, findings, plan

Every page gets a footer saying the data is synthetic, so nobody mistakes it for a
real medical record.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# By default reportlab writes the current time and a random ID into every PDF, so the
# same input would give slightly different files each run. "invariant" turns that off,
# so regenerating gives byte-identical PDFs (Git then only shows real changes).
rl_config.invariant = 1

DISCLAIMER = ("SYNTHETIC DATA: fictional patient and provider, generated for software testing. "
              "Not a real medical record.")

# Text styles. We start from reportlab's built-in styles and adjust the sizes.
_styles = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=_styles["Heading1"], fontSize=15, spaceAfter=1 * mm)
H2 = ParagraphStyle("h2", parent=_styles["Heading2"], fontSize=11, spaceBefore=3 * mm, spaceAfter=1 * mm)
BODY = ParagraphStyle("body", parent=_styles["BodyText"], fontSize=9, leading=12)  # leading = line spacing
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, textColor=colors.grey)


# =============================================================================
# THE CONTENT OF EACH DOCUMENT TYPE
# =============================================================================
# generate.py fills one of these in, then calls the matching render_... function.

@dataclass
class ResultRow:
    """
    One line on a lab report, e.g. "Potassium  5.8  H  mmol/L  3.5 - 5.2".

    Fields:
        panel:     Group heading, e.g. "Electrolytes".
        name:      Test name as this lab prints it.
        value:     The result (already rounded).
        unit:      Unit as this lab prints it.
        decimals:  How many decimal places to show.
        ref_low:   Bottom of the normal range, or None.
        ref_high:  Top of the normal range, or None.
        flag:      "H" (above range), "L" (below range) or "" (normal).
    """
    panel: str
    name: str
    value: float
    unit: str
    decimals: int
    ref_low: float | None
    ref_high: float | None
    flag: str

    @property  # lets you write row.value_text instead of row.value_text()
    def value_text(self) -> str:
        """The value formatted with the right decimals, e.g. 4.6 -> "4.6", 139 -> "139"."""
        return f"{self.value:.{self.decimals}f}"

    @property
    def ref_text(self) -> str:
        """
        The normal range written the way labs print it:
            both limits  -> "3.5 - 5.2"
            only a top   -> "< 3.0"
            only a bottom-> "> 60"
        """
        def fmt(v):
            return f"{v:.{self.decimals}f}"

        if self.ref_low is not None and self.ref_high is not None:
            return f"{fmt(self.ref_low)} - {fmt(self.ref_high)}"
        if self.ref_high is not None:
            return f"< {fmt(self.ref_high)}"
        return f"> {fmt(self.ref_low)}"


@dataclass
class LabReport:
    """
    Everything printed on one lab report.

    Fields:
        lab_name, lab_address: The lab, printed at the top.
        layout:        "A" or "B" (see _layout_a and _layout_b below).
        lab_number:    The lab's reference number for this test, e.g. "KE-24-816751".
        patient_name, patient_id, sex, dob: The patient.
        doctor:        The GP who requested the test.
        collected:     Date the blood was taken.
        reported:      Date the lab issued the report (a day or two later).
        rows:          The results, as a list of ResultRow.
    """
    lab_name: str
    lab_address: str
    layout: str
    lab_number: str
    patient_name: str
    patient_id: str
    sex: str
    dob: date
    doctor: str
    collected: date
    reported: date
    rows: list[ResultRow]


@dataclass
class Prescription:
    """
    Everything printed on one prescription.

    Fields:
        clinic, clinic_address: The GP clinic.
        doctor:        The prescribing doctor.
        patient_name, patient_id, dob: The patient.
        issued:        Date of the prescription.
        items:         Current medicines as (medicine, strength, directions) tuples.
        notes:         Explanations from the doctor, e.g. why a dose changed.
    """
    clinic: str
    clinic_address: str
    doctor: str
    patient_name: str
    patient_id: str
    dob: date
    issued: date
    items: list[tuple[str, str, str]]
    notes: list[str]


@dataclass
class ClinicNoteDoc:
    """
    Everything printed on one clinic note.

    Fields:
        clinic, clinic_address, doctor: Who wrote it.
        patient_name, patient_id, dob:  The patient.
        visit_date:   Date of the consultation.
        reason, findings, plan: The three sections of the note (placeholders already filled in).
    """
    clinic: str
    clinic_address: str
    doctor: str
    patient_name: str
    patient_id: str
    dob: date
    visit_date: date
    reason: str
    findings: str
    plan: str


# =============================================================================
# SHARED HELPERS
# =============================================================================
# Names starting with "_" are "private": only meant to be used inside this file.

def _d(d: date) -> str:
    """Format a date the Australian way: 2024-07-01 -> "01/07/2024"."""
    return d.strftime("%d/%m/%Y")


def _footer(canvas, doc):
    """
    Draw the disclaimer and page number at the bottom of every page.

    Reportlab calls this automatically for each page. `canvas` is the drawing surface
    for the page and `doc` is the document being built.
    """
    canvas.saveState()                        # remember the current font/colour settings
    canvas.setFont("Helvetica-Oblique", 7.5)
    canvas.setFillColor(colors.grey)
    canvas.drawString(15 * mm, 10 * mm, DISCLAIMER)                 # bottom left
    canvas.drawRightString(A4[0] - 15 * mm, 10 * mm, f"Page {doc.page}")  # bottom right
    canvas.restoreState()                     # put the settings back


def _build(path: Path, story: list, title: str) -> None:
    """
    Turn a list of blocks (the "story") into a PDF file.

    Args:
        path:  Where to save the PDF. Missing folders are created.
        story: Reportlab blocks (Paragraph, Table, Spacer...) in page order.
        title: Stored in the PDF's properties (shown by some PDF viewers).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path), pagesize=A4, title=title, author="Synthetic data generator",
                            leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=18 * mm)
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)


def _info_table(pairs: list[tuple[str, str]], widths) -> Table:
    """
    A small two-column table of labels and values, e.g. "Patient | Arun Mehta".

    Args:
        pairs:  List of (label, value) pairs, one per row.
        widths: Column widths, e.g. [30 * mm, 120 * mm].
    """
    rows = [[Paragraph(f"<b>{label}</b>", BODY), Paragraph(value, BODY)] for label, value in pairs]
    table = Table(rows, colWidths=widths, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
    ]))
    return table

# A note on TableStyle: each rule is (command, (first col, first row), (last col, last row), ...).
# Negative numbers count from the end, so (0, 0) to (-1, -1) means "the whole table".


# =============================================================================
# LAB REPORTS
# =============================================================================

def render_lab_report(report: LabReport, path: Path) -> None:
    """
    Save a lab report as a PDF, using the layout of the lab that produced it.

    Args:
        report: The content (see LabReport).
        path:   Where to save the PDF.
    """
    story = _layout_a(report) if report.layout == "A" else _layout_b(report)
    _build(path, story, f"{report.lab_name} report {report.lab_number}")


def _layout_a(r: LabReport) -> list:
    """
    Layout A (Kestrel Pathology): a boxed patient header, then ONE TABLE PER PANEL
    with a separate "Flag" column. No comments section.
    """
    story = [Paragraph(r.lab_name, H1), Paragraph(r.lab_address, SMALL), Spacer(1, 4 * mm)]

    # Patient details on the left, test details on the right, inside one box
    left = _info_table([("Patient", r.patient_name), ("Patient ID", r.patient_id),
                        ("Date of birth", _d(r.dob)), ("Sex", "Male" if r.sex == "M" else "Female")],
                       [28 * mm, 55 * mm])
    right = _info_table([("Lab number", r.lab_number), ("Requested by", r.doctor),
                         ("Collected", _d(r.collected)), ("Reported", _d(r.reported))],
                        [28 * mm, 55 * mm])
    box = Table([[left, right]], colWidths=[90 * mm, 90 * mm])
    box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                             ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [box, Spacer(1, 2 * mm)]

    # Group the rows by panel, keeping their order: {"Diabetes": [row, row], "Lipids": [...]}
    panels: dict[str, list[ResultRow]] = {}
    for row in r.rows:
        panels.setdefault(row.panel, []).append(row)   # setdefault creates the list the first time

    for panel, rows in panels.items():
        story.append(Paragraph(panel.upper(), H2))
        data = [["Test", "Result", "Flag", "Units", "Reference range"]]          # header row
        data += [[x.name, x.value_text, x.flag, x.unit, x.ref_text] for x in rows]
        table = Table(data, colWidths=[62 * mm, 22 * mm, 14 * mm, 34 * mm, 38 * mm])
        style = [
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),          # header row bold
            ("FONT", (0, 1), (-1, -1), "Helvetica", 9),              # other rows normal
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),       # line under header
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F5F7")]),  # stripes
        ]
        # Make the result and flag bold for any out-of-range row
        for i, x in enumerate(rows, start=1):   # start=1 because row 0 is the header
            if x.flag:
                style.append(("FONT", (1, i), (2, i), "Helvetica-Bold", 9))
        table.setStyle(TableStyle(style))
        story.append(table)

    story += [Spacer(1, 4 * mm), Paragraph("H = above reference range, L = below reference range.", SMALL)]
    return story


def _layout_b(r: LabReport) -> list:
    """
    Layout B (Bluegum Diagnostics): patient details as plain lines, then ONE BIG TABLE
    with panel names as shaded rows, the flag written next to the result ("7.4 H"),
    and a "Comments" section at the end.
    """
    story = [
        Paragraph("LABORATORY REPORT", H1),
        Paragraph(f"{r.lab_name} | {r.lab_address}", SMALL),
        Spacer(1, 3 * mm),
        # &nbsp; is a non-breaking space, used here to put gaps between the details
        Paragraph(f"<b>Name:</b> {r.patient_name} &nbsp;&nbsp; <b>ID:</b> {r.patient_id} &nbsp;&nbsp; "
                  f"<b>DOB:</b> {_d(r.dob)} &nbsp;&nbsp; <b>Sex:</b> {r.sex}", BODY),
        Paragraph(f"<b>Referring doctor:</b> {r.doctor} &nbsp;&nbsp; <b>Accession:</b> {r.lab_number}", BODY),
        Paragraph(f"<b>Specimen collected:</b> {_d(r.collected)} &nbsp;&nbsp; "
                  f"<b>Report date:</b> {_d(r.reported)}", BODY),
        Spacer(1, 3 * mm),
    ]

    data = [["Analyte", "Result", "Units", "Ref. interval"]]
    style = [
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
    ]
    current_panel = None
    for x in r.rows:
        # When the panel changes, insert a shaded heading row that spans all 4 columns
        if x.panel != current_panel:
            current_panel = x.panel
            data.append([x.panel, "", "", ""])
            i = len(data) - 1   # index of the row just added
            style += [("FONT", (0, i), (-1, i), "Helvetica-BoldOblique", 9),
                      ("SPAN", (0, i), (-1, i)),
                      ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#E8EEF2"))]
        result = f"{x.value_text} {x.flag}".strip()     # e.g. "7.4 H", or "4.6" if normal
        data.append(["   " + x.name, result, x.unit, x.ref_text])
        if x.flag:
            i = len(data) - 1
            style.append(("FONT", (1, i), (1, i), "Helvetica-Bold", 9))
    table = Table(data, colWidths=[70 * mm, 30 * mm, 38 * mm, 42 * mm])
    table.setStyle(TableStyle(style))
    story.append(table)

    # Comments: one sentence per out-of-range result (useful text for RAG later)
    story.append(Paragraph("Comments", H2))
    flagged = [x for x in r.rows if x.flag]
    if flagged:
        for x in flagged:
            direction = "above" if x.flag == "H" else "below"
            story.append(Paragraph(f"{x.name} is {direction} the reference interval. "
                                   "Please interpret in clinical context.", BODY))
    else:
        story.append(Paragraph("All results within reference intervals.", BODY))
    return story


# =============================================================================
# PRESCRIPTIONS AND CLINIC NOTES
# =============================================================================

def _clinic_header(clinic: str, address: str, title: str) -> list:
    """The top of every clinic document: clinic name, address and the document title."""
    return [Paragraph(clinic, H1), Paragraph(address, SMALL), Spacer(1, 3 * mm), Paragraph(title, H2)]


def render_prescription(p: Prescription, path: Path) -> None:
    """
    Save a prescription as a PDF: patient details, a table of current medicines,
    then the doctor's notes explaining any changes.

    Args:
        p:    The content (see Prescription).
        path: Where to save the PDF.
    """
    story = _clinic_header(p.clinic, p.clinic_address, "PRESCRIPTION")
    story += [
        _info_table([("Patient", p.patient_name), ("Patient ID", p.patient_id),
                     ("Date of birth", _d(p.dob)), ("Date issued", _d(p.issued)),
                     ("Prescriber", p.doctor)], [30 * mm, 120 * mm]),
        Spacer(1, 3 * mm),
    ]

    data = [["Medicine", "Strength", "Directions"]] + [list(item) for item in p.items]
    table = Table(data, colWidths=[45 * mm, 35 * mm, 100 * mm])
    table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF2")),
    ]))
    story += [table, Paragraph("Notes from prescriber", H2)]

    if p.notes:
        story += [Paragraph(note, BODY) for note in p.notes]
    else:
        story.append(Paragraph("Repeat prescription. No changes.", BODY))

    story += [Spacer(1, 10 * mm), Paragraph(f"{p.doctor} (electronic signature)", BODY)]
    _build(path, story, f"Prescription {p.patient_id} {p.issued.isoformat()}")


def render_clinic_note(n: ClinicNoteDoc, path: Path) -> None:
    """
    Save a clinic note as a PDF with three sections: Reason for visit, Findings, Plan.

    Args:
        n:    The content (see ClinicNoteDoc).
        path: Where to save the PDF.
    """
    story = _clinic_header(n.clinic, n.clinic_address, "CLINIC NOTE")
    story += [
        _info_table([("Patient", n.patient_name), ("Patient ID", n.patient_id),
                     ("Date of birth", _d(n.dob)), ("Date of visit", _d(n.visit_date)),
                     ("Doctor", n.doctor)], [30 * mm, 120 * mm]),
        Spacer(1, 2 * mm),
    ]
    for heading, text in [("Reason for visit", n.reason), ("Findings", n.findings), ("Plan", n.plan)]:
        story += [Paragraph(heading, H2), Paragraph(text, BODY)]

    story += [Spacer(1, 10 * mm), Paragraph(f"{n.doctor} (electronic signature)", BODY)]
    _build(path, story, f"Clinic note {n.patient_id} {n.visit_date.isoformat()}")