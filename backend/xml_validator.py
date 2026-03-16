"""
ZWO XML validation and cleanup.
Extracted from skywalker_dashboard.py – logic unchanged.
"""
import re
import xml.etree.ElementTree as ET


def validate_zwo(xml_string: str) -> tuple[bool, str, str]:
    """
    Validate and clean a Zwift workout XML string.

    Returns:
        (is_valid: bool, message: str, clean_xml: str)
    """
    if not xml_string or not xml_string.strip():
        return False, "Empty XML string.", ""

    # Extract XML block if wrapped in markdown fences
    match = re.search(r"```(?:xml)?\s*([\s\S]*?)```", xml_string)
    if match:
        xml_string = match.group(1).strip()

    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError as e:
        return False, f"XML parse error: {e}", xml_string

    # Check root tag
    if root.tag != "workout_file":
        return False, f"Root tag must be <workout_file>, got <{root.tag}>.", xml_string

    workout = root.find("workout")
    if workout is None:
        return False, "Missing <workout> element.", xml_string

    # Fix empty IntervalsT Repeat attributes
    for el in workout.findall(".//IntervalsT"):
        repeat = el.get("Repeat", "")
        if not repeat or repeat.strip() == "":
            el.set("Repeat", "6")

    # Rebuild clean XML
    ET.indent(root, space="  ")
    clean = ET.tostring(root, encoding="unicode", xml_declaration=False)

    # Require at least one workout block
    blocks = list(workout)
    if len(blocks) == 0:
        return False, "Workout has no exercise blocks.", clean

    return True, "Valid Zwift workout.", clean


def extract_xml_from_response(text: str) -> str | None:
    """Pull XML block out of Claude's response text."""
    patterns = [
        r"```xml\s*([\s\S]*?)```",
        r"```\s*(<workout_file[\s\S]*?</workout_file>)\s*```",
        r"(<workout_file[\s\S]*?</workout_file>)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1).strip()
    return None
