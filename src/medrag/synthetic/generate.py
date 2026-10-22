"""
generate.py - turns the patient stories into PDF documents plus an answer key.

This is where everything comes together:
    patients.py  says WHAT happens to each patient
    catalog.py   says how each test and lab works
    render.py    says what each document LOOKS like
    generate.py  (this file) works through each story and creates the files

For each patient it does three things, in order:
    1. Lab reports:   for every blood-test visit, work out each result, decide
                      whether it's high/low, and draw the lab report PDF.
    2. GP visits:     for every doctor's visit, draw the prescription and/or clinic note.
    3. Answer key:    record every medicine and built-in surprise.

Then it writes the answer-key CSV files. Later, we'll compare what the AI extracts
from the PDFs against these files to measure accuracy.

Output (inside the folder passed to generate(), e.g. data/synthetic/):
    patients/<patient_id>/<date>_lab_report_<lab>.pdf
    patients/<patient_id>/<date>_prescription.pdf
    patients/<patient_id>/<date>_clinic_note.pdf
    ground_truth/patients.csv       who each patient is
    ground_truth/documents.csv      every document created
    ground_truth/lab_results.csv    every printed result (as printed, and in standard units)
    ground_truth/medications.csv    every medicine with start and end dates
    ground_truth/clinic_notes.csv   the full text of every clinic note
    ground_truth/events.csv         the surprises built into each story
"""

import csv
import random
import re
import shutil
from datetime import date, timedelta
from pathlib import Path

# The "." means "from this same package" (the synthetic folder)
from .catalog import CONDITIONS, LABS, TESTS, printed_test
from .patients import PATIENTS, Patient
from .render import (ClinicNoteDoc, LabReport, Prescription, ResultRow,
                     render_clinic_note, render_lab_report, render_prescription)

CLINIC = ("Riverbend Medical Clinic", "42 Sample Road, Melbourne VIC 3000")  # (name, address)
DAYS_PER_MONTH = 30.44   # average month length (365.25 / 12)


# =============================================================================
# SMALL HELPER FUNCTIONS
# =============================================================================

def interpolate(points: list[tuple[float, float]], month: float) -> float:
    """
    Find a value at any month by drawing straight lines between key points.

    Args:
        points: Key points as [(month, value), ...], e.g. [(0, 8.9), (6, 7.6)].
        month:  The month we want a value for.

    Returns:
        The value at that month. Before the first point it stays at the first value;
        after the last point it stays at the last value.

    Example:
        interpolate([(0, 10), (10, 20)], 5)  ->  15.0   (halfway between)
    """
    points = sorted(points)
    if month <= points[0][0]:
        return points[0][1]
    # zip(points, points[1:]) pairs each point with the next: (p0, p1), (p1, p2), ...
    for (m0, v0), (m1, v1) in zip(points, points[1:]):
        if month <= m1:
            fraction = (month - m0) / (m1 - m0)   # how far between the two points (0 to 1)
            return v0 + (v1 - v0) * fraction
    return points[-1][1]


def flag(value: float, low: float | None, high: float | None) -> str:
    """
    Compare a result with its normal range.

    Args:
        value: The printed result.
        low:   Bottom of the normal range, or None if there isn't one.
        high:  Top of the normal range, or None if there isn't one.

    Returns:
        "H" if above the range, "L" if below, "" (empty) if within it.
    """
    if high is not None and value > high:
        return "H"
    if low is not None and value < low:
        return "L"
    return ""


def date_at(p: Patient, month: float, jitter_days: int = 0) -> date:
    """
    Convert a story month into a real calendar date for this patient.

    Args:
        p:           The patient (their `start` date is month 0).
        month:       Months since the start, e.g. 12.5.
        jitter_days: Days to shift by, so visits don't fall on perfectly regular dates.

    Example:
        Patient starting 2023-07-03, month 3  ->  about 2023-10-02
    """
    return p.start + timedelta(days=round(month * DAYS_PER_MONTH) + jitter_days)


def fill_placeholders(text: str, printed: dict[tuple[int, str], str]) -> str:
    r"""
    Replace every {CODE@month} in a clinic note with the real printed result.

    Args:
        text:    Note text, e.g. "HbA1c {HBA1C@0}, eGFR {EGFR@0}."
        printed: Lookup of printed results, {(month, code): "8.9%"}.

    Returns:
        The text with values filled in, e.g. "HbA1c 8.9%, eGFR 74 mL/min/1.73m²."

    How the pattern works:  \{(\w+)@(\d+)\}
        \{ and \}     literal curly brackets
        (\w+)        group 1: the test code (letters, digits, underscore)
        @            a literal @
        (\d+)        group 2: the month (digits)
    For each match, the lambda builds the key (month, code) and looks up the value.
    """
    return re.sub(r"\{(\w+)@(\d+)\}", lambda m: printed[(int(m[2]), m[1])], text)


