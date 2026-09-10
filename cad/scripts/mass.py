"""Volare mass budget and the closure plan for the 250 kg cockpit cap.

Mass basis confirmed 2026-09-04: the cap covers the entire cockpit INCLUDING the
pilot and EXCLUDING the supplied hulls and beams (65 kg).

Note 06 section 8's "+32 over cap" / "+102 over cap" are wrong: its 282 kg
subtotal includes 80 kg of demihulls, so it compares a hull-inclusive figure
against a cap that excludes hulls. The cockpit items alone are 202 kg, and with
a 70 kg pilot that is 272 kg - 22 kg over, not 102.

That difference decides the project. 102 kg is not closable by trimming; 22 kg is.

    python scripts/mass.py
    python scripts/mass.py --pilot 60
"""
import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import volare as V

OUT = Path(__file__).resolve().parents[2] / "cad" / "out"

# --- note 06 section 8, item by item -----------------------------------------
# in_cap: does ENERGY_REQ_48 count it? The supplied hulls and beams do not.
BUDGET = [
    # name,                          kg,   group,        in_cap
    ("Demihulls x2 (supplied)",      80.0, "supplied",   False),
    ("Cockpit shell",                27.0, "structure",  True),
    ("Support frame",                26.0, "structure",  True),
    ("Beam + rail fairings",          6.0, "structure",  True),
    ("Hull clamps x4 + hardware",     5.0, "structure",  True),
    ("Seat frame",                    5.0, "structure",  True),
    ("Competr outboard",             25.0, "powertrain", True),
    ("Competr trim assembly",        10.0, "powertrain", True),
    ("Competr control unit",          3.0, "powertrain", True),
    ("Inverter 42 kW class",         10.0, "powertrain", True),
    ("Trim + steering pumps",         8.0, "systems",    True),
    ("Cooling + bilge pumps",         4.0, "systems",    True),
    ("Custom pack, 8 kWh",           52.0, "energy",     True),
    ("DC/DC 96 -> 12 V",              3.0, "systems",    True),
    ("HV/LV harness, contactors",     8.0, "systems",    True),
    ("Solar 4 m2 + MPPT",            10.0, "energy",     True),
]

# --- levers -------------------------------------------------------------------
# cost 0-10: disruption, risk and money combined. Documented, not derived - the
# ranking is a judgement call and is meant to be argued with.
LEVERS = [
    {"id": "solar", "kg": 10.0, "cost": 1,
     "what": "drop the 4 m2 solar array + MPPT",
     "note": "note 06 s7 argues it may cost nothing in race energy. Cheapest kg "
             "on the boat. Check it does not cost Design Jury points (REQ_170)."},
    {"id": "pack6", "kg": 13.0, "cost": 4,
     "what": "pack 8 kWh -> 6 kWh",
     "note": "note 06: costs about 11 min of endurance at 30 km/h. Only viable "
             "once the endurance duration is known - still an open question."},
    {"id": "schedB", "kg": 3.0, "cost": 2,
     "what": "cockpit laminate Schedule B instead of A",
     "note": "note 06. Reduces margin; check against note 03's allowables."},
    {"id": "carbonrail", "kg": 9.0, "cost": 5,
     "what": "carbon rails instead of aluminium",
     "note": "note 06: costs money and needs galvanic isolation from the clamps."},
    {"id": "shellspan", "kg": 12.0, "cost": 6,
     "what": "let the pod shell carry the span; rails become mounting strips",
     "note": "note 08 s3. The shell is 10.4x stiffer than the rail pair needs to "
             "be, and 73% of that survives the cockpit opening. Requires "
             "continuous shear transfer - bolts at 150 mm pitch through moulded "
             "inserts, NOT clearance holes. Must be FE-validated before it is "
             "counted; this is the largest single lever and the least proven."},
    {"id": "sizing", "kg": 4.5, "cost": 3,
     "what": "note 05 stage 3 sizing optimisation on the shell",
     "note": "note 05 predicts 15-20% off the 28.9 kg uniform schedule, i.e. "
             "24-25 kg. Against note 06's 27 kg allowance that is ~2-4 kg. Taken "
             "here as 4.5 kg at the optimistic end; do not bank both this and "
             "schedB, they overlap."},
    {"id": "inverter", "kg": 10.0, "cost": 7,
     "what": "drop the separate 42 kW inverter",
     "note": "note 06 flags it as 'confirm if included' with the Competr package. "
             "If it is integrated this is free; if not, removing it changes the "
             "powertrain. Resolve the question before counting the kg."},
]
# Levers that overlap and must not both be counted at full value.
CONFLICTS = [("schedB", "sizing")]

