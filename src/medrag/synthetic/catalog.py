"""
catalog.py - the medical reference data used to build the synthetic patients.

Think of this file as a small medical dictionary. It doesn't create any PDFs itself;
the other files look things up here. It has four parts:

1. TESTS             Every blood/urine test we use: its name, unit and normal range.
2. PLAUSIBLE_LIMITS  Values no living person could have. Used by tests to catch bugs.
3. CONDITIONS        Which tests and medicines belong to each medical condition.
                     This keeps patients realistic (e.g. no anaemia medicine for
                     someone who only has diabetes).
4. LABS              Two fictional pathology labs that print the SAME tests in
                     DIFFERENT ways (different names, layouts and units), like real
                     labs do. This makes the AI's job realistic later on.
"""

# `dataclass` lets us write small classes that just hold data, without writing
# an __init__ method by hand. Python creates it for us from the listed fields.
from dataclasses import dataclass


# =============================================================================
# 1. LAB TESTS
# =============================================================================

@dataclass(frozen=True)  # frozen=True: values can't be changed after creation (prevents accidents)
class AnalyteDef:
    """
    The definition of one lab test (an "analyte" is the thing being measured).

    Fields:
        code:            Short unique ID used everywhere in the code, e.g. "HBA1C".
        name:            Human-readable name printed on reports, e.g. "HbA1c".
        panel:           Group heading the test appears under, e.g. "Diabetes".
        unit:            Unit of measurement, e.g. "mmol/L".
        decimals:        How many decimal places the lab prints (0 = whole number).
        ref_low:         Bottom of the normal range. None means "no lower limit".
        ref_high:        Top of the normal range. None means "no upper limit".
        ref_low_female:  Different bottom limit for women, if the test has one.
        ref_high_female: Different top limit for women, if the test has one.

    Example:
        AnalyteDef("K", "Potassium", "Electrolytes", "mmol/L", 1, 3.5, 5.2)
        means potassium is printed like "4.6 mmol/L" and is normal between 3.5 and 5.2.
    """
    code: str
    name: str
    panel: str
    unit: str
    decimals: int
    ref_low: float | None
    ref_high: float | None
    ref_low_female: float | None = None    # "= None" makes these two optional
    ref_high_female: float | None = None

    def ref_range(self, sex: str) -> tuple[float | None, float | None]:
        """
        Return the normal range for a person of the given sex.

        Args:
            sex: "M" or "F".

        Returns:
            A pair (low, high). Either can be None if that side has no limit.

        Example:
            TESTS["CREAT"].ref_range("F")  ->  (45, 90)
            TESTS["CREAT"].ref_range("M")  ->  (60, 110)
        """
        if sex == "F":
            # Use the female-specific limit if there is one, otherwise the normal one
            low = self.ref_low_female if self.ref_low_female is not None else self.ref_low
            high = self.ref_high_female if self.ref_high_female is not None else self.ref_high
            return low, high
        return self.ref_low, self.ref_high


# All tests, stored in a dictionary so we can look one up by its code:
#     TESTS["HBA1C"]  ->  the AnalyteDef for HbA1c
#
# The order of this list also sets the order tests appear on a printed report.
#
#            code     name                              panel               unit             dp  low   high  low(F) high(F)
TESTS: dict[str, AnalyteDef] = {t.code: t for t in [
    AnalyteDef("HBA1C", "HbA1c",                          "Diabetes",         "%",             1, 4.0,  6.0),
    AnalyteDef("GLU_F", "Fasting Glucose",                "Diabetes",         "mmol/L",        1, 3.0,  5.4),
    AnalyteDef("CREAT", "Creatinine",                     "Kidney Function",  "µmol/L",        0, 60,   110,  45,    90),
    AnalyteDef("EGFR",  "eGFR",                           "Kidney Function",  "mL/min/1.73m²", 0, 60,   None),
    AnalyteDef("UACR",  "Urine Albumin/Creatinine Ratio", "Kidney Function",  "mg/mmol",       1, None, 2.5,  None,  3.5),
    AnalyteDef("NA",    "Sodium",                         "Electrolytes",     "mmol/L",        0, 135,  145),
    AnalyteDef("K",     "Potassium",                      "Electrolytes",     "mmol/L",        1, 3.5,  5.2),
    AnalyteDef("CHOL",  "Total Cholesterol",              "Lipids",           "mmol/L",        1, None, 5.5),
    AnalyteDef("LDL",   "LDL Cholesterol",                "Lipids",           "mmol/L",        1, None, 3.0),
    AnalyteDef("HDL",   "HDL Cholesterol",                "Lipids",           "mmol/L",        1, 1.0,  None),
    AnalyteDef("TRIG",  "Triglycerides",                  "Lipids",           "mmol/L",        1, None, 2.0),
    AnalyteDef("ALT",   "ALT",                            "Liver Function",   "U/L",           0, 5,    40),
    AnalyteDef("AST",   "AST",                            "Liver Function",   "U/L",           0, 5,    35),
    AnalyteDef("CK",    "Creatine Kinase",                "Muscle",           "U/L",           0, 30,   200),
    AnalyteDef("TSH",   "TSH",                            "Thyroid Function", "mIU/L",         2, 0.4,  4.0),
    AnalyteDef("FT4",   "Free T4",                        "Thyroid Function", "pmol/L",        1, 10.0, 20.0),
    AnalyteDef("HB",    "Haemoglobin",                    "Full Blood Count", "g/L",           0, 130,  180,  115,   165),
]}


