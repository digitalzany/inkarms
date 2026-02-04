"""
Unit tests for the InkArms skills system.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from inkarms.skills import (
    FilesystemPermissions,
    Skill,
    SkillFrontmatter,
    SkillIndex,
    SkillIndexEntry,
    SkillManager,
    SkillMetadata,
    SkillNotFoundError,
    SkillParseError,
    SkillPermissions,
    SkillValidationError,
    parse_skill_directory,
    parse_skill_md,
    parse_skill_yaml,
    parse_yaml_frontmatter,
    validate_skill_directory,
)


# =============================================================================
# Model Tests
# =============================================================================


class TestSkillPermissions:
    """Tests for SkillPermissions model."""

    def test_default_permissions(self):
        """Test default permission values."""
        perms = SkillPermissions()
        assert perms.tools == []
        assert perms.network is False
        assert perms.filesystem.read == []
        assert perms.filesystem.write == []

    def test_default_readonly(self):
        """Test default readonly factory."""
        perms = SkillPermissions.default_readonly()
        assert perms.tools == ["file_read"]
        assert perms.network is False
        assert perms.filesystem.read == ["*"]
        assert perms.filesystem.write == []

    def test_custom_permissions(self):
        """Test custom permission values."""
        perms = SkillPermissions(
            tools=["bash", "file_read", "file_write"],
            network=True,
            filesystem=FilesystemPermissions(
                read=["*.py", "*.js"],
                write=["output/*.md"],
            ),
        )
        assert "bash" in perms.tools
        assert perms.network is True
        assert "*.py" in perms.filesystem.read
        assert "output/*.md" in perms.filesystem.write


class TestSkillMetadata:
    """Tests for SkillMetadata model."""

    def test_minimal_metadata(self):
        """Test metadata with only required fields."""
        meta = SkillMetadata(name="test-skill")
        assert meta.name == "test-skill"
        assert meta.version == "1.0.0"
        assert meta.description == ""
        assert meta.keywords == []

    def test_full_metadata(self):
        """Test metadata with all fields."""
        meta = SkillMetadata(
            name="security-scan",
            version="2.1.0",
            description="Scans code for security issues",
            keywords=["security", "vulnerability", "scan"],
            author="security-team",
            license="MIT",
            repository="https://github.com/org/security-scan",
            permissions=SkillPermissions(
                tools=["file_read"],
                network=False,
            ),
        )
        assert meta.name == "security-scan"
        assert meta.version == "2.1.0"
        assert "security" in meta.keywords
        assert meta.author == "security-team"
        assert meta.permissions.tools == ["file_read"]


class TestSkill:
    """Tests for Skill model."""

    def test_skill_properties(self):
        """Test skill property accessors."""
        skill = Skill(
            metadata=SkillMetadata(
                name="test-skill",
                keywords=["test", "example"],
                permissions=SkillPermissions(tools=["file_read"]),
            ),
            instructions="Do the thing.",
        )
        assert skill.name == "test-skill"
        assert skill.keywords == ["test", "example"]
        assert skill.permissions.tools == ["file_read"]

    def test_get_system_prompt_injection(self):
        """Test system prompt injection formatting."""
        skill = Skill(
            metadata=SkillMetadata(
                name="code-review",
                description="Reviews code for issues",
            ),
            instructions="## Instructions\n\n1. Review the code\n2. Find issues",
        )
        injection = skill.get_system_prompt_injection()
        assert "## Skill: code-review" in injection
        assert "Reviews code for issues" in injection
        assert "## Instructions" in injection


class TestSkillIndex:
    """Tests for SkillIndex model."""

    def test_empty_index(self):
        """Test empty index creation."""
        index = SkillIndex()
        assert index.version == "1.0.0"
        assert len(index.skills) == 0

    def test_add_skill(self):
        """Test adding skill to index."""
        index = SkillIndex()
        entry = SkillIndexEntry(
            name="test-skill",
            version="1.0.0",
            description="A test skill",
            keywords=["test"],
            path="/path/to/skill",
        )
        index.add_skill(entry)
        assert "test-skill" in index.skills
        assert index.skills["test-skill"].name == "test-skill"

    def test_remove_skill(self):
        """Test removing skill from index."""
        index = SkillIndex()
        entry = SkillIndexEntry(
            name="test-skill",
            keywords=["test"],
            path="/path/to/skill",
        )
        index.add_skill(entry)
        assert index.remove_skill("test-skill") is True
        assert "test-skill" not in index.skills
        assert index.remove_skill("nonexistent") is False

    def test_search_exact_name(self):
        """Test search with exact name match."""
        index = SkillIndex()
        index.add_skill(
            SkillIndexEntry(
                name="security-scan",
                description="Scans for security issues",
                keywords=["security", "vulnerability"],
                path="/path",
            )
        )
        index.add_skill(
            SkillIndexEntry(
                name="code-review",
                description="Reviews code",
                keywords=["review", "code"],
                path="/path",
            )
        )

        results = index.search("security-scan")
        assert len(results) > 0
        assert results[0].name == "security-scan"

    def test_search_keywords(self):
        """Test search by keyword."""
        index = SkillIndex()
        index.add_skill(
            SkillIndexEntry(
                name="security-scan",
                description="Scans for security issues",
                keywords=["security", "vulnerability", "audit"],
                path="/path",
            )
        )

        results = index.search("vulnerability")
        assert len(results) > 0
        assert results[0].name == "security-scan"

    def test_search_partial_match(self):
        """Test search with partial keyword match."""
        index = SkillIndex()
        index.add_skill(
            SkillIndexEntry(
                name="api-documentation",
                description="Generates API docs",
                keywords=["api", "documentation", "swagger"],
                path="/path",
            )
        )

        results = index.search("doc")
        assert len(results) > 0

    def test_search_max_results(self):
        """Test search respects max_results."""
        index = SkillIndex()
        for i in range(10):
            index.add_skill(
                SkillIndexEntry(
                    name=f"skill-{i}",
                    keywords=["common"],
                    path=f"/path/{i}",
                )
            )

        results = index.search("common", max_results=3)
        assert len(results) == 3


# =============================================================================
# Parser Tests
# =============================================================================


class TestYamlFrontmatter:
    """Tests for YAML frontmatter parsing."""

    def test_parse_valid_frontmatter(self):
        """Test parsing valid frontmatter."""
        content = """---
