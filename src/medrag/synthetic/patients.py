"""
patients.py - three fictional patients, each with a scripted multi-year medical story.

Instead of random numbers, every patient has a STORY written in advance: when they
had blood tests, how their results changed, when medicines started or changed, and
what their doctor wrote. The generator (generate.py) turns each story into PDFs.

Each story is made of:
    visits        Which month each blood test happened, and which tests were done.
    trajectories  A few key points for how each result moves over time.
                  The generator draws straight lines between them.
    medications   When each medicine started and stopped.
    notes         The doctor's clinic notes (written text, for the RAG search later).
    events        Surprises built in on purpose, e.g. a sudden kidney result drop.
                  These are the answer key for anomaly detection later.

About "months": every date is written as months since the patient's start date.
Month 0 is their first blood test; month 12.5 is about a year and two weeks later.
Fractions like 0.7 are used so a doctor's visit lands a few weeks AFTER a blood test.

About placeholders in clinic notes: write {CODE@month} and the generator replaces it
with the exact result printed on that month's lab report. For example {HBA1C@0}
becomes "8.9%". This guarantees the letters always match the lab reports.

All people, places and values are invented. Any resemblance to real people is coincidental.
"""

from dataclasses import dataclass, field
from datetime import date


# =============================================================================
# BUILDING BLOCKS OF A STORY
# =============================================================================

@dataclass(frozen=True)
class Medication:
    """
    One course of one medicine at one strength.

    A dose change is written as two Medications: the old one ends in the same month
    the new one starts.

    Fields:
        drug:         Medicine name. Must be listed for one of the patient's conditions
                      in catalog.CONDITIONS, or the tests will fail.
        strength:     e.g. "500 mg".
        instructions: How to take it, printed on the prescription.
        start_month:  Month the doctor prescribed it.
        end_month:    Month it was stopped or changed. None = still taking it.
        note:         Explanation printed on the prescription, e.g. why it changed.

    Example:
        Medication("Metformin", "500 mg", "1 tablet twice daily", 0.7, 3.5, "Started metformin.")
        means metformin 500 mg was taken from month 0.7 until month 3.5.
    """
    drug: str
    strength: str
    instructions: str
    start_month: float
    end_month: float | None = None
    note: str = ""


@dataclass(frozen=True)
class Reissue:
    """
    A prescription written WITHOUT any medicine change, e.g. to give advice after
    an unexpected result. It lists the patient's current medicines plus the note.

    Fields:
        month: Month of the doctor's visit.
        note:  The advice printed on the prescription.
    """
    month: float
    note: str


@dataclass(frozen=True)
class ClinicNote:
    """
    The doctor's written note from one visit. Each becomes a "Clinic note" PDF.

    These matter for RAG: lab reports are mostly tables of numbers, but notes are
    sentences, which is what search and question-answering work best on.

    Fields:
        month:    Month of the visit (the same month as any prescription that day).
        reason:   Why the patient came in.
        findings: What the doctor found. Use {CODE@month} placeholders for results.
        plan:     What happens next.
    """
    month: float
    reason: str
    findings: str
    plan: str


@dataclass(frozen=True)
class Event:
    """
    A surprise built into the story on purpose, so we can later check whether the
    system notices it. Written to events.csv as the answer key.

    Fields:
        month:       The visit where it shows up (must be a month in `visits`).
        test_code:   Which test it is about, e.g. "EGFR".
        kind:        One of:
                       "out_of_range"          - result outside the normal range
                       "sudden_change"         - a big jump compared with recent results
                       "trend_reversal"        - a result that was improving starts worsening
                       "response_to_treatment" - a result changes after a medicine change
        description: Plain-English explanation of what happened.
    """
    month: int
    test_code: str
    kind: str
    description: str


