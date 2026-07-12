"""
Seeds the faults collection with a comprehensive fault library covering
audio, text, AND visual (image) symptoms for all 5 appliance types.

Run locally with:
    python -m app.scripts.seed_faults

Safe to re-run: duplicates are skipped (same appliance_type + name).

COST RANGES are reasonable estimates for Indian appliance repair market,
NOT sourced from a verified dataset.
"""

import asyncio

from app.database import close_mongo_connection, connect_to_mongo, get_db
from app.models.fault import FaultCreate, new_fault_document

FAULTS: list[FaultCreate] = [

    # ═══════════════════════════ FRIDGE ═══════════════════════════

    FaultCreate(
        appliance_type="fridge",
        name="Compressor Strain",
        description="Early-stage compressor strain, often caused by a failing start relay or low refrigerant pressure forcing the compressor to work harder than it should.",
        severity="high",
        typical_symptoms=[
            "loud clicking or clunking near the compressor",
            "compressor runs constantly without cycling off",
            "fridge feels warm on the back or side panel",
            "noticeably higher electricity bill",
            "[image] compressor area discolored or overheated",
            "[image] burn marks near compressor wiring",
        ],
        typical_cost_min=2800, typical_cost_max=4500,
    ),
    FaultCreate(
        appliance_type="fridge",
        name="Start Relay Failure",
        description="The start relay has failed or is intermittently failing, often preventing the compressor from starting at all.",
        severity="medium",
        typical_symptoms=[
            "fridge makes a clicking sound every few minutes but doesn't start cooling",
            "compressor hums but doesn't start",
            "fridge stopped cooling suddenly",
            "[image] burnt or blackened relay component",
        ],
        typical_cost_min=400, typical_cost_max=900,
    ),
    FaultCreate(
        appliance_type="fridge",
        name="Condenser Coil Blockage",
        description="Dust or lint buildup on the condenser coils restricting heat dissipation, making the fridge work harder and cool less efficiently.",
        severity="low",
        typical_symptoms=[
            "fridge running hotter on the outside than usual",
            "food not staying as cold as it used to",
            "visible dust buildup at the back of the unit",
            "[image] thick dust or lint coating on condenser coils",
            "[image] dirty or clogged coils visible at the back or bottom",
        ],
        typical_cost_min=300, typical_cost_max=700,
    ),
    FaultCreate(
        appliance_type="fridge",
        name="Thermostat Fault",
        description="The thermostat is misreading internal temperature or failing to signal the compressor correctly.",
        severity="medium",
        typical_symptoms=[
            "inconsistent temperature inside the fridge",
            "food freezing in the fridge compartment",
            "compressor won't turn off even when set to a low cooling level",
        ],
        typical_cost_min=500, typical_cost_max=1200,
    ),
    FaultCreate(
        appliance_type="fridge",
        name="Door Seal Damage",
        description="The rubber gasket around the door has cracked, warped, or degraded, allowing warm air to leak in and forcing the compressor to run longer.",
        severity="low",
        typical_symptoms=[
            "condensation or moisture around the door edges",
            "fridge running more frequently than usual",
            "warm spots inside the fridge near the door",
            "[image] cracked, torn, or moldy door gasket",
            "[image] visible gap between door seal and fridge body",
            "[image] mold or mildew growing on the rubber seal",
        ],
        typical_cost_min=500, typical_cost_max=1500,
    ),
    FaultCreate(
        appliance_type="fridge",
        name="Evaporator Ice Buildup",
        description="Excessive frost or ice buildup on the evaporator coils, usually due to a defrost heater or timer failure.",
        severity="medium",
        typical_symptoms=[
            "freezer section has thick ice buildup",
            "fridge not cooling but freezer is frosted over",
            "unusual hissing or dripping sounds",
            "[image] thick ice or frost coating inside the freezer",
            "[image] ice blocking the air vents inside the fridge",
            "[image] frost buildup on the back wall of the freezer compartment",
        ],
        typical_cost_min=1500, typical_cost_max=3000,
    ),
    FaultCreate(
        appliance_type="fridge",
        name="Refrigerant Leak",
        description="Loss of refrigerant through a crack or corrosion hole in the sealed system, causing reduced cooling capacity.",
        severity="high",
        typical_symptoms=[
            "fridge not cooling at all despite compressor running",
            "oily residue near the back or bottom of the unit",
            "hissing sound from the back of the fridge",
            "[image] oily or greasy stains near tubing or joints",
            "[image] corrosion or green deposits on copper tubing",
            "[image] wet spots or puddles under the fridge",
        ],
        typical_cost_min=3000, typical_cost_max=6000,
    ),
    FaultCreate(
        appliance_type="fridge",
        name="External Corrosion",
        description="Significant rust and corrosion on the exterior body panels, indicating age-related degradation that may extend to internal components.",
        severity="medium",
        typical_symptoms=[
            "visible rust patches on the fridge body",
            "paint peeling or bubbling on exterior panels",
            "structural weakness in the body panels",
            "[image] rust spots or large rust patches on the exterior",
            "[image] peeling paint exposing corroded metal underneath",
            "[image] structural holes or degradation from corrosion",
        ],
        typical_cost_min=2000, typical_cost_max=5000,
    ),
    FaultCreate(
        appliance_type="fridge",
        name="Water Dispenser Leak",
        description="The water dispenser line or valve is leaking, causing water pooling inside or under the fridge.",
        severity="low",
        typical_symptoms=[
            "water pooling inside the fridge or on the floor",
            "dispenser drips even when not in use",
            "[image] water stains or puddles inside the fridge",
            "[image] mineral deposits around the dispenser nozzle",
        ],
        typical_cost_min=400, typical_cost_max=1200,
    ),
    FaultCreate(
        appliance_type="fridge",
        name="Interior Light Failure",
        description="The interior light bulb or LED module has failed, or the door switch is faulty.",
        severity="low",
        typical_symptoms=[
            "light doesn't turn on when door is opened",
            "light flickers intermittently",
            "[image] dark interior when door is open",
            "[image] discolored or burnt-out light socket",
        ],
        typical_cost_min=100, typical_cost_max=500,
    ),

    # ═══════════════════════════ AC ═══════════════════════════

    FaultCreate(
        appliance_type="ac",
        name="Fan Blade Imbalance",
        description="An imbalanced or bent fan blade causing rhythmic vibration or knocking sound.",
        severity="medium",
        typical_symptoms=[
            "rhythmic knocking or thumping sound when running",
            "unit vibrates noticeably more than usual",
            "noise changes with fan speed setting",
            "[image] visibly bent or damaged fan blade",
            "[image] dust buildup causing weight imbalance on blades",
        ],
        typical_cost_min=1200, typical_cost_max=2200,
    ),
    FaultCreate(
        appliance_type="ac",
        name="Loose Mounting Bracket",
        description="The indoor or outdoor unit's mounting bracket has loosened, causing vibration against the wall.",
        severity="low",
        typical_symptoms=[
            "rattling sound from the wall or frame, not the unit",
            "unit appears to shift slightly when running",
            "[image] visible gap between mounting bracket and wall",
            "[image] cracked or rusted mounting hardware",
        ],
        typical_cost_min=400, typical_cost_max=900,
    ),
    FaultCreate(
        appliance_type="ac",
        name="Bearing Wear",
        description="Worn fan motor bearings causing friction and a high-pitched whining or grinding sound.",
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
        description="A failing start or run capacitor preventing the compressor or fan motor from starting reliably.",
        severity="high",
        typical_symptoms=[
            "AC hums but doesn't start",
            "AC turns off by itself a few minutes after starting",
            "outdoor unit fan doesn't spin even when the indoor unit is on",
            "[image] swollen or bulging capacitor",
            "[image] leaked or leaking electrolyte from capacitor",
        ],
        typical_cost_min=600, typical_cost_max=1400,
    ),
    FaultCreate(
        appliance_type="ac",
        name="Dirty Air Filter",
        description="Clogged or dirty air filter restricting airflow, reducing cooling efficiency and straining the system.",
        severity="low",
        typical_symptoms=[
            "weak airflow from the indoor unit",
            "AC takes longer to cool the room",
            "musty or stale smell when AC is running",
            "[image] visibly dirty or clogged air filter",
            "[image] dust and debris buildup on filter mesh",
            "[image] discolored filter that should be white or light-colored",
        ],
        typical_cost_min=200, typical_cost_max=600,
    ),
    FaultCreate(
        appliance_type="ac",
        name="Refrigerant Leak",
        description="Loss of refrigerant gas through a leak in the coils or connection joints, reducing cooling capacity.",
        severity="high",
        typical_symptoms=[
            "AC blowing warm or room-temperature air",
            "ice forming on the indoor unit coils",
            "hissing sound from the indoor or outdoor unit",
            "[image] ice or frost on the evaporator coils",
            "[image] oily residue around pipe connections",
            "[image] corrosion on copper tubing joints",
        ],
        typical_cost_min=2500, typical_cost_max=5000,
    ),
    FaultCreate(
        appliance_type="ac",
        name="Drainage Blockage",
        description="The condensate drain pipe is blocked, causing water to back up and leak from the indoor unit.",
        severity="low",
        typical_symptoms=[
            "water dripping from the indoor unit",
            "water stains on the wall below the AC",
            "gurgling sound from the indoor unit",
            "[image] water dripping or pooling below the indoor unit",
            "[image] algae or mold growth in the drain tray",
            "[image] water stains or damage on the wall",
        ],
        typical_cost_min=300, typical_cost_max=800,
    ),
    FaultCreate(
        appliance_type="ac",
        name="Compressor Failure",
        description="The compressor has failed or is failing, causing complete loss of cooling. Most expensive AC repair.",
        severity="high",
        typical_symptoms=[
            "AC runs but doesn't cool at all",
            "outdoor unit makes loud or unusual noises",
            "circuit breaker trips when AC starts",
            "[image] burn marks or discoloration on compressor",
            "[image] oil leak around the compressor unit",
        ],
        typical_cost_min=5000, typical_cost_max=12000,
    ),
    FaultCreate(
        appliance_type="ac",
        name="Fin Damage",
        description="Bent or crushed aluminum fins on the condenser or evaporator coils restricting airflow.",
        severity="low",
        typical_symptoms=[
            "reduced cooling despite clean filters",
            "outdoor unit runs hot",
            "[image] bent, crushed, or flattened aluminum fins on the coils",
            "[image] debris lodged between the fins",
        ],
        typical_cost_min=500, typical_cost_max=1500,
    ),

    # ═══════════════════════════ WASHER ═══════════════════════════

    FaultCreate(
        appliance_type="washer",
        name="Drum Bearing Wear",
        description="Worn drum bearings causing a grinding noise during spin cycles, usually after years of heavy loads.",
        severity="high",
        typical_symptoms=[
            "loud grinding noise specifically during the spin cycle",
            "noise has gotten progressively worse over weeks or months",
            "drum feels loose when rotated by hand while empty",
            "[image] rust stains or residue around the drum opening",
            "[image] water leaking from beneath the machine",
        ],
        typical_cost_min=3500, typical_cost_max=6000,
    ),
    FaultCreate(
        appliance_type="washer",
        name="Worn Drive Belt",
        description="The belt connecting the motor to the drum has worn, stretched, or slipped.",
        severity="medium",
        typical_symptoms=[
            "drum doesn't spin or spins very slowly",
            "burning rubber smell during operation",
            "motor runs but drum doesn't move",
            "[image] frayed, cracked, or shiny drive belt",
            "[image] rubber debris inside the machine",
        ],
        typical_cost_min=800, typical_cost_max=1800,
    ),
    FaultCreate(
        appliance_type="washer",
        name="Suspension Spring Failure",
        description="One or more suspension springs supporting the drum have failed, causing excessive shaking.",
        severity="medium",
        typical_symptoms=[
            "machine shakes violently or walks across the floor during spin",
            "loud banging noise during spin cycle",
            "visibly uneven drum movement",
            "[image] broken or disconnected spring hanging inside the machine",
            "[image] machine visibly tilted or uneven",
        ],
        typical_cost_min=1500, typical_cost_max=3200,
    ),
    FaultCreate(
        appliance_type="washer",
        name="Motor Coupler Crack",
        description="A cracked motor coupler preventing the drum from spinning even though the motor runs.",
        severity="medium",
        typical_symptoms=[
            "motor makes noise but drum doesn't spin at all",
            "washer fills with water but never agitates or spins",
            "[image] cracked or broken plastic coupler piece",
        ],
        typical_cost_min=700, typical_cost_max=1600,
    ),
    FaultCreate(
        appliance_type="washer",
        name="Door Lock Failure",
        description="The electronic door lock mechanism has failed, preventing the wash cycle from starting.",
        severity="medium",
        typical_symptoms=[
            "washer won't start even though it's plugged in and has water",
            "door doesn't click or lock when closed",
            "error code related to door lock on display",
            "[image] damaged or misaligned door latch mechanism",
            "[image] cracked door handle or hinge",
        ],
        typical_cost_min=600, typical_cost_max=1500,
    ),
    FaultCreate(
        appliance_type="washer",
        name="Water Inlet Valve Failure",
        description="The water inlet valve is stuck open, closed, or leaking, affecting water fill.",
        severity="medium",
        typical_symptoms=[
            "washer doesn't fill with water",
            "washer overfills with water",
            "water continues to trickle in even when off",
            "[image] mineral deposits or rust around the water inlet",
            "[image] water leaking from the hose connection at the back",
        ],
        typical_cost_min=800, typical_cost_max=2000,
    ),
    FaultCreate(
        appliance_type="washer",
        name="Drain Pump Blockage",
        description="Foreign objects or lint blocking the drain pump, preventing water from draining after a wash cycle.",
        severity="low",
        typical_symptoms=[
            "water remains in the drum after the cycle ends",
            "machine displays a drain error",
            "foul smell from stagnant water",
            "[image] lint or debris visible in the drain filter",
            "[image] standing water inside the drum after cycle",
        ],
        typical_cost_min=400, typical_cost_max=1200,
    ),
    FaultCreate(
        appliance_type="washer",
        name="Mold and Mildew Buildup",
        description="Mold or mildew growing inside the drum, gasket, or detergent drawer due to moisture retention.",
        severity="low",
        typical_symptoms=[
            "musty or foul smell from the machine",
            "black spots visible on the door gasket",
            "clothes smell bad even after washing",
            "[image] black mold spots on the rubber door gasket",
            "[image] mildew or discoloration inside the detergent drawer",
            "[image] dark residue on the drum surface",
        ],
        typical_cost_min=300, typical_cost_max=800,
    ),

    # ═══════════════════════════ PURIFIER ═══════════════════════════

    FaultCreate(
        appliance_type="purifier",
        name="Filter Clog / Overload",
        description="A clogged or overdue filter restricting airflow and straining the motor.",
        severity="low",
        typical_symptoms=[
            "noticeably weaker airflow than when new",
            "motor sounds strained or louder than usual",
            "filter indicator light on or filter visibly dirty",
            "[image] discolored or darkened filter element",
            "[image] visible dust and debris caked on the filter",
            "[image] filter that has turned brown or grey from use",
        ],
        typical_cost_min=400, typical_cost_max=900,
    ),
    FaultCreate(
        appliance_type="purifier",
        name="Fan Motor Wear",
        description="Worn fan motor bearings or brushes causing reduced airflow and unusual motor sound.",
        severity="medium",
        typical_symptoms=[
            "grinding or whining sound from the motor",
            "weak airflow even with a clean or new filter",
            "motor runs hot to the touch",
        ],
        typical_cost_min=900, typical_cost_max=2000,
    ),
    FaultCreate(
        appliance_type="purifier",
        name="Sensor Miscalibration",
        description="The air-quality sensor is misreading ambient conditions, causing incorrect speed settings.",
        severity="low",
        typical_symptoms=[
            "unit runs at max speed even in clean air",
            "air quality indicator doesn't change regardless of conditions",
            "unit runs at low speed despite visibly smoky or dusty air",
            "[image] dusty or obstructed sensor opening",
        ],
        typical_cost_min=500, typical_cost_max=1100,
    ),
    FaultCreate(
        appliance_type="purifier",
        name="UV Lamp Failure",
        description="The UV-C germicidal lamp has burned out or degraded, reducing sterilization capability.",
        severity="medium",
        typical_symptoms=[
            "UV indicator light off or flickering",
            "no visible UV glow through the vent when running",
            "[image] darkened or blackened UV lamp tube",
            "[image] UV lamp indicator not lit on the unit",
        ],
        typical_cost_min=600, typical_cost_max=1500,
    ),
    FaultCreate(
        appliance_type="purifier",
        name="Water Tank Leak",
        description="Crack or seal failure in the water tank of a humidifier-purifier combo unit.",
        severity="medium",
        typical_symptoms=[
            "water pooling around the base of the unit",
            "reduced or no mist output",
            "[image] visible crack in the water tank",
            "[image] water stains or mineral deposits around the base",
        ],
        typical_cost_min=500, typical_cost_max=1400,
    ),
    FaultCreate(
        appliance_type="purifier",
        name="External Body Damage",
        description="Physical damage to the purifier housing from drops, impacts, or age-related wear.",
        severity="low",
        typical_symptoms=[
            "unit rattles or vibrates due to cracked housing",
            "parts feel loose when touched",
            "[image] cracked or broken plastic housing",
            "[image] dents or impact damage on the body",
            "[image] broken control panel or buttons",
        ],
        typical_cost_min=300, typical_cost_max=1000,
    ),

    # ═══════════════════════════ CAMERA ═══════════════════════════

    FaultCreate(
        appliance_type="camera",
        name="IR LED Array Failure",
        description="Partial or complete failure of the infrared LED array used for night vision.",
        severity="medium",
        typical_symptoms=[
            "night vision image is dark or has dead zones",
            "daytime image is fine but night image is poor or black",
            "visible dimming of the IR LEDs around the lens at night",
            "[image] some IR LEDs not lit when viewed through phone camera at night",
            "[image] uneven or patchy night vision illumination",
        ],
        typical_cost_min=800, typical_cost_max=1800,
    ),
    FaultCreate(
        appliance_type="camera",
        name="Image Sensor Drift",
        description="Gradual degradation of the image sensor causing color shifts, graininess, or loss of detail.",
        severity="medium",
        typical_symptoms=[
            "image looks grainy or noisy even in good lighting",
            "colors look washed out or shifted",
            "image quality has visibly degraded over months of use",
            "[image] visible noise or grain in the camera feed screenshot",
            "[image] color cast or tint in the captured image",
        ],
        typical_cost_min=1200, typical_cost_max=2800,
    ),
    FaultCreate(
        appliance_type="camera",
        name="Firmware Glitch",
        description="A software-level fault causing intermittent freezing, disconnection, or incorrect behavior.",
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
        description="An unstable or failing power adapter causing intermittent shutdowns or rebooting.",
        severity="medium",
        typical_symptoms=[
            "camera reboots when night vision turns on",
            "camera works fine initially but cuts out after a while",
            "power adapter feels warm or makes a faint buzzing sound",
            "[image] damaged or frayed power cable",
            "[image] discolored or melted power adapter",
        ],
        typical_cost_min=300, typical_cost_max=800,
    ),
    FaultCreate(
        appliance_type="camera",
        name="Lens Obstruction or Damage",
        description="The camera lens is scratched, cracked, fogged, or obstructed by dirt or spider webs.",
        severity="low",
        typical_symptoms=[
            "blurry or hazy image that doesn't improve with cleaning",
            "part of the image is blocked or dark",
            "image has a foggy or cloudy appearance",
            "[image] visible scratch or crack on the lens glass",
            "[image] condensation or moisture inside the lens cover",
            "[image] spider web or dirt covering part of the lens",
        ],
        typical_cost_min=400, typical_cost_max=1200,
    ),
    FaultCreate(
        appliance_type="camera",
        name="Weather Seal Failure",
        description="The weatherproofing seal on an outdoor camera has failed, allowing moisture ingress.",
        severity="high",
        typical_symptoms=[
            "image gets foggy or shows moisture droplets after rain",
            "camera stops working after heavy rain or humidity",
            "[image] visible moisture or water droplets inside the camera housing",
            "[image] rust or corrosion on the camera body or mounting screws",
            "[image] cracked or deteriorated rubber gasket around the housing",
        ],
        typical_cost_min=800, typical_cost_max=2500,
    ),
    FaultCreate(
        appliance_type="camera",
        name="Mounting Damage",
        description="The camera mount or bracket is damaged, causing the camera to tilt, sag, or fall.",
        severity="low",
        typical_symptoms=[
            "camera has shifted angle on its own",
            "camera is sagging or tilted downward",
            "[image] cracked or broken mounting bracket",
            "[image] loose or missing mounting screws",
            "[image] wall damage around the mount point",
        ],
        typical_cost_min=200, typical_cost_max=700,
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