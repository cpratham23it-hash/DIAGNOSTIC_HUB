"""
Seeds the symptom_questions collection with a small number of REAL,
working decision-tree branches per appliance — not an exhaustive tree.

Building out the full tree (every real branch a technician would ask
about) is content/knowledge-engineering work that should come from real
diagnostic experience, not be fabricated wholesale. What's here is a
working skeleton: enough real branches per appliance to prove the engine
end-to-end and give you a concrete pattern to extend.

Run locally with:
    python -m app.scripts.seed_symptom_questions

Safe to re-run: it checks for an identical (appliance_type, question_text,
parent_question_id, parent_option_value) combination before inserting.
NOTE: this dedup check needs the parent's real Mongo _id, so each
appliance's questions must be inserted in tree order (root, then its
children, then their children) — which is exactly the order below. Don't
reorder these blocks.
"""

import asyncio
from datetime import datetime, timezone

from app.database import close_mongo_connection, connect_to_mongo, get_db


async def _find_or_create(db, *, appliance_type, question_text, parent_id, parent_value, options, resolves_to=None):
    existing = await db.symptom_questions.find_one({
        "appliance_type": appliance_type,
        "question_text": question_text,
        "parent_question_id": parent_id,
        "parent_option_value": parent_value,
    })
    if existing is not None:
        return existing["_id"], False

    doc = {
        "appliance_type": appliance_type,
        "question_text": question_text,
        "parent_question_id": parent_id,
        "parent_option_value": parent_value,
        "options": options,
        "resolves_to": resolves_to,
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.symptom_questions.insert_one(doc)
    return result.inserted_id, True


async def seed_fridge(db, counters):
    root_id, created = await _find_or_create(
        db,
        appliance_type="fridge",
        question_text="What's the fridge doing?",
        parent_id=None, parent_value=None,
        options=[
            {"value": "not_cooling", "label": "Not cooling at all"},
            {"value": "noisy", "label": "Running but making an unusual noise"},
            {"value": "warm_outside", "label": "Outside/back panel feels unusually warm"},
        ],
    )
    counters["created" if created else "skipped"] += 1
    root_id = str(root_id)

    q2_id, created = await _find_or_create(
        db,
        appliance_type="fridge",
        question_text="When it tries to cool, do you hear any sound from the compressor area?",
        parent_id=root_id, parent_value="not_cooling",
        options=[
            {"value": "clicking_no_start", "label": "Clicking every few minutes, but it never starts"},
            {"value": "silent", "label": "Completely silent, nothing happens"},
        ],
    )
    counters["created" if created else "skipped"] += 1
    q2_id = str(q2_id)

    _, created = await _find_or_create(
        db,
        appliance_type="fridge",
        question_text="(leaf) clicking, no start",
        parent_id=q2_id, parent_value="clicking_no_start",
        options=[],
        resolves_to=[{"fault_name": "Start Relay Failure", "confidence": 62}],
    )
    counters["created" if created else "skipped"] += 1

    _, created = await _find_or_create(
        db,
        appliance_type="fridge",
        question_text="(leaf) silent, not cooling",
        parent_id=q2_id, parent_value="silent",
        options=[],
        resolves_to=[
            {"fault_name": "Compressor Strain", "confidence": 45},
            {"fault_name": "Start Relay Failure", "confidence": 30},
        ],
    )
    counters["created" if created else "skipped"] += 1

    _, created = await _find_or_create(
        db,
        appliance_type="fridge",
        question_text="(leaf) noisy",
        parent_id=root_id, parent_value="noisy",
        options=[],
        resolves_to=[{"fault_name": "Compressor Strain", "confidence": 58}],
    )
    counters["created" if created else "skipped"] += 1

    _, created = await _find_or_create(
        db,
        appliance_type="fridge",
        question_text="(leaf) warm outside",
        parent_id=root_id, parent_value="warm_outside",
        options=[],
        resolves_to=[{"fault_name": "Condenser Coil Blockage", "confidence": 67}],
    )
    counters["created" if created else "skipped"] += 1


async def seed_ac(db, counters):
    root_id, created = await _find_or_create(
        db,
        appliance_type="ac",
        question_text="What are you noticing with the AC?",
        parent_id=None, parent_value=None,
        options=[
            {"value": "noise", "label": "An unusual sound while running"},
            {"value": "wont_start", "label": "It hums but won't actually turn on"},
        ],
    )
    counters["created" if created else "skipped"] += 1
    root_id = str(root_id)

    q2_id, created = await _find_or_create(
        db,
        appliance_type="ac",
        question_text="What kind of sound is it?",
        parent_id=root_id, parent_value="noise",
        options=[
            {"value": "knocking", "label": "Rhythmic knocking or thumping"},
            {"value": "whining", "label": "High-pitched whining or grinding"},
            {"value": "rattling_wall", "label": "Rattling that seems to come from the wall/frame"},
        ],
    )
    counters["created" if created else "skipped"] += 1
    q2_id = str(q2_id)

    _, created = await _find_or_create(
        db,
        appliance_type="ac",
        question_text="(leaf) knocking",
        parent_id=q2_id, parent_value="knocking",
        options=[],
        resolves_to=[{"fault_name": "Fan Blade Imbalance", "confidence": 72}],
    )
    counters["created" if created else "skipped"] += 1

    _, created = await _find_or_create(
        db,
        appliance_type="ac",
        question_text="(leaf) whining",
        parent_id=q2_id, parent_value="whining",
        options=[],
        resolves_to=[{"fault_name": "Bearing Wear", "confidence": 64}],
    )
    counters["created" if created else "skipped"] += 1

    _, created = await _find_or_create(
        db,
        appliance_type="ac",
        question_text="(leaf) rattling wall",
        parent_id=q2_id, parent_value="rattling_wall",
        options=[],
        resolves_to=[{"fault_name": "Loose Mounting Bracket", "confidence": 70}],
    )
    counters["created" if created else "skipped"] += 1

    _, created = await _find_or_create(
        db,
        appliance_type="ac",
        question_text="(leaf) wont start",
        parent_id=root_id, parent_value="wont_start",
        options=[],
        resolves_to=[{"fault_name": "Capacitor Fault", "confidence": 68}],
    )
    counters["created" if created else "skipped"] += 1


async def seed_washer(db, counters):
    root_id, created = await _find_or_create(
        db,
        appliance_type="washer",
        question_text="What's happening with the washer?",
        parent_id=None, parent_value=None,
        options=[
            {"value": "no_spin", "label": "Drum doesn't spin at all"},
            {"value": "shaking", "label": "Shakes violently during spin"},
            {"value": "grinding", "label": "Grinding noise during spin"},
        ],
    )
    counters["created" if created else "skipped"] += 1
    root_id = str(root_id)

    q2_id, created = await _find_or_create(
        db,
        appliance_type="washer",
        question_text="Does the motor make any sound when the drum should be spinning?",
        parent_id=root_id, parent_value="no_spin",
        options=[
            {"value": "motor_runs", "label": "Yes, the motor runs but the drum stays still"},
            {"value": "nothing", "label": "No, nothing happens at all"},
        ],
    )
    counters["created" if created else "skipped"] += 1
    q2_id = str(q2_id)

    _, created = await _find_or_create(
        db,
        appliance_type="washer",
        question_text="(leaf) motor runs, no spin",
        parent_id=q2_id, parent_value="motor_runs",
        options=[],
        resolves_to=[
            {"fault_name": "Motor Coupler Crack", "confidence": 55},
            {"fault_name": "Worn Drive Belt", "confidence": 40},
        ],
    )
    counters["created" if created else "skipped"] += 1

    _, created = await _find_or_create(
        db,
        appliance_type="washer",
        question_text="(leaf) shaking",
        parent_id=root_id, parent_value="shaking",
        options=[],
        resolves_to=[{"fault_name": "Suspension Spring Failure", "confidence": 66}],
    )
    counters["created" if created else "skipped"] += 1

    _, created = await _find_or_create(
        db,
        appliance_type="washer",
        question_text="(leaf) grinding",
        parent_id=root_id, parent_value="grinding",
        options=[],
        resolves_to=[{"fault_name": "Drum Bearing Wear", "confidence": 73}],
    )
    counters["created" if created else "skipped"] += 1


async def seed_purifier(db, counters):
    root_id, created = await _find_or_create(
        db,
        appliance_type="purifier",
        question_text="What's the issue with the purifier?",
        parent_id=None, parent_value=None,
        options=[
            {"value": "weak_airflow", "label": "Airflow feels weaker than usual"},
            {"value": "wrong_speed", "label": "Runs at the wrong speed for the air quality"},
        ],
    )
    counters["created" if created else "skipped"] += 1
    root_id = str(root_id)

    q2_id, created = await _find_or_create(
        db,
        appliance_type="purifier",
        question_text="Have you checked or changed the filter recently?",
        parent_id=root_id, parent_value="weak_airflow",
        options=[
            {"value": "old_filter", "label": "No, it's been a while"},
            {"value": "new_filter", "label": "Yes, it's clean/new and still weak"},
        ],
    )
    counters["created" if created else "skipped"] += 1
    q2_id = str(q2_id)

    _, created = await _find_or_create(
        db,
        appliance_type="purifier",
        question_text="(leaf) old filter",
        parent_id=q2_id, parent_value="old_filter",
        options=[],
        resolves_to=[{"fault_name": "Filter Clog / Overload", "confidence": 80}],
    )
    counters["created" if created else "skipped"] += 1

    _, created = await _find_or_create(
        db,
        appliance_type="purifier",
        question_text="(leaf) new filter still weak",
        parent_id=q2_id, parent_value="new_filter",
        options=[],
        resolves_to=[{"fault_name": "Fan Motor Wear", "confidence": 58}],
    )
    counters["created" if created else "skipped"] += 1

    _, created = await _find_or_create(
        db,
        appliance_type="purifier",
        question_text="(leaf) wrong speed",
        parent_id=root_id, parent_value="wrong_speed",
        options=[],
        resolves_to=[{"fault_name": "Sensor Miscalibration", "confidence": 61}],
    )
    counters["created" if created else "skipped"] += 1


async def seed_camera(db, counters):
    root_id, created = await _find_or_create(
        db,
        appliance_type="camera",
        question_text="What's going wrong with the camera?",
        parent_id=None, parent_value=None,
        options=[
            {"value": "bad_night", "label": "Night vision looks dark or has dead zones"},
            {"value": "reboots", "label": "Randomly disconnects or reboots"},
        ],
    )
    counters["created" if created else "skipped"] += 1
    root_id = str(root_id)

    _, created = await _find_or_create(
        db,
        appliance_type="camera",
        question_text="(leaf) bad night vision",
        parent_id=root_id, parent_value="bad_night",
        options=[],
        resolves_to=[{"fault_name": "IR LED Array Failure", "confidence": 65}],
    )
    counters["created" if created else "skipped"] += 1

    q2_id, created = await _find_or_create(
        db,
        appliance_type="camera",
        question_text="Does it reboot specifically when night vision kicks in, or at random times?",
        parent_id=root_id, parent_value="reboots",
        options=[
            {"value": "on_night_vision", "label": "Specifically when night vision turns on"},
            {"value": "random", "label": "At random times, no clear pattern"},
        ],
    )
    counters["created" if created else "skipped"] += 1
    q2_id = str(q2_id)

    _, created = await _find_or_create(
        db,
        appliance_type="camera",
        question_text="(leaf) reboots on night vision",
        parent_id=q2_id, parent_value="on_night_vision",
        options=[],
        resolves_to=[{"fault_name": "Power Supply Instability", "confidence": 70}],
    )
    counters["created" if created else "skipped"] += 1

    _, created = await _find_or_create(
        db,
        appliance_type="camera",
        question_text="(leaf) random reboots",
        parent_id=q2_id, parent_value="random",
        options=[],
        resolves_to=[{"fault_name": "Firmware Glitch", "confidence": 55}],
    )
    counters["created" if created else "skipped"] += 1


async def seed():
    connect_to_mongo()
    db = get_db()

    counters = {"created": 0, "skipped": 0}

    await seed_fridge(db, counters)
    await seed_ac(db, counters)
    await seed_washer(db, counters)
    await seed_purifier(db, counters)
    await seed_camera(db, counters)

    print(f"Done. {counters['created']} questions created, {counters['skipped']} already existed.")
    close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(seed())