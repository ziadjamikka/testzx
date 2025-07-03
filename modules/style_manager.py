import json
import os
from typing import List, Dict, Any

class StyleManager:
    def __init__(self, json_path: str = 'config/textstyles/styles.json'):
        self.json_path = json_path
        self.data = self.load_data()

    def load_data(self) -> Dict[str, Any]:
        if not os.path.exists(self.json_path):
            return {"groups": [], "ungrouped": []}
        with open(self.json_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_data(self):
        with open(self.json_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)

    # --- Group Management ---
    def get_groups(self) -> List[Dict[str, Any]]:
        return self.data["groups"]

    def add_group(self, name: str):
        self.data["groups"].append({"name": name, "styles": []})
        self.save_data()

    def remove_group(self, group_index: int):
        if 0 <= group_index < len(self.data["groups"]):
            del self.data["groups"][group_index]
            self.save_data()

    def rename_group(self, group_index: int, new_name: str):
        if 0 <= group_index < len(self.data["groups"]):
            self.data["groups"][group_index]["name"] = new_name
            self.save_data()

    # --- Style Management ---
    def get_ungrouped_styles(self) -> List[Dict[str, Any]]:
        return self.data["ungrouped"]

    def add_ungrouped_style(self, style: Dict[str, Any]):
        self.data["ungrouped"].append(style)
        self.save_data()

    def update_ungrouped_style(self, index: int, new_style: Dict[str, Any]):
        if 0 <= index < len(self.data["ungrouped"]):
            self.data["ungrouped"][index] = new_style
            self.save_data()

    def delete_ungrouped_style(self, index: int):
        if 0 <= index < len(self.data["ungrouped"]):
            del self.data["ungrouped"][index]
            self.save_data()

    def get_group_styles(self, group_index: int) -> List[Dict[str, Any]]:
        if 0 <= group_index < len(self.data["groups"]):
            return self.data["groups"][group_index]["styles"]
        return []

    def add_style_to_group(self, group_index: int, style: Dict[str, Any]):
        if 0 <= group_index < len(self.data["groups"]):
            self.data["groups"][group_index]["styles"].append(style)
            self.save_data()

    def update_group_style(self, group_index: int, style_index: int, new_style: Dict[str, Any]):
        if 0 <= group_index < len(self.data["groups"]):
            styles = self.data["groups"][group_index]["styles"]
            if 0 <= style_index < len(styles):
                styles[style_index] = new_style
                self.save_data()

    def delete_group_style(self, group_index: int, style_index: int):
        if 0 <= group_index < len(self.data["groups"]):
            styles = self.data["groups"][group_index]["styles"]
            if 0 <= style_index < len(styles):
                del styles[style_index]
                self.save_data()

    def move_style(self, from_group: int, from_index: int, to_group: int = None):
        # Move style from one group to another or to ungrouped
        if from_group is None:
            # from ungrouped
            if 0 <= from_index < len(self.data["ungrouped"]):
                style = self.data["ungrouped"].pop(from_index)
                if to_group is not None and 0 <= to_group < len(self.data["groups"]):
                    self.data["groups"][to_group]["styles"].append(style)
                else:
                    self.data["ungrouped"].append(style)
                self.save_data()
        else:
            # from group
            if 0 <= from_group < len(self.data["groups"]):
                styles = self.data["groups"][from_group]["styles"]
                if 0 <= from_index < len(styles):
                    style = styles.pop(from_index)
                    if to_group is not None and 0 <= to_group < len(self.data["groups"]):
                        self.data["groups"][to_group]["styles"].append(style)
                    else:
                        self.data["ungrouped"].append(style)
                    self.save_data()

    # --- Compatibility for old code ---
    def get_styles(self) -> List[Dict[str, Any]]:
        # Return all styles (ungrouped + all groups) for compatibility
        all_styles = list(self.data["ungrouped"])
        for group in self.data["groups"]:
            all_styles.extend(group["styles"])
        return all_styles 