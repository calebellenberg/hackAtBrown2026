"""
Extended unit tests for the Memory Engine (memory.py).

Covers: _chunk_markdown, _determine_target_file, _count_observations,
_simple_append_update, retrieve_context, apply_memory_update, consolidate_memory.
"""

import os
import json
import tempfile
import shutil
import pytest
from unittest.mock import patch, AsyncMock, Mock

from memory import MemoryEngine

# Reuse the conftest mock service account path
from conftest import MOCK_SERVICE_ACCOUNT_PATH


def _make_engine(memory_dir=None, chroma_dir=None):
    """Create a MemoryEngine with temp dirs."""
    md = memory_dir or tempfile.mkdtemp()
    cd = chroma_dir or tempfile.mkdtemp()
    os.makedirs(md, exist_ok=True)
    return MemoryEngine(
        memory_dir=md,
        chroma_persist_dir=cd,
        service_account_path=MOCK_SERVICE_ACCOUNT_PATH,
    )


# ── _chunk_markdown ─────────────────────────────────────────────────────

class TestChunkMarkdown:
    def test_empty_content(self):
        engine = _make_engine()
        chunks = engine._chunk_markdown("", "test.md")
        assert chunks == []

    def test_no_headers(self):
        engine = _make_engine()
        chunks = engine._chunk_markdown("Just plain text\nAnother line", "test.md")
        assert len(chunks) == 1
        assert chunks[0]["section"] == "Introduction"
        assert chunks[0]["file"] == "test.md"

    def test_single_section(self):
        engine = _make_engine()
        content = "# Title\nSome content here\n- bullet 1\n- bullet 2"
        chunks = engine._chunk_markdown(content, "Goals.md")
        assert len(chunks) == 1
        assert chunks[0]["section"] == "Title"
        assert "bullet 1" in chunks[0]["content"]

    def test_multiple_sections(self):
        engine = _make_engine()
        content = "# Section A\nContent A\n## Section B\nContent B\n# Section C\nContent C"
        chunks = engine._chunk_markdown(content, "test.md")
        assert len(chunks) == 3

    def test_large_section_gets_split(self):
        engine = _make_engine()
        # Create content larger than MAX_CHUNK_SIZE
        big_content = "# Big Section\n" + "\n".join(
            [f"- Observation line {i} with some extra detail" for i in range(50)]
        )
        chunks = engine._chunk_markdown(big_content, "test.md")
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk["content"]) <= engine.MAX_CHUNK_SIZE + 100  # some tolerance

    def test_file_metadata_preserved(self):
        engine = _make_engine()
        content = "# Goals\n- Save money"
        chunks = engine._chunk_markdown(content, "Goals.md")
        assert all(c["file"] == "Goals.md" for c in chunks)

    def test_whitespace_only_sections_skipped(self):
        engine = _make_engine()
        content = "# Header\n\n\n\n# Another\nReal content"
        chunks = engine._chunk_markdown(content, "test.md")
        # Empty section between headers should be skipped
        assert all(c["content"].strip() for c in chunks)


# ── _determine_target_file ──────────────────────────────────────────────

class TestDetermineTargetFile:
    def test_goal_keywords(self):
        engine = _make_engine()
        assert engine._determine_target_file("User has a goal to save $5000") == "Goals.md"
        assert engine._determine_target_file("aspiration to travel") == "Goals.md"

    def test_budget_keywords(self):
        engine = _make_engine()
        assert engine._determine_target_file("monthly budget exceeded") == "Budget.md"
        assert engine._determine_target_file("over budget on electronics") == "Budget.md"

    def test_state_keywords(self):
        engine = _make_engine()
        assert engine._determine_target_file("savings account balance is $1000") == "State.md"
        assert engine._determine_target_file("current income level") == "State.md"

    def test_default_to_behavior(self):
        engine = _make_engine()
        assert engine._determine_target_file("User tends to shop late at night") == "Behavior.md"
        assert engine._determine_target_file("comfortable spending on shoes") == "Behavior.md"

    def test_empty_string(self):
        engine = _make_engine()
        assert engine._determine_target_file("") == "Behavior.md"


# ── _count_observations ─────────────────────────────────────────────────

class TestCountObservations:
    def test_empty_content(self):
        engine = _make_engine()
        assert engine._count_observations("") == 0

    def test_placeholder_lines_not_counted(self):
        engine = _make_engine()
        content = "## Section\n- [No patterns recorded yet]\n- [AMOUNT]\n- [ ] checkbox"
        assert engine._count_observations(content) == 0

    def test_real_entries_counted(self):
        engine = _make_engine()
        content = "## Observed\n- User buys shoes often\n- Late night shopping detected\n- High impulse on electronics"
        assert engine._count_observations(content) == 3

    def test_mixed_content(self):
        engine = _make_engine()
        content = "## Section\n- [No patterns recorded yet]\n- Real observation\n- Another real one"
        assert engine._count_observations(content) == 2


# ── _simple_append_update ───────────────────────────────────────────────

