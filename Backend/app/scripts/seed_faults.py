"""
Seeds the faults collection with a real, structured starting set —
replacing "nothing exists yet" with actual documents Module 1 and Module 3
can eventually reference.

Run locally with:
    python -m app.scripts.seed_faults

Safe to re-run: create_fault in the faults router already rejects exact
duplicates (same appliance_type + name), so running this twice won't
double up entries — it'll just print 409s for ones that already exist,
which this script catches and reports as "skipped", not a failure.

COST RANGES — IMPORTANT CAVEAT:
There is no public dataset for Indian appliance repair costs (flagged in
the original project plan). These typical_cost_min/max values are
reasonable estimates based on general appliance-repair pricing patterns,
NOT sourced from a verified dataset of real transactions. They exist so
the app has something non-empty to show — they should be treated as
placeholder until Module 5/6 (technician bookings) start feeding in real
transaction data, which was always the intended long-term source of truth
for this field.
"""

import asyncio

from app.database import close_mongo_connection, connect_to_mongo, get_db
from app.models.fault import FaultCreate, new_fault_document

FAULTS: list[FaultCreate] = [
    # ───────────────────────── FRIDGE ─────────────────────────
    FaultCreate(
        appliance_type="fridge",
        name="Compressor Strain",
        description=(
            "Early-stage compressor strain, often caused by a failing start relay or low "
            "refrigerant pressure forcing the compressor to work harder than it should. "
            "Usually presents as a louder-than-normal running sound and longer cooling cycles."
        ),
        severity="high",
        typical_symptoms=[
            "loud clicking or clunking near the compressor",
            "compressor runs constantly without cycling off",
            "fridge feels warm to the touch on the back/side panel",
            "noticeably higher electricity bill",
        ],
        typical_cost_min=2800, typical_cost_max=4500,
    ),
    FaultCreate(
        appliance_type="fridge",
        name="Start Relay Failure",
        description=(
            "The start relay (a small component that gives the compressor its initial "
            "power kick) has failed or is intermittently failing, often preventing the "
            "compressor from starting at all."
        ),
        severity="medium",
        typical_symptoms=[
            "fridge makes a clicking sound every few minutes but doesn't start cooling",
            "compressor hums but doesn't start",
            "fridge stopped cooling suddenly",
        ],
        typical_cost_min=400, typical_cost_max=900,
    ),
    FaultCreate(
        appliance_type="fridge",
        name="Condenser Coil Blockage",
        description=(
            "Dust or lint buildup on the condenser coils (usually at the back or "
            "underneath the unit) is restricting heat dissipation, making the fridge "
            "work harder and cool less efficiently."
        ),
        severity="low",
        typical_symptoms=[
            "fridge running hotter on the outside than usual",
            "food not staying as cold as it used to",
            "visible dust buildup at the back of the unit",
        ],
        typical_cost_min=300, typical_cost_max=700,
    ),
    FaultCreate(
        appliance_type="fridge",
        name="Thermostat Fault",
        description=(
            "The thermostat is misreading internal temperature or failing to signal the "
            "compressor correctly, leading to inconsistent cooling — sometimes too cold, "
            "sometimes not cold enough."
        ),
        severity="medium",
        typical_symptoms=[
            "inconsistent temperature inside the fridge",
            "food freezing in the fridge compartment (not the freezer)",
            "compressor won't turn off even when set to a low cooling level",
        ],
        typical_cost_min=500, typical_cost_max=1200,
    ),

    # ───────────────────────── AC ─────────────────────────
    FaultCreate(
        appliance_type="ac",
        name="Fan Blade Imbalance",
        description=(
            "An imbalanced or bent fan blade in the indoor or outdoor unit, often from "
            "dust buildup or a loose mount, causing a rhythmic vibration or knocking sound."
        ),
        severity="medium",
        typical_symptoms=[
            "rhythmic knocking or thumping sound when running",
            "unit vibrates noticeably more than usual",
            "noise changes with fan speed setting",
        ],
        typical_cost_min=1200, typical_cost_max=2200,
    ),
    FaultCreate(
        appliance_type="ac",
        name="Loose Mounting Bracket",
        description=(
            "The indoor or outdoor unit's mounting bracket has loosened over time, "
            "causing the whole unit to vibrate against the wall or frame during operation."
        ),
        severity="low",
        typical_symptoms=[
            "rattling sound that seems to come from the wall or frame, not the unit itself",
            "unit appears to shift slightly when running",
        ],
        typical_cost_min=400, typical_cost_max=900,
    ),
    FaultCreate(
        appliance_type="ac",
        name="Bearing Wear",
        description=(
            "Worn fan motor bearings causing friction and a high-pitched whining or "
            "grinding sound, typically worsening over time as wear increases."
        ),
        severity="medium",
        typical_symptoms=[
            "high-pitched whining or grinding sound",
            "sound gets worse the longer the unit runs",
            "fan feels like it's struggling to spin up",
        ],
        typical_cost_min=900, typical_cost_max=1800,
    ),
    FaultCreate(
        appliance_type="ac",
        name="Capacitor Fault",
        description=(
            "A failing start or run capacitor preventing the compressor or fan motor "
            "from starting reliably — often shows up as the unit trying and failing to "
            "turn on, or shutting off shortly after starting."
        ),
        severity="high",
        typical_symptoms=[
            "AC hums but doesn't start",
            "AC turns off by itself a few minutes after starting",
            "outdoor unit fan doesn't spin even when the indoor unit is on",
        ],
        typical_cost_min=600, typical_cost_max=1400,
    ),

    # ───────────────────────── WASHER ─────────────────────────
    FaultCreate(
        appliance_type="washer",
        name="Drum Bearing Wear",
        description=(
            "Worn drum bearings causing a grinding noise during spin cycles, usually "
            "after years of heavy or unbalanced loads. Tends to get progressively worse."
        ),
        severity="high",
        typical_symptoms=[
            "loud grinding noise specifically during the spin cycle",
            "noise has gotten progressively worse over weeks/months",
            "drum feels loose when rotated by hand while empty",
        ],
        typical_cost_min=3500, typical_cost_max=6000,
    ),
    FaultCreate(
        appliance_type="washer",
        name="Worn Drive Belt",
        description=(
            "The belt connecting the motor to the drum has worn, stretched, or slipped, "
            "causing the drum to spin slower than expected or not at all."
        ),
        severity="medium",
        typical_symptoms=[
            "drum doesn't spin or spins very slowly during wash/spin cycle",
            "burning rubber smell during operation",
            "motor runs but drum doesn't move",
        ],
        typical_cost_min=800, typical_cost_max=1800,
    ),
    FaultCreate(
        appliance_type="washer",
        name="Suspension Spring Failure",
        description=(
            "One or more suspension springs supporting the drum have failed, causing "
            "excessive shaking or banging, especially during the spin cycle."
        ),
        severity="medium",
        typical_symptoms=[
            "machine shakes violently or 'walks' across the floor during spin",
            "loud banging noise during spin cycle",
            "visibly uneven drum movement",
        ],
        typical_cost_min=1500, typical_cost_max=3200,
    ),
    FaultCreate(
        appliance_type="washer",
        name="Motor Coupler Crack",
        description=(
            "A cracked motor coupler (a small plastic part connecting the motor to the "
            "transmission) preventing the drum from spinning even though the motor runs."
        ),
        severity="medium",
        typical_symptoms=[
            "motor makes noise but drum doesn't spin at all",
            "washer fills with water but never agitates or spins",
        ],
        typical_cost_min=700, typical_cost_max=1600,
    ),

    # ───────────────────────── PURIFIER ─────────────────────────
    FaultCreate(
        appliance_type="purifier",
        name="Filter Clog / Overload",
        description=(
            "A clogged or overdue filter restricting airflow and straining the motor — "
            "the single most common purifier issue, and usually the cheapest to fix."
        ),
        severity="low",
        typical_symptoms=[
            "noticeably weaker airflow than when new",
            "motor sounds strained or louder than usual",
            "filter indicator light on (if equipped) or filter visibly dirty",
        ],
        typical_cost_min=400, typical_cost_max=900,
    ),
    FaultCreate(
        appliance_type="purifier",
        name="Fan Motor Wear",
        description=(
            "Worn fan motor bearings or brushes causing reduced airflow and an unusual "
            "motor sound independent of filter condition."
        ),
        severity="medium",
        typical_symptoms=[
            "grinding or whining sound from the motor",
            "weak airflow even with a clean/new filter",
            "motor runs hot to the touch",
        ],
        typical_cost_min=900, typical_cost_max=2000,
    ),
    FaultCreate(
        appliance_type="purifier",
        name="Sensor Miscalibration",
        description=(
            "The air-quality sensor is misreading ambient conditions, causing the unit "
            "to run at the wrong speed (too high or too low) regardless of actual air quality."
        ),
        severity="low",
        typical_symptoms=[
            "unit runs at max speed even in clean air",
            "air quality indicator doesn't change regardless of conditions",
            "unit runs at low speed despite visibly smoky/dusty air",
        ],
        typical_cost_min=500, typical_cost_max=1100,
    ),

    # ───────────────────────── CAMERA ─────────────────────────
    FaultCreate(
        appliance_type="camera",
        name="IR LED Array Failure",
        description=(
            "Partial or complete failure of the infrared LED array used for night "
            "vision, common after moisture exposure or prolonged outdoor heat cycling."
        ),
        severity="medium",
        typical_symptoms=[
            "night vision image is dark or has dead zones",
            "daytime image is fine but night image is poor or black",
            "visible dimming of the small red/IR LEDs around the lens at night",
        ],
        typical_cost_min=800, typical_cost_max=1800,
    ),
    FaultCreate(
        appliance_type="camera",
        name="Image Sensor Drift",
        description=(
            "Gradual degradation of the image sensor causing color shifts, graininess, "
            "or loss of detail over time, independent of lighting conditions."
        ),
        severity="medium",
        typical_symptoms=[
            "image looks grainy or noisy even in good lighting",
            "colors look washed out or shifted (e.g. everything looks slightly pink/green)",
            "image quality has visibly degraded over months of use",
        ],
        typical_cost_min=1200, typical_cost_max=2800,
    ),
    FaultCreate(
        appliance_type="camera",
        name="Firmware Glitch",
        description=(
            "A software-level fault causing intermittent freezing, disconnection, or "
            "incorrect behavior, often resolvable without any hardware replacement."
        ),
        severity="low",
        typical_symptoms=[
            "camera randomly disconnects from the app",
            "live view freezes but the camera light is still on",
            "camera occasionally reboots itself",
        ],
        typical_cost_min=0, typical_cost_max=400,
    ),
    FaultCreate(
        appliance_type="camera",
        name="Power Supply Instability",
        description=(
            "An unstable or failing power adapter/supply causing intermittent shutdowns "
            "or rebooting, especially under load (e.g. when night vision or recording kicks in)."
        ),
        severity="medium",
        typical_symptoms=[
            "camera reboots when night vision turns on",
            "camera works fine on first plug-in but cuts out after a while",
            "power adapter feels warm or makes a faint buzzing sound",
        ],
        typical_cost_min=300, typical_cost_max=800,
    ),
]


async def seed():
    connect_to_mongo()
    db = get_db()

    created, skipped = 0, 0
    for fault in FAULTS:
        existing = await db.faults.find_one(
            {"appliance_type": fault.appliance_type, "name": fault.name}
        )
        if existing is not None:
            print(f"SKIP  (already exists): {fault.appliance_type} / {fault.name}")
            skipped += 1
            continue

        doc = new_fault_document(fault)
        await db.faults.insert_one(doc)
        print(f"ADDED: {fault.appliance_type} / {fault.name}")
        created += 1

    print(f"\nDone. {created} added, {skipped} skipped (already existed).")
    close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(seed())