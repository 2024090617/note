"""Tests for skills/loader.py."""

from digimate.skills.loader import discover_skills, render_skills_block, Skill


def test_discover_no_skills(tmp_path):
    skills = discover_skills(str(tmp_path))
    assert skills == []


def test_discover_project_skills(tmp_path):
    skills_dir = tmp_path / ".digimate" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "testing.md").write_text("---\ndescription: Testing utilities\n---\n\nSkill content.")
    skills = discover_skills(str(tmp_path))
    assert len(skills) == 1
    assert skills[0].name == "testing"
    assert "Testing utilities" in skills[0].description


def test_skill_load(tmp_path):
    skills_dir = tmp_path / ".digimate" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "myskill.md").write_text("# My Skill\nInstructions here.")
    skills = discover_skills(str(tmp_path))
    content = skills[0].load()
    assert "Instructions here" in content


def test_render_skills_block():
    skills = [Skill(name="test", description="A test skill", path=None, source="project")]
    block = render_skills_block(skills)
    assert "<available_skills>" in block
    assert "test" in block


def test_render_skills_block_empty():
    assert render_skills_block([]) == ""