name: test-skill
description: A test skill
---

# Test Skill

Instructions here.
"""
        frontmatter, body = parse_yaml_frontmatter(content)
        assert frontmatter is not None
        assert frontmatter["name"] == "test-skill"
        assert frontmatter["description"] == "A test skill"
        assert "# Test Skill" in body

    def test_parse_no_frontmatter(self):
        """Test parsing content without frontmatter."""
        content = "# Just a header\n\nSome content."
        frontmatter, body = parse_yaml_frontmatter(content)
        assert frontmatter is None
        assert body == content

    def test_parse_unclosed_frontmatter(self):
        """Test handling unclosed frontmatter."""
        content = "---\nname: test\nNo closing delimiter"
        frontmatter, body = parse_yaml_frontmatter(content)
        assert frontmatter is None


class TestParseSkillMd:
    """Tests for SKILL.md parsing."""

    def test_parse_skill_md(self, sample_skill_md):
        """Test parsing a valid SKILL.md."""
        frontmatter, instructions = parse_skill_md(sample_skill_md)
        assert frontmatter is not None
        assert frontmatter.name == "test-skill"
        assert "# Test Skill" in instructions

    def test_parse_skill_md_no_frontmatter(self):
        """Test parsing SKILL.md without frontmatter."""
        content = "# Skill\n\nJust instructions."
        frontmatter, instructions = parse_skill_md(content)
        assert frontmatter is None
        assert "# Skill" in instructions

    def test_parse_skill_md_missing_name(self):
        """Test error when frontmatter missing name."""
        content = """---
description: Missing name field
---