@dataclass
class Patient:
    """
    Everything about one fictional patient.

    Fields:
        patient_id:    Short ID used in file names, e.g. "P001".
        name, sex, dob: Basic details printed on every document.
        conditions:    Keys from catalog.CONDITIONS, e.g. ["type2_diabetes", "ckd"].
        doctor:        The patient's GP, printed on documents.
        start:         The real calendar date of month 0.
        visits:        {month: [test codes done that day]}.
        lab_for_month: {month: lab key}, which lab did each blood test.
        trajectories:  {test code: [(month, value), (month, value), ...]}.
                       Key points of the true value over time, in standard units.
        medications:   List of Medication.
        notes:         List of ClinicNote.
        events:        List of Event.
        reissues:      List of Reissue (optional).
        noise_pct:     Size of the random wobble added to each result.
                       0.012 means about +/-1.2%, so results look natural.
    """
    patient_id: str
    name: str
    sex: str
    dob: date
    conditions: list[str]
    doctor: str
    start: date
    visits: dict[int, list[str]]
    lab_for_month: dict[int, str]
    trajectories: dict[str, list[tuple[float, float]]]
    medications: list[Medication]
    notes: list[ClinicNote]
    events: list[Event]
    # field(default_factory=list) gives each patient its own empty list by default.
    # (Writing "= []" would make all patients share ONE list, a classic Python trap.)
    reissues: list[Reissue] = field(default_factory=list)
    noise_pct: float = 0.012


# Groups of tests that are usually ordered together, to keep the visit lists short
DIABETES = ["HBA1C", "GLU_F"]
KIDNEY = ["CREAT", "EGFR"]
SALTS = ["NA", "K"]                      # electrolytes: sodium and potassium
LIPIDS = ["CHOL", "LDL", "HDL", "TRIG"]  # cholesterol panel
LIVER = ["ALT", "AST"]
THYROID = ["TSH", "FT4"]


def creatinine_from_egfr(egfr_points, base_creat, base_egfr):
    """
    Work out creatinine key points from eGFR key points.

    eGFR (how well the kidneys filter) is calculated from creatinine, so the two
    always move in opposite directions: when eGFR falls, creatinine rises. Deriving
    one from the other keeps them consistent, instead of risking two lists that
    contradict each other.

    Args:
        egfr_points: [(month, eGFR), ...] key points for eGFR.
        base_creat:  The patient's creatinine at the first eGFR point.
        base_egfr:   The patient's eGFR at the first point.

    Returns:
        [(month, creatinine), ...] at the same months.

    The power of 1.1 is a simple approximation of the real eGFR formula.
    """
    return [(month, base_creat * (base_egfr / egfr) ** 1.1) for month, egfr in egfr_points]


# =============================================================================
# PATIENT 1: Arun Mehta - type 2 diabetes with early kidney disease
# =============================================================================
#
# Story:
#   - Diagnosed at month 0. Metformin + perindopril (kidney protection) started.
#   - HbA1c improves from 8.9% to about 7% within a year.
#   - Month 12: one-off high potassium. Atorvastatin started for cholesterol.
#   - Month 18: sudden eGFR drop after gastroenteritis (dehydration), partly recovers.
#   - Months 15-24: HbA1c creeps back up (less exercise after a knee injury).
#   - Month 24: empagliflozin added; HbA1c improves again.
#   - Changes lab at month 15, so HbA1c switches from % to mmol/mol.

p1_months = [0, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33]   # a blood test every 3 months
p1_egfr = [(0, 74), (15, 68), (18, 51), (21, 64), (24, 62), (27, 58), (30, 58), (33, 57)]

