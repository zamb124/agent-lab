from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.docs.prepare import (
    _page_title,
    _render_pages_yaml,
    _titled_nav_link,
    copy_scenario_images,
)
from scripts.gates.repo.scenario_docs_quality import check_readme_quality
from tests.ui.scenario_doc import build_screenshot_filename, prepare_flat_screenshot_output


class ScenarioScreenshotNamingTest(unittest.TestCase):
    def test_explicit_name_gets_instruction_prefix_and_step_number(self) -> None:
        filename = build_screenshot_filename(
            "send-message-in-channel",
            4,
            "Проверьте сообщение",
            screenshot_name="message-visible-in-channel",
        )

        self.assertEqual(
            filename,
            "send-message-in-channel--04-message-visible-in-channel.png",
        )

    def test_english_label_is_used_as_automatic_fallback(self) -> None:
        filename = build_screenshot_filename(
            "send-message-in-channel",
            1,
            "Откройте нужный канал",
            label_en="Open the target channel",
        )

        self.assertEqual(
            filename,
            "send-message-in-channel--01-open-the-target-channel.png",
        )

    def test_russian_label_is_transliterated_as_automatic_fallback(self) -> None:
        filename = build_screenshot_filename(
            "send-message-in-channel",
            1,
            "Откройте нужный канал",
        )

        self.assertEqual(
            filename,
            "send-message-in-channel--01-otkroyte-nuzhnyy-kanal.png",
        )

    def test_prepare_removes_legacy_and_previous_generated_images_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "scenario"
            legacy_dir = out_dir / "screenshots"
            legacy_dir.mkdir(parents=True)
            _ = (legacy_dir / "001.png").write_bytes(b"legacy")
            _ = (out_dir / "send-message--01-old.png").write_bytes(b"old")
            preserved = out_dir / "manually-curated.png"
            _ = preserved.write_bytes(b"keep")

            result = prepare_flat_screenshot_output(out_dir, "send-message")

            self.assertEqual(result, out_dir)
            self.assertFalse(legacy_dir.exists())
            self.assertFalse((out_dir / "send-message--01-old.png").exists())
            self.assertTrue(preserved.is_file())


class ScenarioScreenshotLayoutTest(unittest.TestCase):
    def test_quality_gate_accepts_flat_named_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenarios_root = Path(tmp) / "scenarios"
            slug_dir = scenarios_root / "sync" / "chat" / "send-message"
            slug_dir.mkdir(parents=True)
            names = [
                "send-message--01-open-channel.png",
                "send-message--02-message-visible.png",
            ]
            for name in names:
                _ = (slug_dir / name).write_bytes(b"png")
            markdown = (
                "# Как отправить сообщение\n\n"
                "## Шаг 1. Откройте канал\n\n"
                f"![Канал]({names[0]})\n\n"
                "## Шаг 2. Проверьте сообщение\n\n"
                f"![Сообщение]({names[1]})\n"
            )
            _ = (slug_dir / "README.md").write_text(markdown, encoding="utf-8")
            _ = (slug_dir / "README.en.md").write_text(
                "# How to send a message\n\n"
                "## Step 1. Open the channel\n\n"
                f"![Channel]({names[0]})\n\n"
                "## Step 2. Verify the message\n\n"
                f"![Message]({names[1]})\n",
                encoding="utf-8",
            )

            errors, warnings = check_readme_quality(scenarios_root)
            self.assertEqual(errors, [])
            self.assertEqual(warnings, [])

    def test_quality_gate_rejects_legacy_subdirectory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenarios_root = Path(tmp) / "scenarios"
            slug_dir = scenarios_root / "sync" / "chat" / "send-message"
            legacy_dir = slug_dir / "screenshots"
            legacy_dir.mkdir(parents=True)
            _ = (legacy_dir / "001.png").write_bytes(b"png")
            markdown = (
                "# Как отправить сообщение\n\n"
                "## Шаг 1. Откройте канал\n\n"
                "![Канал](screenshots/001.png)\n\n"
                "## Шаг 2. Проверьте сообщение\n\n"
                "![Сообщение](screenshots/001.png)\n"
            )
            _ = (slug_dir / "README.md").write_text(markdown, encoding="utf-8")

            errors, _ = check_readme_quality(scenarios_root)

            self.assertTrue(any("legacy-каталог screenshots/ запрещён" in error for error in errors))
            self.assertTrue(any("должен лежать рядом с README.md" in error for error in errors))

    def test_docs_prepare_copies_images_next_to_generated_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "source" / "send-message"
            dst_dir = root / "build" / "platform"
            src_dir.mkdir(parents=True)
            dst_dir.mkdir(parents=True)
            image = src_dir / "send-message--01-open-channel.png"
            other = dst_dir / "other-slug--01-keep.png"
            stale = dst_dir / "send-message--99-old.png"
            _ = image.write_bytes(b"png")
            _ = other.write_bytes(b"keep")
            _ = stale.write_bytes(b"old")

            copy_scenario_images(src_dir, dst_dir, slug="send-message")

            self.assertEqual((dst_dir / image.name).read_bytes(), b"png")
            self.assertEqual(other.read_bytes(), b"keep")
            self.assertFalse(stale.exists())
            self.assertFalse((dst_dir / "screenshots").exists())


class ScenarioSidebarNavTest(unittest.TestCase):
    def test_pages_yaml_uses_titled_leaves_for_slug_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "platform-cron-field.md"
            _ = page.write_text('---\ntitle: "Cron Field"\n---\n\nbody\n', encoding="utf-8")

            self.assertEqual(_page_title(page), "Cron Field")
            rendered = _render_pages_yaml(
                [
                    "index.md",
                    (
                        "UI Kit",
                        [
                            "ui-kit/index.md",
                            _titled_nav_link(page, "platform-cron-field.md"),
                        ],
                    ),
                ]
            )

        self.assertIn("- ui-kit/index.md\n", rendered)
        self.assertIn('- "Cron Field": platform-cron-field.md\n', rendered)
        self.assertNotIn("platform-cron-field/index.md", rendered)


if __name__ == "__main__":
    _ = unittest.main()
