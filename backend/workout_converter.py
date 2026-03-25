"""
Convert Skywalker ZWO workouts to Garmin TCX and Wahoo ERG formats.

- TCX: importable into Garmin Connect (Web) → syncs to Garmin Edge
- ERG: simple text format, works with Wahoo ELEMNT + most trainers
- Note: Wahoo ELEMNT also supports .zwo directly!
"""
import xml.etree.ElementTree as ET
from xml.dom import minidom
import re


def _parse_zwo(zwo_xml: str) -> dict:
    """Parse ZWO XML into a structured dict."""
    root = ET.fromstring(zwo_xml)
    name = root.findtext("name") or "Skywalker Workout"
    description = root.findtext("description") or ""
    steps = []

    workout = root.find("workout")
    if workout is None:
        return {"name": name, "description": description, "steps": steps}

    for elem in workout:
        tag = elem.tag
        if tag == "Warmup":
            steps.append({
                "type": "warmup",
                "duration": int(elem.get("Duration", 480)),
                "power_low": float(elem.get("PowerLow", 0.25)),
                "power_high": float(elem.get("PowerHigh", 0.75)),
            })
        elif tag == "Cooldown":
            steps.append({
                "type": "cooldown",
                "duration": int(elem.get("Duration", 480)),
                "power_low": float(elem.get("PowerLow", 0.55)),
                "power_high": float(elem.get("PowerHigh", 0.25)),
            })
        elif tag == "SteadyState":
            steps.append({
                "type": "steady",
                "duration": int(elem.get("Duration", 1800)),
                "power": float(elem.get("Power", 0.65)),
            })
        elif tag == "IntervalsT":
            repeat = int(elem.get("Repeat", 1))
            on_dur = int(elem.get("OnDuration", 30))
            off_dur = int(elem.get("OffDuration", 30))
            on_pwr = float(elem.get("OnPower", 1.0))
            off_pwr = float(elem.get("OffPower", 0.5))
            for _ in range(repeat):
                steps.append({"type": "steady", "duration": on_dur, "power": on_pwr})
                steps.append({"type": "steady", "duration": off_dur, "power": off_pwr})

    return {"name": name, "description": description, "steps": steps}


def zwo_to_erg(zwo_xml: str, ftp: int = 230) -> str:
    """Convert ZWO to ERG format (watts). Works with Wahoo ELEMNT + TrainerRoad."""
    parsed = _parse_zwo(zwo_xml)
    lines = [
        "[COURSE HEADER]",
        f"DESCRIPTION = {parsed['name']}",
        f"FILE NAME = {parsed['name'].replace(' ', '_')}.erg",
        "MINUTES WATTS",
        "[END COURSE HEADER]",
        "[COURSE DATA]",
    ]

    current_min = 0.0
    for step in parsed["steps"]:
        dur_min = step["duration"] / 60.0
        if step["type"] == "warmup":
            # Ramp from power_low to power_high
            w_start = round(step["power_low"] * ftp)
            w_end = round(step["power_high"] * ftp)
            lines.append(f"{current_min:.2f}\t{w_start}")
            current_min += dur_min
            lines.append(f"{current_min:.2f}\t{w_end}")
        elif step["type"] == "cooldown":
            w_start = round(step["power_low"] * ftp)
            w_end = round(step["power_high"] * ftp)
            lines.append(f"{current_min:.2f}\t{w_start}")
            current_min += dur_min
            lines.append(f"{current_min:.2f}\t{w_end}")
        else:
            w = round(step["power"] * ftp)
            lines.append(f"{current_min:.2f}\t{w}")
            current_min += dur_min
            lines.append(f"{current_min:.2f}\t{w}")

    lines.append("[END COURSE DATA]")
    return "\n".join(lines)