DRAG_WORK_EXTRA_KG = 3.7   # windscreen/shoulder fairing + bracket blending,
                           # from optimise.py; note 06 budgets no line for these

# A wet hand layup lands within maybe +/-5% of its calculated mass, and the
# cockpit shell alone is 27 kg. Landing 0.3 kg under a hard cap is not a plan, it
# is a coin toss at scrutineering. Require real margin.
MIN_MARGIN_KG = 5.0


def totals(pilot_kg=None, extra_kg=0.0, applied=()):
    pilot_kg = V.PILOT_DESIGN_KG if pilot_kg is None else pilot_kg
    supplied_note06 = sum(m for _, m, _, c in BUDGET if not c)
    cockpit = sum(m for _, m, _, c in BUDGET if c) + extra_kg
    saved = sum(l["kg"] for l in LEVERS if l["id"] in applied)
    cockpit -= saved
    return {
        "cockpit_kg": cockpit,
        "pilot_kg": pilot_kg,
        "in_cap_kg": cockpit + pilot_kg,
        "cap_kg": V.MASS_CAP_KG,
        "margin_kg": V.MASS_CAP_KG - (cockpit + pilot_kg),
        "supplied_actual_kg": V.HULLS_BEAMS_KG,
        "supplied_note06_kg": supplied_note06,
        "displacement_kg": cockpit + pilot_kg + V.HULLS_BEAMS_KG,
        "saved_kg": saved,
        "applied": list(applied),
    }


def closure_plans(pilot_kg=None, extra_kg=0.0, target=None):
    """Every lever subset that reaches the cap, cheapest first."""
    target = V.MASS_CAP_KG if target is None else target
    ids = [l["id"] for l in LEVERS]
    cost = {l["id"]: l["cost"] for l in LEVERS}
    plans = []
    for r in range(1, len(ids) + 1):
        for combo in itertools.combinations(ids, r):
            if any(a in combo and b in combo for a, b in CONFLICTS):
                continue
            t = totals(pilot_kg, extra_kg, combo)
            if t["in_cap_kg"] <= target:
                plans.append({"levers": combo, "cost": sum(cost[i] for i in combo),
                              **t})
    plans.sort(key=lambda p: (p["cost"], -p["margin_kg"]))
    # keep only non-dominated plans: no cheaper plan already covers this set
    keep, seen = [], []
    for p in plans:
        if any(set(q["levers"]) <= set(p["levers"]) for q in seen):
            continue
        seen.append(p)
        keep.append(p)
    return keep