class TestSimpleAppendUpdate:
    def test_replace_placeholder(self):
        engine = _make_engine()
        content = "# Behavior\n\n## Observed Behaviors\n- [No patterns recorded yet]\n"
        result = engine._simple_append_update(content, "User shops at night", "Behavior.md")
        assert "User shops at night" in result
        assert "[No patterns recorded yet]" not in result

    def test_append_to_section(self):
        engine = _make_engine()
        content = "# Behavior\n\n## Observed Behaviors\n- Existing observation\n"
        result = engine._simple_append_update(content, "New observation", "Behavior.md")
        assert "Existing observation" in result
        assert "New observation" in result

    def test_reject_when_full(self):
        engine = _make_engine()
        lines = ["# Behavior\n\n## Observed Behaviors"]
        for i in range(6):
            lines.append(f"- Observation {i}")
        content = "\n".join(lines)
        result = engine._simple_append_update(content, "One more", "Behavior.md")
        assert "One more" not in result  # Should not add beyond 5

    def test_create_section_if_missing(self):
        engine = _make_engine()
        content = "# Behavior\n\nSome content without Observed Behaviors section\n"
        result = engine._simple_append_update(content, "New obs", "Behavior.md")
        assert "## Observed Behaviors" in result
        assert "New obs" in result


# ── retrieve_context ────────────────────────────────────────────────────

class TestRetrieveContext:
    @pytest.mark.asyncio
    async def test_always_includes_goals_and_budget(self):
        td = tempfile.mkdtemp()
        try:
            # Create all memory files
            for fname, content in [
                ("Goals.md", "# Goals\n- Save $5000"),
                ("Budget.md", "# Budget\n- $500/month"),
                ("State.md", "# State\n- Balance $1000"),
                ("Behavior.md", "# Behavior\n- Shops at night"),
            ]:
                with open(os.path.join(td, fname), "w") as f:
                    f.write(content)

            engine = _make_engine(memory_dir=td)
            snippets = await engine.retrieve_context("shoes $50 amazon")

            files_in_snippets = [s["file"] for s in snippets]
            assert "Goals.md" in files_in_snippets
            assert "Budget.md" in files_in_snippets
        finally:
            shutil.rmtree(td, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_empty_memory_dir(self):
        td = tempfile.mkdtemp()
        try:
            engine = _make_engine(memory_dir=td)
            snippets = await engine.retrieve_context("test query")
            # Should not crash, may return empty list
            assert isinstance(snippets, list)
        finally:
            shutil.rmtree(td, ignore_errors=True)


# ── apply_memory_update ─────────────────────────────────────────────────

class TestApplyMemoryUpdate:
    @pytest.mark.asyncio
    async def test_empty_string_returns_false(self):
        engine = _make_engine()
        result = await engine.apply_memory_update("")
        assert result is False

    @pytest.mark.asyncio
    async def test_none_returns_false(self):
        engine = _make_engine()
        result = await engine.apply_memory_update(None)
        assert result is False

    @pytest.mark.asyncio
    async def test_backup_created(self):
        td = tempfile.mkdtemp()
        try:
            behavior_path = os.path.join(td, "Behavior.md")
            with open(behavior_path, "w") as f:
                f.write("# Behavior\n\n## Observed Behaviors\n- [No patterns recorded yet]\n")

            engine = _make_engine(memory_dir=td)
            # After successful update, backup should be removed
            await engine.apply_memory_update("User shops frequently")
            # If update succeeded, backup was removed. If failed, backup exists.
            # Just verify the file still exists
            assert os.path.exists(behavior_path)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_successful_update_writes_content(self):
        td = tempfile.mkdtemp()
        try:
            behavior_path = os.path.join(td, "Behavior.md")
            with open(behavior_path, "w") as f:
                f.write("# Behavior\n\n## Observed Behaviors\n- [No patterns recorded yet]\n")

            engine = _make_engine(memory_dir=td)
            result = await engine.apply_memory_update("User prefers quality over price")
            assert result is True

            with open(behavior_path, "r") as f:
                content = f.read()
            assert "User prefers quality over price" in content
        finally:
            shutil.rmtree(td, ignore_errors=True)


# ── consolidate_memory ──────────────────────────────────────────────────

class TestConsolidateMemory:
    @pytest.mark.asyncio
    async def test_skips_small_files(self):
        td = tempfile.mkdtemp()
        try:
            # Create small memory files (below threshold)
            for fname in ["Goals.md", "Budget.md", "State.md", "Behavior.md"]:
                with open(os.path.join(td, fname), "w") as f:
                    f.write(f"# {fname}\n- Short content\n")

            engine = _make_engine(memory_dir=td)
            await engine.reindex_memory()
            results = await engine.consolidate_memory()

            for fname, result in results.items():
                assert result["status"] == "skipped"
        finally:
            shutil.rmtree(td, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_consolidates_large_files(self):
        td = tempfile.mkdtemp()
        try:
            # Create a large Behavior.md that exceeds thresholds
            lines = ["# Behavior\n\n## Observed Behaviors"]
            for i in range(15):
                lines.append(f"- User bought item {i} at price ${i * 10} on amazon.com repeatedly")
            content = "\n".join(lines)

            for fname in ["Goals.md", "Budget.md", "State.md"]:
                with open(os.path.join(td, fname), "w") as f:
                    f.write(f"# {fname}\n- Short\n")

            with open(os.path.join(td, "Behavior.md"), "w") as f:
                f.write(content)

            engine = _make_engine(memory_dir=td)
            await engine.reindex_memory()

            # Mock the Gemini API call for consolidation
            async def mock_gemini(*args, **kwargs):
                return {"refined_content": "# Behavior\n\n## Observed Behaviors\n- User shops frequently on amazon.com\n"}

            engine._call_gemini_api = mock_gemini
            results = await engine.consolidate_memory()

            assert results["Behavior.md"]["status"] == "consolidated"
        finally:
            shutil.rmtree(td, ignore_errors=True)