P001 = Patient(
    patient_id="P001",
    name="Arun Mehta",
    sex="M",
    dob=date(1968, 4, 17),
    conditions=["type2_diabetes", "ckd"],
    doctor="Dr Priya Raman",
    start=date(2023, 7, 3),
    # Every visit: sugar, kidneys and salts. Every 6 months: urine albumin.
    # Once a year: cholesterol panel and haemoglobin.
    visits={
        month: DIABETES + KIDNEY + SALTS
        + (["UACR"] if month % 6 == 0 else [])
        + (LIPIDS + ["HB"] if month in (0, 12, 24, 33) else [])
        for month in p1_months
    },
    lab_for_month={month: ("kestrel" if month < 15 else "bluegum") for month in p1_months},
    trajectories={
        "HBA1C": [(0, 8.9), (3, 8.4), (6, 7.6), (9, 7.1), (12, 6.9), (15, 7.0), (18, 7.2),
                  (21, 7.9), (24, 8.4), (27, 7.6), (30, 7.0), (33, 6.9)],
        "GLU_F": [(0, 10.2), (3, 9.1), (6, 8.0), (9, 7.3), (12, 7.0), (15, 7.1), (18, 7.4),
                  (21, 8.3), (24, 9.0), (27, 7.9), (30, 7.2), (33, 7.0)],
        "EGFR": p1_egfr,
        "CREAT": creatinine_from_egfr(p1_egfr, base_creat=92, base_egfr=74),
        "NA": [(0, 139), (33, 139)],                                   # steady
        "K": [(0, 4.4), (9, 4.6), (12, 5.8), (15, 4.6), (33, 4.5)],    # one-off spike at 12
        "UACR": [(0, 3.1), (12, 4.2), (24, 5.0), (30, 3.6)],
        "CHOL": [(0, 5.4), (12, 5.6), (24, 4.2), (33, 4.1)],
        "LDL": [(0, 3.2), (12, 3.3), (24, 2.0), (33, 1.9)],            # falls after statin
        "HDL": [(0, 1.0), (33, 1.1)],
        "TRIG": [(0, 2.4), (12, 2.5), (24, 2.0), (33, 1.8)],
        "HB": [(0, 142), (12, 139), (24, 136), (33, 135)],
    },
    medications=[
        Medication("Metformin", "500 mg", "1 tablet twice daily with meals", 0.7, 3.5,
                   "Started metformin for type 2 diabetes."),
        Medication("Metformin", "1000 mg", "1 tablet twice daily with meals", 3.5, None,
                   "Metformin increased from 500 mg to 1000 mg twice daily."),
        Medication("Perindopril", "5 mg", "1 tablet once daily", 0.7, None,
                   "Started perindopril to protect the kidneys."),
        Medication("Atorvastatin", "20 mg", "1 tablet once daily at night", 12.5, None,
                   "Started atorvastatin for cholesterol."),
        Medication("Empagliflozin", "10 mg", "1 tablet once daily in the morning", 24.5, None,
                   "Added empagliflozin as HbA1c has risen again."),
    ],
    notes=[
        ClinicNote(
            month=0.7,
            reason="Review of blood tests. Arun reports increased thirst and tiredness for about two months.",
            findings="HbA1c {HBA1C@0}, fasting glucose {GLU_F@0}. Kidney function: eGFR {EGFR@0}, "
                     "urine albumin/creatinine ratio {UACR@0}. Blood pressure 142/88.",
            plan="New diagnosis of type 2 diabetes with early signs of kidney involvement. Start metformin "
                 "500 mg twice daily and perindopril 5 mg daily. Referred to a dietitian. "
                 "Repeat bloods in 3 months.",
        ),
        ClinicNote(
            month=12.5,
            reason="Routine 12-month diabetes review.",
            findings="HbA1c {HBA1C@12}, much improved. Potassium {K@12}, above the normal range. "
                     "LDL cholesterol {LDL@12}.",
            plan="Potassium may be related to perindopril or to a delay in processing the sample. "
                 "Continue perindopril and recheck potassium at the next blood test. "
                 "Start atorvastatin 20 mg at night for cholesterol.",
        ),
        ClinicNote(
            month=18.4,
            reason="Follow-up of kidney results.",
            findings="eGFR {EGFR@18}, down from {EGFR@15} three months earlier. Creatinine {CREAT@18}. "
                     "Arun had gastroenteritis with vomiting and poor fluid intake in the week before the test.",
            plan="The drop is likely related to dehydration. Advised to keep up fluids. "
                 "Repeat kidney function in 3 months.",
        ),
        ClinicNote(
            month=24.5,
            reason="Diabetes review.",
            findings="HbA1c {HBA1C@24}, risen from {HBA1C@15} over the past 9 months. Arun has been less "
                     "active since a knee injury. eGFR {EGFR@24}.",
            plan="Add empagliflozin 10 mg each morning, which also helps protect the kidneys. "
                 "Discussed drinking enough water and good genital hygiene. Review in 3 months.",
        ),
    ],
    events=[
        Event(9, "HBA1C", "response_to_treatment", "HbA1c fell from 8.9% to about 7.1% after metformin was started and increased."),
        Event(12, "K", "out_of_range", "One-off high potassium (about 5.8 mmol/L); back in range at the next test."),
        Event(18, "EGFR", "sudden_change", "Sudden eGFR drop to about 51 (below range) after gastroenteritis; partly recovered by month 21."),
        Event(24, "HBA1C", "trend_reversal", "HbA1c rose again from about 7.0% to 8.4% between months 15 and 24."),
        Event(30, "HBA1C", "response_to_treatment", "HbA1c back to about 7.0% after empagliflozin was added."),
        Event(24, "LDL", "response_to_treatment", "LDL fell from about 3.3 to 2.0 mmol/L after atorvastatin was started."),
    ],
)