def main():
    argv = sys.argv[1:]
    pilot = float(argv[argv.index("--pilot") + 1]) if "--pilot" in argv else V.PILOT_DESIGN_KG

    print("=" * 70)
    print("VOLARE MASS BUDGET vs the 250 kg cockpit cap (ENERGY_REQ_48)")
    print("=" * 70)
    print(f"  cap covers the entire cockpit INCLUDING the {pilot:.0f} kg pilot")
    print(f"  cap EXCLUDES the supplied hulls + beams ({V.HULLS_BEAMS_KG:.0f} kg)")

    print("\nNOTE 06 SECTION 8, split by whether the cap counts it")
    print(f"  {'item':<30}{'kg':>7}  {'group':<11}{'in cap':>7}")
    print("  " + "-" * 58)
    for n, m, g, c in BUDGET:
        print(f"  {n:<30}{m:>7.1f}  {g:<11}{'yes' if c else 'NO':>7}")
    print("  " + "-" * 58)
    base = totals(pilot)
    print(f"  {'note 06 table total':<30}{sum(m for _, m, _, _ in BUDGET):>7.1f}")
    print(f"  {'  of which supplied hulls':<30}{base['supplied_note06_kg']:>7.1f}"
          f"   (outside the cap)")
    print(f"  {'  COCKPIT ITEMS':<30}{base['cockpit_kg']:>7.1f}")

    print("\nAGAINST THE CAP")
    print(f"  cockpit                 {base['cockpit_kg']:7.1f} kg")
    print(f"  + pilot                 {pilot:7.1f} kg")
    print(f"  {'-' * 34}")
    print(f"  in-cap total            {base['in_cap_kg']:7.1f} kg")
    print(f"  cap                     {V.MASS_CAP_KG:7.1f} kg")
    print(f"  OVER BY                 {-base['margin_kg']:7.1f} kg")
    print(f"\n  note 06 says '+102 over cap'. That compares its hull-INCLUSIVE")
    print(f"  282 kg subtotal against a cap that excludes hulls. The real gap")
    print(f"  is {-base['margin_kg']:.0f} kg - which the levers below can close.")

    # the drag work is not free
    withdrag = totals(pilot, DRAG_WORK_EXTRA_KG)
    print(f"\nCOST OF THE AERO WORK")
    print(f"  optimise.py adds a windscreen/shoulder fairing and bracket blending")
    print(f"  that note 06 has no line for: +{DRAG_WORK_EXTRA_KG:.1f} kg.")
    print(f"  Those two items are worth 19 N of drag, so they pay for themselves")
    print(f"  on resistance - but they widen the mass gap to "
          f"{-withdrag['margin_kg']:.1f} kg.")

    print("\nLEVERS")
    print(f"  {'id':<12}{'kg':>6}{'cost':>6}   what")
    print("  " + "-" * 66)
    for l in sorted(LEVERS, key=lambda x: x["cost"] / x["kg"]):
        print(f"  {l['id']:<12}{l['kg']:>6.1f}{l['cost']:>6}   {l['what']}")
    print(f"  {'-' * 66}")
    print(f"  {'TOTAL':<12}{sum(l['kg'] for l in LEVERS):>6.1f}"
          f"       (minus overlaps: schedB and sizing overlap)")

    print("\nCLOSURE PLANS (including the aero work), cheapest disruption first")
    plans = closure_plans(pilot, DRAG_WORK_EXTRA_KG)
    if not plans:
        print("  NONE REACH THE CAP - the powertrain has to change.")
    else:
        print(f"  {'cost':>5}{'saved':>8}{'in-cap':>9}{'margin':>9}   levers")
        print("  " + "-" * 66)
        for p in plans[:8]:
            print(f"  {p['cost']:>5}{p['saved_kg']:>8.1f}{p['in_cap_kg']:>9.1f}"
                  f"{p['margin_kg']:>9.1f}   {' + '.join(p['levers'])}")
        safe = [p for p in plans if p["margin_kg"] >= MIN_MARGIN_KG]
        b = safe[0] if safe else plans[0]
        if plans[0]["margin_kg"] < MIN_MARGIN_KG:
            print(f"\n  The cheapest plan lands only {plans[0]['margin_kg']:.1f} kg "
                  f"under the cap. A wet layup varies by more than")
            print(f"  that, so it is not a plan. Requiring at least "
                  f"{MIN_MARGIN_KG:.0f} kg of margin instead:")
        print(f"\n  RECOMMENDED: {' + '.join(b['levers'])}")
        for lid in b["levers"]:
            l = next(x for x in LEVERS if x["id"] == lid)
            print(f"    - {l['what']} ({l['kg']:.0f} kg)")
            print(f"      {l['note']}")
        print(f"\n  lands at {b['in_cap_kg']:.1f} kg, {b['margin_kg']:.1f} kg under the cap,")
        print(f"  all-up displacement {b['displacement_kg']:.1f} kg.")

    print("\nPILOT SENSITIVITY (the cap includes the pilot, so this matters)")
    print(f"  {'pilot kg':>9}{'in-cap':>9}{'margin':>9}   closure")
    for pk in (60, 65, 70, 75, 80, 90):
        t = totals(pk, DRAG_WORK_EXTRA_KG)
        pl = closure_plans(pk, DRAG_WORK_EXTRA_KG)
        sf = [q for q in pl if q["margin_kg"] >= MIN_MARGIN_KG]
        tag = " + ".join((sf or pl)[0]["levers"]) if pl else "NOT ACHIEVABLE"
        if pl and not sf:
            tag += "  (no >=5 kg margin option)"
        print(f"  {pk:>9.0f}{t['in_cap_kg']:>9.1f}{t['margin_kg']:>9.1f}   {tag}")

    print("\nWHAT THIS DOES NOT FIX")
    print("  ENERGY_REQ_188 caps the motor at 25 kW nominal; the Competr outboard")
    print("  is 26.9 kW. That is a compliance failure independent of mass, and if")
    print("  it forces a different outboard the 25 + 10 + 3 kg powertrain block")
    print("  and the 10 kg inverter question all reopen. Settle it first - it can")
    print("  invalidate every plan above.")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "mass.json").write_text(json.dumps(
        {"basis": {"cap_kg": V.MASS_CAP_KG, "pilot_kg": pilot,
                   "supplied_kg": V.HULLS_BEAMS_KG},
         "budget": [{"item": n, "kg": m, "group": g, "in_cap": c} for n, m, g, c in BUDGET],
         "baseline": base, "with_aero_work": withdrag,
         "levers": LEVERS,
         "plans": [{**p, "levers": list(p["levers"])} for p in plans[:12]]},
        indent=2, default=float))
    print(f"\nwrote {OUT / 'mass.json'}")


if __name__ == "__main__":
    main()