Instructions.
"""
        with pytest.raises(SkillValidationError):
            parse_skill_md(content)


class TestParseSkillYaml:
    """Tests for skill.yaml parsing."""

    def test_parse_skill_yaml(self, sample_skill_yaml):
        """Test parsing a valid skill.yaml."""
        metadata = parse_skill_yaml(sample_skill_yaml)
        assert metadata.name == "test-skill"
        assert metadata.version == "1.0.0"
        assert "test" in metadata.keywords
        assert "file_read" in metadata.permissions.tools
        assert metadata.permissions.network is False

    def test_parse_skill_yaml_minimal(self):
        """Test parsing minimal skill.yaml."""
        content = "name: minimal-skill"
        metadata = parse_skill_yaml(content)
        assert metadata.name == "minimal-skill"
        assert metadata.version == "1.0.0"

    def test_parse_skill_yaml_missing_name(self):
        """Test error when name missing."""
        content = "version: 1.0.0"
        with pytest.raises(SkillValidationError):
            parse_skill_yaml(content)

    def test_parse_skill_yaml_invalid_yaml(self):
        """Test error on invalid YAML."""
        content = "name: test\ninvalid: [unclosed"
        with pytest.raises(SkillParseError):
            parse_skill_yaml(content)


class TestParseSkillDirectory:
    """Tests for skill directory parsing."""

    def test_parse_skill_directory(self, sample_skill_yaml, sample_skill_md):
        """Test parsing a valid skill directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "skill.yaml").write_text(sample_skill_yaml)
            (skill_dir / "SKILL.md").write_text(sample_skill_md)

            skill = parse_skill_directory(skill_dir)
            assert skill.name == "test-skill"
            # Compare resolved paths to handle macOS /var -> /private/var symlink
            assert skill.path.resolve() == skill_dir.resolve()
            assert "# Test Skill" in skill.instructions

    def test_parse_skill_directory_missing_yaml(self, sample_skill_md):
        """Test error when skill.yaml missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(sample_skill_md)

            with pytest.raises(SkillParseError, match="skill.yaml"):
                parse_skill_directory(skill_dir)

    def test_parse_skill_directory_missing_md(self, sample_skill_yaml):
        """Test error when SKILL.md missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "skill.yaml").write_text(sample_skill_yaml)

            with pytest.raises(SkillParseError, match="SKILL.md"):
                parse_skill_directory(skill_dir)

    def test_parse_skill_directory_name_mismatch(self):
        """Test error when names don't match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "skill.yaml").write_text("name: skill-one")
            (skill_dir / "SKILL.md").write_text("""---
name: skill-two
---
Instructions.
""")

            with pytest.raises(SkillValidationError, match="mismatch"):
                parse_skill_directory(skill_dir)


class TestValidateSkillDirectory:
    """Tests for skill directory validation."""

    def test_validate_valid_skill(self, sample_skill_yaml, sample_skill_md):
        """Test validating a valid skill."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "skill.yaml").write_text(sample_skill_yaml)
            (skill_dir / "SKILL.md").write_text(sample_skill_md)

            issues = validate_skill_directory(skill_dir)
            # Should only have warnings, no errors
            errors = [i for i in issues if not i.startswith("Warning:")]
            assert len(errors) == 0

    def test_validate_missing_directory(self):
        """Test validation of nonexistent directory."""
        issues = validate_skill_directory(Path("/nonexistent/path"))
        assert any("does not exist" in i for i in issues)

    def test_validate_empty_instructions(self, sample_skill_yaml):
        """Test validation catches empty instructions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "skill.yaml").write_text(sample_skill_yaml)
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
---

""")

            issues = validate_skill_directory(skill_dir)
            assert any("no instructions" in i.lower() for i in issues)


# =============================================================================
# Manager Tests
# =============================================================================


