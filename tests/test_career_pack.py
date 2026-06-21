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
    "company-enrich",
    "cv-tailor",
    "cover-letter",
    "interview-prep",
    "fit-analysis",
    "email-analyser",
    "sms-analyser",
    "network-scan",
    "apply-prep",
    "content-library",
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


from app import capabilities as caps  # noqa: E402
from app.agent import runner  # noqa: E402
from app.agent.tools import ALL_TOOL_NAMES  # noqa: E402
from app.config import get_config  # noqa: E402


def test_build_options_enables_both_packs(tmp_path):
    opts = runner.build_options(model=None, cwd=tmp_path, api_key=None)
    cfg = get_config()
    assert cfg.career_pack_dir.is_absolute()
    assert cfg.business_pack_dir.is_absolute()
    assert opts.plugins == [
        {"type": "local", "path": str(cfg.career_pack_dir)},
        {"type": "local", "path": str(cfg.business_pack_dir)},
    ]
    assert opts.skills == caps.SKILL_NAMES
    assert len(opts.skills) == 16
    for name in ("Skill", "WebSearch", "WebFetch"):
        assert name in opts.allowed_tools
    assert all(t in opts.allowed_tools for t in ALL_TOOL_NAMES)
    # both plugin paths must point at real packs (not depend on cwd)
    assert (cfg.career_pack_dir / ".claude-plugin" / "plugin.json").exists()
    assert (cfg.business_pack_dir / ".claude-plugin" / "plugin.json").exists()


async def test_gate_allows_skill_tools_denies_others():
    for allowed in ("Skill", "WebSearch", "WebFetch"):
        assert (await runner._gate(allowed, {}, None)).behavior == "allow"
    for forbidden in ("Bash", "Write", "Edit", "Read", "mcp__app__delete_everything"):
        assert (await runner._gate(forbidden, {}, None)).behavior == "deny"
