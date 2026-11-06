"""Checks for the OpenCode project config: opencode.json and the skills OpenCode loads."""

import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILLS = REPO / ".opencode" / "skills"


def frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "---", f"{path} must start with a --- frontmatter block"
    end = lines.index("---", 1)
    return dict(line.split(":", 1) for line in lines[1:end] if ":" in line)


class OpenCodeConfigTest(unittest.TestCase):
    def test_config_is_json_with_browser_server(self):
        config = json.loads((REPO / "opencode.json").read_text(encoding="utf-8"))
        browser = config["mcp"]["playwright"]
        self.assertEqual(browser["type"], "local")
        self.assertIn("--headless", browser["command"])

    def test_nvidia_models_are_listed_and_shown(self):
        config = json.loads((REPO / "opencode.json").read_text(encoding="utf-8"))
        nvidia = config["provider"]["nvidia"]
        self.assertEqual(nvidia["options"]["baseURL"], "https://integrate.api.nvidia.com/v1")
        self.assertEqual(nvidia["options"]["apiKey"], "{env:NVIDIA_API_KEY}")
        # Every whitelisted model has a name and limits, so it shows up even without models.dev
        self.assertEqual(sorted(nvidia["whitelist"]), sorted(nvidia["models"]))
        for model in nvidia["models"].values():
            self.assertTrue(model["name"])
            self.assertGreater(model["limit"]["context"], model["limit"]["output"])

    def test_skills_follow_opencode_naming_rules(self):
        skills = sorted(p for p in SKILLS.iterdir() if p.is_dir())
        self.assertTrue(skills)
        for skill in skills:
            meta = {k.strip(): v.strip() for k, v in frontmatter(skill / "SKILL.md").items()}
            # OpenCode only loads a skill whose name matches its folder and this pattern.
            self.assertEqual(meta.get("name"), skill.name)
            self.assertRegex(skill.name, r"^[a-z0-9]+(-[a-z0-9]+)*$")
            self.assertLessEqual(len(skill.name), 64)
            self.assertTrue(meta.get("description"), f"{skill.name} needs a description")


if __name__ == "__main__":
    unittest.main()
