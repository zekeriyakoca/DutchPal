from typing import List


def map_to_joint_levels(cefr_level: str) -> List[str]:
    """
    Map CEFR levels to joint levels.
    """
    level_mapping = {
        "A1": ["A1", "A2"],
        "A2": ["A1", "A2", "B1"],
        "B1": ["A2", "B1", "B2"],
        "B2": ["B1", "B2", "C1"],
        "C1": ["B2", "C1", "C2"],
        "C2": ["C1", "C1", "C2"],
        "ALL LEVELS": ["ALL LEVELS"],
    }
    return level_mapping.get(cefr_level, ["ALL LEVELS"])