def zwo_to_tcx(zwo_xml: str, ftp: int = 230) -> str:
    """Convert ZWO to Garmin TCX workout format (importable into Garmin Connect)."""
    parsed = _parse_zwo(zwo_xml)

    root = ET.Element("TrainingCenterDatabase")
    root.set("xmlns", "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.set("xsi:schemaLocation",
             "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2 "
             "http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd")

    workouts = ET.SubElement(root, "Workouts")
    workout = ET.SubElement(workouts, "Workout")
    workout.set("Sport", "Biking")

    ET.SubElement(workout, "Name").text = parsed["name"]

    step_id = 1
    for step in parsed["steps"]:
        s = ET.SubElement(workout, "Step")
        s.set("xsi:type", "Step_t")
        ET.SubElement(s, "StepId").text = str(step_id)
        step_id += 1

        if step["type"] == "warmup":
            ET.SubElement(s, "Name").text = "Warmup"
            dur = ET.SubElement(s, "Duration")
            dur.set("xsi:type", "Time_t")
            ET.SubElement(dur, "Seconds").text = str(step["duration"])
            ET.SubElement(s, "Intensity").text = "Warmup"
            target = ET.SubElement(s, "Target")
            target.set("xsi:type", "Power_t")
            zone = ET.SubElement(target, "CustomPowerZone")
            ET.SubElement(zone, "Low").text = str(round(step["power_low"] * ftp))
            ET.SubElement(zone, "High").text = str(round(step["power_high"] * ftp))

        elif step["type"] == "cooldown":
            ET.SubElement(s, "Name").text = "Cooldown"
            dur = ET.SubElement(s, "Duration")
            dur.set("xsi:type", "Time_t")
            ET.SubElement(dur, "Seconds").text = str(step["duration"])
            ET.SubElement(s, "Intensity").text = "Cooldown"
            target = ET.SubElement(s, "Target")
            target.set("xsi:type", "Power_t")
            zone = ET.SubElement(target, "CustomPowerZone")
            lo = min(step["power_low"], step["power_high"])
            hi = max(step["power_low"], step["power_high"])
            ET.SubElement(zone, "Low").text = str(round(lo * ftp))
            ET.SubElement(zone, "High").text = str(round(hi * ftp))

        else:  # steady
            w = round(step["power"] * ftp)
            label = "High Intensity" if step["power"] > 1.0 else (
                "Sweet Spot" if step["power"] >= 0.88 else "Zone 2"
            )
            ET.SubElement(s, "Name").text = label
            dur = ET.SubElement(s, "Duration")
            dur.set("xsi:type", "Time_t")
            ET.SubElement(dur, "Seconds").text = str(step["duration"])
            ET.SubElement(s, "Intensity").text = "Active" if step["power"] >= 0.56 else "Resting"
            target = ET.SubElement(s, "Target")
            target.set("xsi:type", "Power_t")
            zone = ET.SubElement(target, "CustomPowerZone")
            ET.SubElement(zone, "Low").text = str(round(w * 0.97))
            ET.SubElement(zone, "High").text = str(round(w * 1.03))

    # Pretty print
    raw = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ")
    # Remove extra XML declaration added by minidom
    lines = pretty.split("\n")
    if lines[0].startswith("<?xml"):
        lines[0] = '<?xml version="1.0" encoding="UTF-8"?>'
    return "\n".join(lines)


def zwo_to_workout_card(zwo_xml: str, ftp: int = 230) -> str:
    """Generate a human-readable workout card for outdoor use (phone/printout)."""
    parsed = _parse_zwo(zwo_xml)
    total_sec = sum(s["duration"] for s in parsed["steps"])
    total_min = total_sec // 60

    lines = [
        f"{'='*50}",
        f"  {parsed['name'].upper()}",
        f"  Skywalker Coach | FTP: {ftp}W | {total_min} min",
        f"{'='*50}",
        "",
    ]

    if parsed["description"]:
        lines.append(f"  {parsed['description']}")
        lines.append("")

    lines.append("INTERVALLE:")
    lines.append("-" * 50)

    elapsed = 0
    for i, step in enumerate(parsed["steps"], 1):
        dur = step["duration"]
        m, s = divmod(dur, 60)
        dur_str = f"{m}:{s:02d}" if s else f"{m} min"
        start_min = elapsed // 60

        if step["type"] == "warmup":
            w1 = round(step["power_low"] * ftp)
            w2 = round(step["power_high"] * ftp)
            lines.append(f"  {i:2}. ▲ WARMUP     {dur_str:>8}  |  {w1}W → {w2}W  [{start_min} min]")
        elif step["type"] == "cooldown":
            w1 = round(step["power_low"] * ftp)
            w2 = round(step["power_high"] * ftp)
            lines.append(f"  {i:2}. ▼ COOLDOWN   {dur_str:>8}  |  {w1}W → {w2}W  [{start_min} min]")
        else:
            w = round(step["power"] * ftp)
            pct = round(step["power"] * 100)
            zone = "🔴 HIT" if step["power"] > 1.0 else (
                "🟡 SS" if step["power"] >= 0.88 else (
                "🟢 Z2" if step["power"] >= 0.56 else "⚪ Z1"
            ))
            lines.append(f"  {i:2}. {zone}        {dur_str:>8}  |  {w}W  ({pct}%)  [{start_min} min]")

        elapsed += dur

    lines += [
        "-" * 50,
        f"  GESAMT: {total_min} min",
        "",
        "  Legende: ⚪Z1 <56%  🟢Z2 56-87%  🟡SS 88-94%  🔴HIT >100%",
        f"{'='*50}",
    ]
    return "\n".join(lines)
