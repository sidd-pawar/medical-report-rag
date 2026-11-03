"""
prescriptions.py - reads prescriptions with an LLM, then builds a medication timeline in code.

Why we need this: to say "HbA1c fell after empagliflozin was added", the system has to
know WHEN each medicine started, stopped or changed dose. That information is in the
prescription PDFs.

The same principle as lab reports:  the LLM reads, Python calculates.

    1. The LLM reads each prescription and lists the medicines on it (name, strength,
       directions), plus the date and the doctor's notes.         -> extract_prescription()
    2. Code compares each prescription with the patient's previous one to work out
       what changed: started, stopped, or dose changed.            -> build_timeline()

Each prescription lists ALL the medicines the patient is currently taking, so comparing
two in a row shows exactly what changed between them.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

from .config import CHAT_MODEL
from .llm import cached_parse, make_openai_parser
from .parsing import ParsedDocument

# =============================================================================
# 1. SCHEMA AND PROMPT
# =============================================================================
# As in extraction.py, these docstrings and descriptions are sent to the LLM.

class PrescribedMedicine(BaseModel):
    """One medicine listed on a prescription."""
    name: str = Field(description="Medicine name exactly as printed, e.g. 'Metformin'.")
    strength: str = Field(description="Strength exactly as printed, e.g. '500 mg' or '75 microgram'.")
    directions: str = Field(description="Directions exactly as printed.")


class ExtractedPrescription(BaseModel):
    """The details and medicines on one prescription."""
    issued_date: str = Field(description="Date the prescription was issued, as YYYY-MM-DD.")
    prescriber: str = Field(description="Name of the prescribing doctor.")
    medicines: list[PrescribedMedicine] = Field(description="Every medicine listed, in order.")
    notes: str = Field(description="The prescriber's notes, copied exactly. Empty string if none.")


INSTRUCTIONS = """You extract the details of a medical prescription from its text.

The text comes from a PDF, so table cells may appear one per line. Rebuild each row of the
medicines table: medicine, strength, directions.

Rules:
- List every medicine in the medicines table, and nothing else.
- Copy names, strengths and directions exactly as printed.
- Dates on the prescription are written DD/MM/YYYY. Return issued_date as YYYY-MM-DD.
- notes: copy the text under "Notes from prescriber" exactly. Do not summarise or add anything.
"""

PrescriptionParser = Callable[[str], tuple[ExtractedPrescription, dict]]


def extract_prescription(doc: ParsedDocument, cache_dir: Path,
                         parser: PrescriptionParser | None = None,
                         model: str = CHAT_MODEL) -> ExtractedPrescription:
    """
    Get the structured contents of one prescription, using the cache if possible.

    Args:
        doc:       A parsed prescription (from parsing.py).
        cache_dir: Folder of saved answers, one JSON file per document.
        parser:    The function that calls the LLM. None = OpenAI (only created if needed).
        model:     Model name, stored in the cache file.
    """
    if doc.doc_type != "prescription":
        raise ValueError(f"{doc.doc_id} is a {doc.doc_type}, not a prescription")
    return cached_parse(
        doc.doc_id, doc.text, cache_dir, ExtractedPrescription,
        make_parser=lambda: parser or make_openai_parser(ExtractedPrescription, INSTRUCTIONS, model),
        model=model,
    )


# =============================================================================
# 2. TIMELINE: work out what changed, in code
# =============================================================================

@dataclass
class MedicationCourse:
    """
    One medicine at one strength, from the prescription that started it until the
    prescription that stopped or changed it.

    Fields:
        patient_id:   Whose medicine it is.
        drug:         Medicine name.
        strength:     e.g. "500 mg".
        directions:   How to take it.
        start_date:   Issue date of the prescription where it first appears.
        start_doc_id: That prescription's document ID (so the app can cite it).
        end_date:     Issue date of the prescription where it was stopped or changed.
                      None = still being taken on the latest prescription.
    """
    patient_id: str
    drug: str
    strength: str
    directions: str
    start_date: str
    start_doc_id: str
    end_date: str | None = None


@dataclass
class MedicationChange:
    """
    One change between two prescriptions in a row.

    Fields:
        patient_id, date, doc_id: When and where the change happened.
        drug:   Medicine name.
        change: "started", "stopped" or "dose_changed".
        detail: Plain-English description, e.g. "500 mg -> 1000 mg".
    """
    patient_id: str
    date: str
    doc_id: str
    drug: str
    change: str
    detail: str


def _key(name: str) -> str:
    """Compare medicine names ignoring case and spaces: 'Metformin ' == 'metformin'."""
    return name.strip().lower()


def build_timeline(prescriptions: list[tuple[str, str, ExtractedPrescription]]
                   ) -> tuple[list[MedicationCourse], list[MedicationChange]]:
    """
    Turn a patient's prescriptions into medication courses and a list of changes.

    Args:
        prescriptions: (patient_id, doc_id, ExtractedPrescription) for every prescription.
                       Any order, any number of patients.

    Returns:
        (courses, changes)

    Example, for prescriptions on three dates:
        Jul: Metformin 500 mg, Perindopril 5 mg
        Oct: Metformin 1000 mg, Perindopril 5 mg
        Jul: Metformin 1000 mg, Perindopril 5 mg, Atorvastatin 20 mg
    gives changes:
        Jul  Metformin    started       500 mg
        Jul  Perindopril  started       5 mg
        Oct  Metformin    dose_changed  500 mg -> 1000 mg
        Jul  Atorvastatin started       20 mg
    """
    courses: list[MedicationCourse] = []
    changes: list[MedicationChange] = []

    # Handle each patient separately, oldest prescription first
    for patient_id in sorted({p for p, _, _ in prescriptions}):
        history = sorted((rx.issued_date, doc_id, rx) for p, doc_id, rx in prescriptions if p == patient_id)

        open_courses: dict[str, MedicationCourse] = {}   # medicine -> the course still running
        for date, doc_id, rx in history:
            current = {_key(m.name): m for m in rx.medicines}

            # Stopped: was running, but not on this prescription
            for key in list(open_courses):
                if key not in current:
                    course = open_courses.pop(key)
                    course.end_date = date
                    changes.append(MedicationChange(patient_id, date, doc_id, course.drug,
                                                    "stopped", course.strength))

            for key, med in current.items():
                running = open_courses.get(key)
                if running and running.strength == med.strength:
                    continue                                   # unchanged, nothing to record
                if running:                                    # same medicine, new strength
                    running.end_date = date
                    changes.append(MedicationChange(patient_id, date, doc_id, med.name, "dose_changed",
                                                    f"{running.strength} -> {med.strength}"))
                else:
                    changes.append(MedicationChange(patient_id, date, doc_id, med.name,
                                                    "started", med.strength))
                new_course = MedicationCourse(patient_id, med.name, med.strength, med.directions,
                                              start_date=date, start_doc_id=doc_id)
                courses.append(new_course)
                open_courses[key] = new_course

    return courses, changes