# =============================================================================
# 2. PLAUSIBLE LIMITS
# =============================================================================

# The widest values that could ever appear in a living person, as (min, max).
# These are NOT normal ranges. A result outside the normal range is a real,
# interesting finding; a result outside THESE limits means our code has a bug.
# The tests check every generated value against this table.
PLAUSIBLE_LIMITS: dict[str, tuple[float, float]] = {
    "HBA1C": (3.0, 20.0),
    "GLU_F": (1.0, 40.0),
    "CREAT": (20, 1500),
    "EGFR":  (5, 150),
    "UACR":  (0.0, 300.0),
    "NA":    (110, 170),
    "K":     (2.0, 8.0),
    "CHOL":  (1.0, 15.0),
    "LDL":   (0.2, 12.0),
    "HDL":   (0.2, 4.0),
    "TRIG":  (0.2, 20.0),
    "ALT":   (2, 2000),
    "AST":   (2, 2000),
    "CK":    (10, 20000),
    "TSH":   (0.01, 100.0),
    "FT4":   (2.0, 80.0),
    "HB":    (50, 220),
}


# =============================================================================
# 3. CONDITIONS
# =============================================================================

@dataclass(frozen=True)
class ConditionDef:
    """
    What normally goes with one medical condition.

    Fields:
        label:     Readable name, e.g. "Type 2 diabetes".
        tests:     Test codes doctors usually check for this condition.
        medicines: Medicine names commonly prescribed for this condition.

    A patient may only have tests and medicines that belong to one of their
    conditions (or to ROUTINE_TESTS). The tests enforce this rule automatically.

    `frozenset` is a set that can't be changed. A set is used because we only
    ever ask "is X in here?", which sets answer very quickly.
    """
    label: str
    tests: frozenset[str]
    medicines: frozenset[str]


# General blood tests any adult might have at a check-up, whatever their condition.
ROUTINE_TESTS = frozenset({"HB", "NA", "K", "CREAT", "EGFR", "GLU_F"})

# Look a condition up by its key:  CONDITIONS["hypothyroidism"].medicines  ->  {"Levothyroxine"}
CONDITIONS: dict[str, ConditionDef] = {
    "type2_diabetes": ConditionDef(
        label="Type 2 diabetes",
        # Blood sugar, plus kidneys and cholesterol, which diabetes can affect
        tests=frozenset({"HBA1C", "GLU_F", "CREAT", "EGFR", "UACR", "CHOL", "LDL", "HDL", "TRIG"}),
        # Statins are included because diabetes raises heart risk
        medicines=frozenset({"Metformin", "Empagliflozin", "Atorvastatin", "Rosuvastatin"}),
    ),
    "ckd": ConditionDef(
        label="Chronic kidney disease (early stage)",
        tests=frozenset({"CREAT", "EGFR", "UACR", "NA", "K", "HB"}),
        medicines=frozenset({"Perindopril", "Empagliflozin"}),
    ),
    "hypertension": ConditionDef(
        label="Hypertension",
        tests=frozenset({"CREAT", "EGFR", "NA", "K", "GLU_F", "CHOL", "LDL", "HDL", "TRIG"}),
        medicines=frozenset({"Amlodipine", "Perindopril"}),
    ),
    "high_cholesterol": ConditionDef(
        label="High cholesterol",
        # Liver tests (ALT, AST) and CK are checked because statins can affect liver and muscles
        tests=frozenset({"CHOL", "LDL", "HDL", "TRIG", "ALT", "AST", "CK"}),
        medicines=frozenset({"Atorvastatin", "Rosuvastatin"}),
    ),
    "hypothyroidism": ConditionDef(
        label="Hypothyroidism",
        # An underactive thyroid can raise cholesterol, so lipids are checked too
        tests=frozenset({"TSH", "FT4", "CHOL", "LDL", "HDL", "TRIG"}),
        medicines=frozenset({"Levothyroxine"}),
    ),
}


