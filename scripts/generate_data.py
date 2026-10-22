"""
generate_data.py - creates the synthetic patients' PDFs and answer key.

Run it from the project's main folder:
    python scripts/generate_data.py

It writes everything into data/synthetic/. Running it again deletes and rebuilds
that folder, and gives exactly the same files every time (fixed seed).
"""

from medrag.config import DATA_DIR                 # the project's data/ folder
from medrag.synthetic.generate import generate     # the function that does the work

# Where to put the output, and the random seed that makes it repeatable
OUTPUT_DIR = DATA_DIR / "synthetic"
SEED = 42

counts = generate(OUTPUT_DIR, seed=SEED)

# Print a short summary, e.g. "documents           55"
print(f"Created synthetic data in {OUTPUT_DIR}")
for name, number in counts.items():
    print(f"  {name:<20}{number}")   # :<20 pads the name to 20 characters so numbers line up