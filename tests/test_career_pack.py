"""Static validity of the career-pack plugin + the runner seam config.

A renamed/missing skill must fail loudly here — the SDK would otherwise just
discover zero skills and the agent would silently improvise.
"""

from __future__ import annotations

import json
from pathlib import Path

PACK_DIR = Path(__file__).resolve().parent.parent / "skills" / "career-pack"
EXPECTED_SKILLS = {
    "enrich-opportunity",
    "company-research",
    "cv-tailor",
    "interview-prep",
    "fit-analysis",
}


def test_plugin_manifest_parses():
    manifest = json.loads((PACK_DIR / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "career-pack"
    assert manifest["description"]


def test_exactly_the_expected_skills_exist():
    found = {p.name for p in (PACK_DIR / "skills").iterdir() if p.is_dir()}
    assert found == EXPECTED_SKILLS


def _frontmatter(skill_dir: Path) -> dict[str, str]:
    text = (skill_dir / "SKILL.md").read_text()
    assert text.startswith("---\n"), f"{skill_dir.name}: missing frontmatter"
    block = text.split("---", 2)[1]
    return {
        k.strip(): v.strip()
        for k, v in (line.split(":", 1) for line in block.strip().splitlines() if ":" in line)
    }


def test_skill_frontmatter_matches_directory():
    for skill_dir in sorted((PACK_DIR / "skills").iterdir()):
        meta = _frontmatter(skill_dir)
        assert meta["name"] == skill_dir.name
        assert meta["description"], f"{skill_dir.name}: empty description"


def test_every_skill_declares_a_write_back_contract():
    for skill_dir in sorted((PACK_DIR / "skills").iterdir()):
        body = (skill_dir / "SKILL.md").read_text()
        assert "## Write-back contract" in body, skill_dir.name
        assert "mcp__app__" in body, skill_dir.name