def write_csv(path: Path, rows: list[dict]) -> None:
    """
    Save a list of dictionaries as a CSV file. The keys of the first row become the
    column headers.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="" stops blank lines appearing between rows on Windows
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


# =============================================================================
# THE MAIN FUNCTION
# =============================================================================

def generate(out_dir: Path, seed: int = 42) -> dict[str, int]:
    """
    Create every PDF and answer-key file for all patients.

    Args:
        out_dir: Folder to write into, e.g. data/synthetic. It is deleted and
                 recreated, so old files never mix with new ones.
        seed:    Starting number for the random generator. The same seed always
                 gives exactly the same "random" wobble, dates and lab numbers,
                 so anyone running the code gets identical files.

    Returns:
        How many of each thing was created, e.g. {"documents": 55, ...}.
    """
    if out_dir.exists():
        shutil.rmtree(out_dir)   # delete the old folder and everything in it
    rng = random.Random(seed)    # our own random generator, seeded for repeatability

    # Lists that collect the answer-key rows as we go
    patients, documents, results, medications, notes, events = [], [], [], [], [], []

    for p in PATIENTS:
        folder = out_dir / "patients" / p.patient_id   # "/" joins paths with pathlib
        patients.append({
            "patient_id": p.patient_id, "name": p.name, "sex": p.sex, "dob": p.dob.isoformat(),
            "conditions": "; ".join(CONDITIONS[c].label for c in p.conditions),
        })

        visit_doc: dict[int, tuple[str, date]] = {}  # month -> (lab report doc_id, date), for events
        printed: dict[tuple[int, str], str] = {}     # (month, code) -> "8.9%", for clinic notes

        # ---------------------------------------------------------------------
        # 1. LAB REPORTS: one PDF per blood-test visit
        # ---------------------------------------------------------------------
        for month, codes in sorted(p.visits.items()):
            lab = LABS[p.lab_for_month[month]]
            collected = date_at(p, month, rng.randint(-4, 4))      # +/- 4 days, like real life
            reported = collected + timedelta(days=rng.randint(1, 2))
            doc_id = f"{p.patient_id}-LAB-{collected.isoformat()}"  # e.g. "P001-LAB-2023-06-30"
            file = folder / f"{collected.isoformat()}_lab_report_{lab.key}.pdf"
            visit_doc[month] = (doc_id, collected)

            rows = []
            # Sort by the order tests are listed in TESTS, so each panel stays together
            for code in sorted(codes, key=list(TESTS).index):
                test = TESTS[code]

                # The "true" value from the story, plus a small random wobble
                true_value = interpolate(p.trajectories[code], month)
                value = true_value * (1 + rng.gauss(0, p.noise_pct))   # gauss = bell-curve random
                value = round(value, test.decimals) if test.decimals else round(value)

                # How this particular lab prints it (name, units, rounding, range)
                name, shown, unit, decimals, low, high = printed_test(lab, test, p.sex, value)
                f = flag(shown, low, high)
                rows.append(ResultRow(test.panel, name, shown, unit, decimals, low, high, f))

                # Remember the printed text so clinic notes can quote it, e.g. "8.9%" or "7.0 mmol/L"
                spacer = "" if unit == "%" else " "
                printed[(month, code)] = f"{shown:.{decimals}f}{spacer}{unit}"

                # Answer key: what's printed on the page AND the value in standard units
                results.append({
                    "doc_id": doc_id, "patient_id": p.patient_id,
                    "collected_date": collected.isoformat(), "lab": lab.name,
                    "test_code": code, "test_name_printed": name,
                    "value_printed": f"{shown:.{decimals}f}", "unit_printed": unit,
                    "ref_low": "" if low is None else low, "ref_high": "" if high is None else high,
                    "flag": f, "value_standard": value, "unit_standard": test.unit,
                })

            render_lab_report(LabReport(
                lab_name=lab.name, lab_address=lab.address, layout=lab.layout,
                lab_number=f"{lab.key[:2].upper()}-{collected:%y}-{rng.randint(100000, 999999)}",
                patient_name=p.name, patient_id=p.patient_id, sex=p.sex, dob=p.dob,
                doctor=p.doctor, collected=collected, reported=reported, rows=rows), file)
            documents.append({"doc_id": doc_id, "patient_id": p.patient_id, "doc_type": "lab_report",
                              "date": collected.isoformat(), "issuer": lab.name,
                              "file": file.relative_to(out_dir).as_posix()})

        # ---------------------------------------------------------------------
        # 2. GP VISITS: a prescription and/or a clinic note, on the same day
        # ---------------------------------------------------------------------
        # A GP visit happens whenever a medicine starts/changes, a reissue is written,
        # or a clinic note exists. The "|" joins two sets (union).
        rx_months = {m.start_month for m in p.medications} | {r.month for r in p.reissues}
        note_months = {n.month for n in p.notes}
        rx_doc: dict[float, tuple[str, str]] = {}   # month -> (prescription doc_id, date)

        for month in sorted(rx_months | note_months):
            visit = date_at(p, month, rng.randint(-2, 2))   # one date shared by both documents

            # --- Prescription
            if month in rx_months:
                # Medicines being taken on this date: started already, and not yet ended
                active = [m for m in p.medications
                          if m.start_month <= month and (m.end_month is None or m.end_month > month)]
                # Notes: explain anything that started today, plus any reissue advice
                rx_notes = [m.note for m in p.medications if m.start_month == month and m.note]
                rx_notes += [r.note for r in p.reissues if r.month == month]

                doc_id = f"{p.patient_id}-RX-{visit.isoformat()}"
                file = folder / f"{visit.isoformat()}_prescription.pdf"
                rx_doc[month] = (doc_id, visit.isoformat())
                render_prescription(Prescription(
                    clinic=CLINIC[0], clinic_address=CLINIC[1], doctor=p.doctor,
                    patient_name=p.name, patient_id=p.patient_id, dob=p.dob, issued=visit,
                    items=[(m.drug, m.strength, m.instructions) for m in active],
                    notes=rx_notes), file)
                documents.append({"doc_id": doc_id, "patient_id": p.patient_id,
                                  "doc_type": "prescription", "date": visit.isoformat(),
                                  "issuer": CLINIC[0], "file": file.relative_to(out_dir).as_posix()})

            # --- Clinic note
            for n in [n for n in p.notes if n.month == month]:
                reason = fill_placeholders(n.reason, printed)
                findings = fill_placeholders(n.findings, printed)
                plan = fill_placeholders(n.plan, printed)

                doc_id = f"{p.patient_id}-NOTE-{visit.isoformat()}"
                file = folder / f"{visit.isoformat()}_clinic_note.pdf"
                render_clinic_note(ClinicNoteDoc(
                    clinic=CLINIC[0], clinic_address=CLINIC[1], doctor=p.doctor,
                    patient_name=p.name, patient_id=p.patient_id, dob=p.dob, visit_date=visit,
                    reason=reason, findings=findings, plan=plan), file)
                documents.append({"doc_id": doc_id, "patient_id": p.patient_id,
                                  "doc_type": "clinic_note", "date": visit.isoformat(),
                                  "issuer": CLINIC[0], "file": file.relative_to(out_dir).as_posix()})
                notes.append({"doc_id": doc_id, "patient_id": p.patient_id, "date": visit.isoformat(),
                              "reason": reason, "findings": findings, "plan": plan})

        # ---------------------------------------------------------------------
        # 3. ANSWER KEY for medicines and built-in surprises
        # ---------------------------------------------------------------------
        for m in p.medications:
            start_doc, start_date = rx_doc[m.start_month]
            medications.append({
                "patient_id": p.patient_id, "drug": m.drug, "strength": m.strength,
                "instructions": m.instructions, "start_doc_id": start_doc, "start_date": start_date,
                # The end date is the date of the prescription that replaced it
                "end_date": "" if m.end_month is None else rx_doc[m.end_month][1],
            })
        for e in p.events:
            doc_id, collected = visit_doc[e.month]
            events.append({"patient_id": p.patient_id, "doc_id": doc_id,
                           "collected_date": collected.isoformat(), "test_code": e.test_code,
                           "kind": e.kind, "description": e.description})

    # Write all answer-key files
    gt = out_dir / "ground_truth"
    write_csv(gt / "patients.csv", patients)
    write_csv(gt / "documents.csv", sorted(documents, key=lambda d: (d["patient_id"], d["date"])))
    write_csv(gt / "lab_results.csv", results)
    write_csv(gt / "medications.csv", medications)
    write_csv(gt / "clinic_notes.csv", notes)
    write_csv(gt / "events.csv", events)

    return {"patients": len(patients), "documents": len(documents), "lab_results": len(results),
            "medication_courses": len(medications), "clinic_notes": len(notes), "events": len(events)}