# =============================================================================
# PATIENT 2: Grace Liu - high blood pressure and high cholesterol
# =============================================================================
#
# Story ("does this medicine suit me?"):
#   - Month 0: amlodipine (blood pressure) and atorvastatin 20 mg (cholesterol) started.
#   - LDL falls, but not quite to target, so atorvastatin is increased to 40 mg at month 10.
#   - Months 13-16: liver enzymes (ALT, AST) and muscle enzyme (CK) rise; muscle aches.
#   - Month 16: switched to rosuvastatin. By month 19 everything is back to normal.

p2_months = [0, 3, 6, 10, 13, 16, 19, 23, 27, 31]
p2_egfr = [(0, 82), (31, 80)]

P002 = Patient(
    patient_id="P002",
    name="Grace Liu",
    sex="F",
    dob=date(1962, 9, 3),
    conditions=["hypertension", "high_cholesterol"],
    doctor="Dr Tom Hollis",
    start=date(2023, 10, 9),
    # Every visit: cholesterol and liver tests (routine on a statin).
    # Extra tests only at some visits, as a real GP would order them.
    visits={
        month: LIPIDS + LIVER
        + (["CK"] if month in (0, 13, 16, 19) else [])
        + (KIDNEY + SALTS if month in (0, 10, 19, 27) else [])
        + (["GLU_F"] if month in (0, 13, 27) else [])
        + (["HB"] if month in (0, 19) else [])
        for month in p2_months
    },
    lab_for_month={month: "kestrel" for month in p2_months},
    trajectories={
        "LDL": [(0, 4.6), (3, 3.2), (6, 3.1), (10, 3.0), (13, 2.3), (16, 2.2), (19, 2.1),
                (23, 2.0), (27, 2.1), (31, 2.0)],
        "HDL": [(0, 1.4), (31, 1.5)],
        "TRIG": [(0, 2.1), (6, 1.7), (13, 1.5), (31, 1.4)],
        "CHOL": [(0, 6.9), (3, 5.4), (6, 5.2), (10, 5.1), (13, 4.4), (16, 4.3), (19, 4.2),
                 (23, 4.1), (27, 4.2), (31, 4.1)],
        "ALT": [(0, 24), (10, 27), (13, 58), (16, 71), (19, 33), (23, 28), (31, 26)],   # side effect
        "AST": [(0, 22), (10, 24), (13, 44), (16, 52), (19, 27), (31, 23)],
        "CK": [(0, 110), (13, 190), (16, 240), (19, 120)],
        "EGFR": p2_egfr,
        "CREAT": creatinine_from_egfr(p2_egfr, base_creat=68, base_egfr=82),
        "NA": [(0, 140), (31, 140)],
        "K": [(0, 4.2), (31, 4.3)],
        "GLU_F": [(0, 5.3), (27, 5.5)],
        "HB": [(0, 132), (19, 134)],
    },
    medications=[
        Medication("Amlodipine", "5 mg", "1 tablet once daily", 0.5, None,
                   "Started amlodipine for blood pressure."),
        Medication("Atorvastatin", "20 mg", "1 tablet once daily at night", 0.5, 10.5,
                   "Started atorvastatin for cholesterol."),
        Medication("Atorvastatin", "40 mg", "1 tablet once daily at night", 10.5, 16.5,
                   "Atorvastatin increased from 20 mg to 40 mg as LDL is above target."),
        Medication("Rosuvastatin", "10 mg", "1 tablet once daily", 16.5, None,
                   "Atorvastatin stopped. Switched to rosuvastatin 10 mg after raised liver "
                   "enzymes and muscle aches."),
    ],
    notes=[
        ClinicNote(
            month=0.5,
            reason="Blood pressure and cholesterol check.",
            findings="Blood pressure 152/94 on three readings. Total cholesterol {CHOL@0}, "
                     "LDL cholesterol {LDL@0}. Liver tests normal (ALT {ALT@0}).",
            plan="Diagnosis of high blood pressure and high cholesterol. Start amlodipine 5 mg daily "
                 "and atorvastatin 20 mg at night. Diet and exercise advice given. "
                 "Repeat cholesterol and liver tests in 3 months.",
        ),
        ClinicNote(
            month=10.5,
            reason="Cholesterol review.",
            findings="LDL cholesterol {LDL@10}, improved but still above Grace's target of 2.5 mmol/L. "
                     "Blood pressure 128/80.",
            plan="Increase atorvastatin to 40 mg at night. Grace to report any muscle aches. "
                 "Repeat cholesterol, liver tests and CK in 3 months.",
        ),
        ClinicNote(
            month=16.5,
            reason="Aching thighs for about six weeks.",
            findings="ALT {ALT@16} and AST {AST@16}, both above range. Creatine kinase {CK@16}, above range. "
                     "LDL cholesterol {LDL@16}.",
            plan="Likely a side effect of the higher atorvastatin dose. Stop atorvastatin and start "
                 "rosuvastatin 10 mg daily. Repeat liver tests and CK in 3 months.",
        ),
        ClinicNote(
            month=19.3,
            reason="Follow-up after changing cholesterol medicine.",
            findings="Muscle aches have gone. ALT {ALT@19} and creatine kinase {CK@19}, both back in range. "
                     "LDL cholesterol {LDL@19}.",
            plan="Rosuvastatin is suiting Grace well. Continue current medicines. Review in 6 months.",
        ),
    ],
    events=[
        Event(3, "LDL", "response_to_treatment", "LDL fell from 4.6 to about 3.2 mmol/L after atorvastatin 20 mg was started."),
        Event(13, "ALT", "out_of_range", "ALT rose above range (about 58 U/L) after the atorvastatin dose increase."),
        Event(16, "ALT", "out_of_range", "ALT peaked at about 71 U/L; AST also above range."),
        Event(16, "CK", "out_of_range", "Creatine kinase above range (about 240 U/L)."),
        Event(19, "ALT", "response_to_treatment", "ALT back in range (about 33 U/L) after switching to rosuvastatin; LDL stayed controlled."),
    ],
)