class TestSkillManager:
    """Tests for SkillManager."""

    def test_create_skill(self):
        """Test creating a new skill."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Patch the global skills dir
            import inkarms.skills.loader as loader_module

            original_func = loader_module.get_skills_dir

            def mock_get_skills_dir():
                return Path(tmpdir)

            loader_module.get_skills_dir = mock_get_skills_dir

            try:
                manager = SkillManager()
                skill_path = manager.create_skill(
                    "my-new-skill",
                    description="A brand new skill",
                    location="global",
                )

                assert skill_path.exists()
                assert (skill_path / "skill.yaml").exists()
                assert (skill_path / "SKILL.md").exists()

                # Verify content
                yaml_content = (skill_path / "skill.yaml").read_text()
                assert "my-new-skill" in yaml_content
                assert "A brand new skill" in yaml_content

            finally:
                loader_module.get_skills_dir = original_func

    def test_create_skill_already_exists(self):
        """Test error when creating skill that exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import inkarms.skills.loader as loader_module

            original_func = loader_module.get_skills_dir

            def mock_get_skills_dir():
                return Path(tmpdir)

            loader_module.get_skills_dir = mock_get_skills_dir

            try:
                manager = SkillManager()

                # Create first skill
                manager.create_skill("test-skill")

                # Try to create again
                with pytest.raises(ValueError, match="already exists"):
                    manager.create_skill("test-skill")

            finally:
                loader_module.get_skills_dir = original_func

    def test_list_skills(self, sample_skill_yaml, sample_skill_md):
        """Test listing installed skills."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import inkarms.skills.loader as loader_module

            original_func = loader_module.get_skills_dir

            def mock_get_skills_dir():
                return Path(tmpdir)

            loader_module.get_skills_dir = mock_get_skills_dir

            try:
                # Create a skill
                skill_dir = Path(tmpdir) / "test-skill"
                skill_dir.mkdir()
                (skill_dir / "skill.yaml").write_text(sample_skill_yaml)
                (skill_dir / "SKILL.md").write_text(sample_skill_md)

                manager = SkillManager()
                skills = manager.list_skills(include_project=False)

                assert len(skills) == 1
                assert skills[0].name == "test-skill"

            finally:
                loader_module.get_skills_dir = original_func

    def test_get_skill(self, sample_skill_yaml, sample_skill_md):
        """Test loading a skill by name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import inkarms.skills.loader as loader_module

            original_func = loader_module.get_skills_dir

            def mock_get_skills_dir():
                return Path(tmpdir)

            loader_module.get_skills_dir = mock_get_skills_dir

            try:
                # Create a skill
                skill_dir = Path(tmpdir) / "test-skill"
                skill_dir.mkdir()
                (skill_dir / "skill.yaml").write_text(sample_skill_yaml)
                (skill_dir / "SKILL.md").write_text(sample_skill_md)

                manager = SkillManager()
                skill = manager.get_skill("test-skill")

                assert skill.name == "test-skill"
                assert "# Test Skill" in skill.instructions

            finally:
                loader_module.get_skills_dir = original_func

    def test_get_skill_not_found(self):
        """Test error when skill not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import inkarms.skills.loader as loader_module

            original_func = loader_module.get_skills_dir

            def mock_get_skills_dir():
                return Path(tmpdir)

            loader_module.get_skills_dir = mock_get_skills_dir

            try:
                manager = SkillManager()
                with pytest.raises(SkillNotFoundError):
                    manager.get_skill("nonexistent-skill")

            finally:
                loader_module.get_skills_dir = original_func

    def test_search(self, sample_skill_yaml, sample_skill_md):
        """Test searching for skills."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import inkarms.skills.loader as loader_module
            import inkarms.skills.index as index_module

            original_skills_func = loader_module.get_skills_dir
            original_index_func = index_module.get_index_path

            def mock_get_skills_dir():
                return Path(tmpdir)

            def mock_get_index_path():
                return Path(tmpdir) / "index.json"

            loader_module.get_skills_dir = mock_get_skills_dir
            index_module.get_index_path = mock_get_index_path

            try:
                # Create a skill
                skill_dir = Path(tmpdir) / "test-skill"
                skill_dir.mkdir()
                (skill_dir / "skill.yaml").write_text(sample_skill_yaml)
                (skill_dir / "SKILL.md").write_text(sample_skill_md)

                manager = SkillManager()

                # Rebuild index first
                manager.reindex(include_project=False)

                # Search
                results = manager.search("test")
                assert len(results) > 0
                assert results[0].name == "test-skill"

            finally:
                loader_module.get_skills_dir = original_skills_func
                index_module.get_index_path = original_index_func

    def test_validate_skill(self, sample_skill_yaml, sample_skill_md):
        """Test validating a skill."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "skill.yaml").write_text(sample_skill_yaml)
            (skill_dir / "SKILL.md").write_text(sample_skill_md)

            manager = SkillManager()
            issues = manager.validate_skill(skill_dir)

            # Should have no errors (maybe warnings)
            errors = [i for i in issues if not i.startswith("Warning:")]
            assert len(errors) == 0

    def test_remove_skill(self, sample_skill_yaml, sample_skill_md):
        """Test removing a skill."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import inkarms.skills.loader as loader_module

            original_func = loader_module.get_skills_dir

            def mock_get_skills_dir():
                return Path(tmpdir)

            loader_module.get_skills_dir = mock_get_skills_dir

            try:
                # Create a skill
                skill_dir = Path(tmpdir) / "test-skill"
                skill_dir.mkdir()
                (skill_dir / "skill.yaml").write_text(sample_skill_yaml)
                (skill_dir / "SKILL.md").write_text(sample_skill_md)

                manager = SkillManager()
                assert manager.remove_skill("test-skill") is True
                assert not skill_dir.exists()

            finally:
                loader_module.get_skills_dir = original_func

    def test_install_skill(self, sample_skill_yaml, sample_skill_md):
        """Test installing a skill from local path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import inkarms.skills.loader as loader_module

            original_func = loader_module.get_skills_dir

            dest_dir = Path(tmpdir) / "dest"
            dest_dir.mkdir()

            def mock_get_skills_dir():
                return dest_dir

            loader_module.get_skills_dir = mock_get_skills_dir

            try:
                # Create source skill
                source_dir = Path(tmpdir) / "source" / "my-skill"
                source_dir.mkdir(parents=True)
                (source_dir / "skill.yaml").write_text(
                    sample_skill_yaml.replace("test-skill", "my-skill")
                )
                (source_dir / "SKILL.md").write_text(
                    sample_skill_md.replace("test-skill", "my-skill")
                )

                manager = SkillManager()
                installed_path = manager.install_skill(str(source_dir))

                assert installed_path.exists()
                assert installed_path == dest_dir / "my-skill"

            finally:
                loader_module.get_skills_dir = original_func


# =============================================================================
# Integration Tests
# =============================================================================


class TestSkillIntegration:
    """Integration tests for the skill system."""

    def test_full_workflow(self, sample_skill_yaml, sample_skill_md):
        """Test complete skill workflow: create, list, load, search, remove."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import inkarms.skills.loader as loader_module
            import inkarms.skills.index as index_module

            original_skills_func = loader_module.get_skills_dir
            original_index_func = index_module.get_index_path

            def mock_get_skills_dir():
                return Path(tmpdir)

            def mock_get_index_path():
                return Path(tmpdir) / "index.json"

            loader_module.get_skills_dir = mock_get_skills_dir
            index_module.get_index_path = mock_get_index_path

            try:
                manager = SkillManager()

                # Create a skill
                skill_path = manager.create_skill(
                    "workflow-skill",
                    description="Testing the workflow",
                )
                assert skill_path.exists()

                # List skills
                skills = manager.list_skills(include_project=False)
                assert len(skills) == 1

                # Reindex
                manager.reindex(include_project=False)

                # Search
                results = manager.search("workflow")
                assert len(results) > 0

                # Load the skill
                skill = manager.get_skill("workflow-skill")
                assert skill.name == "workflow-skill"

                # Get info
                info = manager.get_skill_info("workflow-skill")
                assert info["name"] == "workflow-skill"

                # Remove
                assert manager.remove_skill("workflow-skill") is True
                assert not skill_path.exists()

            finally:
                loader_module.get_skills_dir = original_skills_func
                index_module.get_index_path = original_index_func