# =============================================================================
# 4. LABS
# =============================================================================

@dataclass(frozen=True)
class LabDef:
    """
    A fictional pathology lab and the way it prints reports.

    Fields:
        key:        Short ID used in file names, e.g. "kestrel".
        name:       Full name printed at the top of the report.
        address:    Fictional address printed under the name.
        layout:     "A" (one table per panel) or "B" (one big table plus comments).
        aliases:    Tests this lab names differently, as {test code: printed name}.
                    Tests not listed here use the standard name from TESTS.
        hba1c_unit: "%" or "mmol/mol". Australian labs use either.
    """
    key: str
    name: str
    address: str
    layout: str
    aliases: dict[str, str]
    hba1c_unit: str


LABS: dict[str, LabDef] = {
    "kestrel": LabDef(
        key="kestrel",
        name="Kestrel Pathology",
        address="Level 2, 18 Fictional Lane, Melbourne VIC 3000",
        layout="A",
        aliases={},             # uses all the standard names
        hba1c_unit="%",
    ),
    "bluegum": LabDef(
        key="bluegum",
        name="Bluegum Diagnostics",
        address="7 Example Street, Clayton VIC 3168",
        layout="B",
        aliases={               # same tests, different names on the page
            "GLU_F": "Glucose (fasting)",
            "EGFR": "Estimated GFR",
            "UACR": "Urine ACR",
            "LDL": "LDL-C",
            "HDL": "HDL-C",
            "CHOL": "Cholesterol, total",
            "FT4": "Free Thyroxine (FT4)",
            "HB": "Hb",
        },
        hba1c_unit="mmol/mol",  # the AI will have to convert this back to %
    ),
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def hba1c_pct_to_mmol_mol(pct: float) -> float:
    """
    Convert an HbA1c result from % to mmol/mol.

    Uses the standard formula printed on Australian reports:
        mmol/mol = (% - 2.15) x 10.929

    Args:
        pct: HbA1c as a percentage, e.g. 7.0

    Returns:
        The same result in mmol/mol, e.g. 53.0 (not rounded).
    """
    return (pct - 2.15) * 10.929


def printed_test(lab: LabDef, test: AnalyteDef, sex: str, value: float):
    """
    Work out exactly how a particular lab would print one test result.

    The same result looks different depending on the lab. For example, HbA1c 7.0%
    is printed by Kestrel as "HbA1c 7.0 %" but by Bluegum as "HbA1c 53 mmol/mol".

    Args:
        lab:   The lab printing the report (from LABS).
        test:  The test being printed (from TESTS).
        sex:   "M" or "F", because some normal ranges differ by sex.
        value: The result in the standard unit from TESTS (e.g. HbA1c in %).

    Returns:
        A tuple of 6 items:
            name      - the name this lab prints, e.g. "LDL-C"
            value     - the value rounded the way this lab prints it
            unit      - the unit this lab prints
            decimals  - how many decimal places to show
            ref_low   - bottom of the normal range (or None)
            ref_high  - top of the normal range (or None)
    """
    # Use the lab's own name for the test if it has one, otherwise the standard name
    name = lab.aliases.get(test.code, test.name)
    low, high = test.ref_range(sex)

    # Special case: this lab reports HbA1c in mmol/mol, so convert value AND range.
    # The range 20-42 mmol/mol is the same as 4.0-6.0 %.
    if test.code == "HBA1C" and lab.hba1c_unit == "mmol/mol":
        return name, round(hba1c_pct_to_mmol_mol(value)), "mmol/mol", 0, 20, 42

    # Normal case: round to the test's usual decimal places
    rounded = round(value, test.decimals) if test.decimals else round(value)
    return name, rounded, test.unit, test.decimals, low, high