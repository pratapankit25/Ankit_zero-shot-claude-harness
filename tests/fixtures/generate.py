"""Deterministic synthetic fixtures (seed 42) + pre-computed ground truths.

Entirely fictional data shaped like UP Police exports. Regenerate with:
    uv run python tests/fixtures/generate.py
Committed outputs: samples/*.csv + expected_answers.json — tests read these.
Fixture sizes intentionally exceed every sample/row cap in the app
(harness/patterns/test-driven.md → full-data gates).
"""
import csv
import json
import random
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
SAMPLES = HERE / "samples"

DISTRICTS = {
    "Lucknow": ["Hazratganj", "Gomti Nagar", "Alambagh"],
    "Kanpur Nagar": ["Kotwali Kanpur", "Kalyanpur", "Govind Nagar"],
    "Varanasi": ["Lanka", "Sigra", "Adampur"],
    "Prayagraj": ["Civil Lines Prayagraj", "Kareli", "Naini"],
    "Agra": ["Sadar Agra", "Tajganj", "Etmadpur"],
    "Meerut": ["Kotwali Meerut", "Civil Lines Meerut", "Partapur"],
    "Gorakhpur": ["Cantt Gorakhpur", "Gulriha", "Khorabar"],
    "Ghaziabad": ["Kavi Nagar", "Indirapuram", "Loni"],
}
# Lucknow weighted clearly highest so "top district" has one unambiguous answer.
DISTRICT_WEIGHTS = {
    "Lucknow": 26, "Kanpur Nagar": 18, "Varanasi": 12, "Prayagraj": 11,
    "Agra": 10, "Meerut": 9, "Gorakhpur": 7, "Ghaziabad": 7,
}
HINDI_DISTRICT = {
    "Lucknow": "लखनऊ", "Kanpur Nagar": "कानपुर नगर", "Varanasi": "वाराणसी",
    "Prayagraj": "प्रयागराज", "Agra": "आगरा", "Meerut": "मेरठ",
    "Gorakhpur": "गोरखपुर", "Ghaziabad": "गाज़ियाबाद",
}
CRIME_HEADS = [
    ("Theft", "379 BNS 303"), ("Vehicle Theft", "379A"), ("Burglary", "331 BNS"),
    ("Assault", "115 BNS"), ("Cheating & Fraud", "318 BNS"), ("Kidnapping", "137 BNS"),
    ("Rioting", "191 BNS"), ("Dowry Harassment", "85 BNS"),
]
STATUSES = ["Under Investigation", "Chargesheeted", "Closed"]
CALL_TYPES = ["Crime", "Accident", "Medical", "Fire", "Dispute"]

N_FIR = 3200
N_CALLS = 2400
START = date(2024, 1, 1)
END = date(2025, 6, 30)


def _rand_date(rng: random.Random) -> date:
    span = (END - START).days
    return START + timedelta(days=rng.randint(0, span))


def main() -> None:
    rng = random.Random(42)
    SAMPLES.mkdir(exist_ok=True)

    district_pool = [d for d, w in DISTRICT_WEIGHTS.items() for _ in range(w)]

    # ---- fir_records.csv ------------------------------------------------
    fir_rows = []
    for i in range(1, N_FIR + 1):
        district = rng.choice(district_pool)
        ps = rng.choice(DISTRICTS[district])
        head, section = CRIME_HEADS[rng.randrange(len(CRIME_HEADS))]
        d = _rand_date(rng)
        fir_rows.append({
            "fir_no": f"FIR/{d.year}/{i:06d}",
            "district": district,
            "police_station": ps,
            "crime_head": head,
            "sections": section,
            "fir_date": d.isoformat(),
            "status": rng.choices(STATUSES, weights=[55, 30, 15])[0],
            "complainant_gender": rng.choices(["M", "F"], weights=[63, 37])[0],
        })
    with open(SAMPLES / "fir_records.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(fir_rows[0].keys()))
        w.writeheader()
        w.writerows(fir_rows)

    # ---- dial112_calls.csv ---------------------------------------------
    call_rows = []
    for i in range(1, N_CALLS + 1):
        district = rng.choice(district_pool)
        d = _rand_date(rng)
        base = {"Lucknow": 9, "Ghaziabad": 16}.get(district, 12)
        call_rows.append({
            "call_id": f"C112-{i:06d}",
            "district": district,
            "call_type": rng.choice(CALL_TYPES),
            "call_date": d.isoformat(),
            "response_minutes": max(3, int(rng.gauss(base, 3))),
        })
    with open(SAMPLES / "dial112_calls.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(call_rows[0].keys()))
        w.writeheader()
        w.writerows(call_rows)

    # ---- personnel.csv --------------------------------------------------
    personnel_rows = []
    for district, stations in DISTRICTS.items():
        for ps in stations:
            sanctioned = rng.randint(60, 140)
            actual = int(sanctioned * rng.uniform(0.62, 0.95))
            # Lucknow understaffed on purpose → highest FIRs-per-officer, unambiguous
            if district == "Lucknow":
                actual = int(sanctioned * 0.55)
            personnel_rows.append({
                "district": district,
                "police_station": ps,
                "sanctioned_strength": sanctioned,
                "actual_strength": actual,
            })
    with open(SAMPLES / "personnel.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(personnel_rows[0].keys()))
        w.writeheader()
        w.writerows(personnel_rows)

    # ---- ground truths --------------------------------------------------
    by_district_2025 = defaultdict(int)
    lucknow_2025_by_month = defaultdict(int)
    for r in fir_rows:
        if r["fir_date"].startswith("2025"):
            by_district_2025[r["district"]] += 1
            if r["district"] == "Lucknow":
                lucknow_2025_by_month[r["fir_date"][:7]] += 1
    top_district_2025 = max(by_district_2025, key=by_district_2025.get)

    actual_by_district = defaultdict(int)
    for r in personnel_rows:
        actual_by_district[r["district"]] += r["actual_strength"]
    fir_per_officer_2025 = {
        d: by_district_2025[d] / actual_by_district[d] for d in DISTRICTS
    }
    top_fir_per_officer = max(fir_per_officer_2025, key=fir_per_officer_2025.get)
    min_fir_per_officer = min(fir_per_officer_2025, key=fir_per_officer_2025.get)

    expected = {
        "total_fir_rows": N_FIR,
        "total_call_rows": N_CALLS,
        "total_personnel_rows": len(personnel_rows),
        "fir_2025_by_district": dict(sorted(by_district_2025.items())),
        "top_district_2025": top_district_2025,
        "top_district_2025_count": by_district_2025[top_district_2025],
        "top_district_2025_hindi": HINDI_DISTRICT[top_district_2025],
        "lucknow_2025_by_month": dict(sorted(lucknow_2025_by_month.items())),
        "top_fir_per_officer_district": top_fir_per_officer,
        "min_fir_per_officer_district": min_fir_per_officer,
        "fir_per_officer_2025": {d: round(v, 4) for d, v in sorted(fir_per_officer_2025.items())},
        "district_aliases": HINDI_DISTRICT,
    }
    (HERE / "expected_answers.json").write_text(
        json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"fixtures written: {N_FIR} FIRs, {N_CALLS} calls, {len(personnel_rows)} personnel")
    print(f"top district 2025: {top_district_2025} ({by_district_2025[top_district_2025]})")
    print(f"top FIRs/officer 2025: {top_fir_per_officer}")


if __name__ == "__main__":
    main()