# =============================================================================
# PATIENT 3: Daniel O'Connor - underactive thyroid (hypothyroidism)
# =============================================================================
#
# Story:
#   - Month 0: diagnosed, levothyroxine 50 microgram started.
#   - Dose stepped up to 75 (month 2) then 100 (month 4) until TSH is normal.
#   - Stable for a year, then at month 16 TSH jumps with no dose change.
#     Cause: he started a calcium supplement and takes it with his tablet.
#   - Advised to separate them; TSH back to normal by month 19.

p3_months = [0, 2, 4, 7, 10, 13, 16, 19, 21, 24]
p3_egfr = [(0, 96), (24, 95)]

P003 = Patient(
    patient_id="P003",
    name="Daniel O'Connor",
    sex="M",
    dob=date(1981, 2, 11),
    conditions=["hypothyroidism"],
    doctor="Dr Aisha Karim",
    start=date(2024, 2, 12),
    # Every visit: thyroid tests. Plus a baseline check at month 0 and a yearly check at 13.
    visits={
        month: THYROID
        + (["HB"] + LIPIDS if month in (0, 13) else [])
        + (KIDNEY + SALTS if month == 0 else [])
        for month in p3_months
    },
    lab_for_month={month: "bluegum" for month in p3_months},
    trajectories={
        # TSH goes UP when the thyroid is underactive; Free T4 goes DOWN. They mirror each other.
        "TSH": [(0, 9.8), (2, 6.4), (4, 4.6), (7, 2.4), (10, 1.9), (13, 2.1), (16, 7.6),
                (19, 3.0), (21, 2.2), (24, 1.8)],
        "FT4": [(0, 8.9), (2, 11.2), (4, 12.8), (7, 15.6), (10, 16.4), (13, 16.0), (16, 10.9),
                (19, 14.8), (21, 16.1), (24, 16.6)],
        "HB": [(0, 148), (13, 151)],
        "CHOL": [(0, 6.1), (13, 5.0)],   # cholesterol improves once the thyroid is treated
        "LDL": [(0, 4.0), (13, 3.0)],
        "HDL": [(0, 1.2), (13, 1.3)],
        "TRIG": [(0, 1.9), (13, 1.5)],
        "EGFR": p3_egfr,
        "CREAT": creatinine_from_egfr(p3_egfr, base_creat=84, base_egfr=96),
        "NA": [(0, 141), (24, 141)],
        "K": [(0, 4.1), (24, 4.1)],
    },
    medications=[
        Medication("Levothyroxine", "50 microgram", "1 tablet once daily on an empty stomach", 0.3, 2.3,
                   "Started levothyroxine for an underactive thyroid."),
        Medication("Levothyroxine", "75 microgram", "1 tablet once daily on an empty stomach", 2.3, 4.3,
                   "Levothyroxine increased from 50 to 75 microgram."),
        Medication("Levothyroxine", "100 microgram", "1 tablet once daily on an empty stomach", 4.3, None,
                   "Levothyroxine increased from 75 to 100 microgram."),
    ],
    reissues=[
        Reissue(16.3, "No dose change. Take on an empty stomach and at least 4 hours apart from "
                      "calcium or iron supplements. Repeat blood test in 3 months."),
    ],
    notes=[
        ClinicNote(
            month=0.3,
            reason="Tiredness, weight gain of about 4 kg and feeling cold for several months.",
            findings="TSH {TSH@0}, above range, and Free T4 {FT4@0}, below range. "
                     "Cholesterol {CHOL@0}, LDL cholesterol {LDL@0}.",
            plan="Diagnosis of an underactive thyroid (hypothyroidism). Start levothyroxine 50 microgram "
                 "each morning on an empty stomach. Repeat thyroid tests in 6 to 8 weeks.",
        ),
        ClinicNote(
            month=4.3,
            reason="Thyroid review.",
            findings="TSH {TSH@4}, still slightly above range, down from {TSH@0} at diagnosis. "
                     "Energy is improving.",
            plan="Increase levothyroxine to 100 microgram daily. Repeat thyroid tests in 3 months.",
        ),
        ClinicNote(
            month=16.3,
            reason="Unexpected thyroid result.",
            findings="TSH {TSH@16}, above range after a year of normal results. Free T4 {FT4@16}. "
                     "Daniel started a calcium supplement two months ago and takes it at breakfast "
                     "together with his levothyroxine.",
            plan="Calcium can reduce how much levothyroxine is absorbed. No dose change. Take "
                 "levothyroxine at least 4 hours apart from calcium. Repeat thyroid tests in 3 months.",
        ),
        ClinicNote(
            month=19.3,
            reason="Thyroid follow-up.",
            findings="TSH {TSH@19}, back in range after separating calcium and levothyroxine. Free T4 {FT4@19}.",
            plan="Continue levothyroxine 100 microgram daily. Thyroid tests every 6 to 12 months.",
        ),
    ],
    events=[
        Event(0, "TSH", "out_of_range", "TSH high (about 9.8 mIU/L) and Free T4 low before treatment."),
        Event(7, "TSH", "response_to_treatment", "TSH back in range (about 2.4) after dose increases to 100 microgram."),
        Event(16, "TSH", "sudden_change", "TSH jumped to about 7.6 after a year of stable results, after starting calcium."),
        Event(19, "TSH", "response_to_treatment", "TSH back in range (about 3.0) after separating calcium and levothyroxine."),
    ],
)


# The list the generator loops over. To add a patient, define it above and add it here.
PATIENTS: list[Patient] = [P001, P002, P003]