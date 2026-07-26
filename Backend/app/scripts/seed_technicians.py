"""
Seeds the technicians collection with demo technician profiles.
Run: python -m app.scripts.seed_technicians
Safe to re-run: duplicates skipped by name.
"""

import asyncio
from app.database import connect_to_mongo, close_mongo_connection, get_db
from app.models.technician import TechnicianCreate, new_technician_document

TECHNICIANS = [
    TechnicianCreate(
        name="Rakesh Iyer",
        service_area="Mumbai",
        specialties=["Compressor Strain", "Start Relay Failure", "Refrigerant Leak",
                     "Condenser Coil Blockage", "Thermostat Fault", "Compressor Failure"],
        price_per_visit=650,
    ),
    TechnicianCreate(
        name="Fathima Begum",
        service_area="Mumbai",
        specialties=["Compressor Strain", "Condenser Coil Blockage", "Door Seal Damage",
                     "Evaporator Ice Buildup", "Dirty Air Filter", "Drainage Blockage",
                     "Mold and Mildew Buildup", "Filter Clog / Overload"],
        price_per_visit=500,
    ),
    TechnicianCreate(
        name="Suresh Patil",
        service_area="Mumbai",
        specialties=["Fan Blade Imbalance", "Bearing Wear", "Drum Bearing Wear",
                     "Worn Drive Belt", "Suspension Spring Failure", "Motor Coupler Crack",
                     "Fan Motor Wear"],
        price_per_visit=450,
    ),
    TechnicianCreate(
        name="Priya Sharma",
        service_area="Mumbai",
        specialties=["Capacitor Fault", "Refrigerant Leak", "Compressor Failure",
                     "Start Relay Failure", "Water Inlet Valve Failure",
                     "Power Supply Instability", "Electrical Damage"],
        price_per_visit=700,
    ),
    TechnicianCreate(
        name="Mohammed Khan",
        service_area="Mumbai",
        specialties=["IR LED Array Failure", "Image Sensor Drift", "Firmware Glitch",
                     "Lens Obstruction or Damage", "Weather Seal Failure",
                     "Sensor Miscalibration", "UV Lamp Failure"],
        price_per_visit=550,
    ),
    TechnicianCreate(
        name="Anita Deshmukh",
        service_area="Mumbai",
        specialties=["External Corrosion", "Door Seal Damage", "Door Lock Failure",
                     "Water Dispenser Leak", "Drain Pump Blockage",
                     "Mounting Damage", "External Body Damage", "Fin Damage"],
        price_per_visit=400,
    ),
]


async def seed():
    connect_to_mongo()
    db = get_db()

    # Set ratings/jobs for demo
    extras = [
        {"rating": 4.9, "jobs_completed": 212},
        {"rating": 4.8, "jobs_completed": 156},
        {"rating": 4.6, "jobs_completed": 89},
        {"rating": 4.7, "jobs_completed": 178},
        {"rating": 4.5, "jobs_completed": 64},
        {"rating": 4.4, "jobs_completed": 102},
    ]

    created, skipped = 0, 0
    for i, tech in enumerate(TECHNICIANS):
        existing = await db.technicians.find_one({"name": tech.name})
        if existing:
            print(f"SKIP (exists): {tech.name}")
            skipped += 1
            continue
        doc = new_technician_document(tech)
        doc.update(extras[i])
        await db.technicians.insert_one(doc)
        print(f"ADDED: {tech.name}")
        created += 1

    print(f"\nDone. {created} added, {skipped} skipped.")
    close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(seed())