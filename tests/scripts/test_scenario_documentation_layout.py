from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_scenario_docs_quality import check_readme_quality
from scripts.docs_prepare import copy_scenario_images
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
            _ = (slug_dir / "README.en.md").write_text(markdown, encoding="utf-8")

            self.assertEqual(check_readme_quality(scenarios_root), [])

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

            errors = check_readme_quality(scenarios_root)

            self.assertTrue(any("legacy-каталог screenshots/ запрещён" in error for error in errors))
            self.assertTrue(any("должен лежать рядом с README.md" in error for error in errors))

    def test_docs_prepare_copies_images_next_to_generated_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "source" / "send-message"
            dst_dir = root / "build" / "send-message"
            src_dir.mkdir(parents=True)
            dst_dir.mkdir(parents=True)
            image = src_dir / "send-message--01-open-channel.png"
            _ = image.write_bytes(b"png")

            copy_scenario_images(src_dir, dst_dir)

            self.assertEqual((dst_dir / image.name).read_bytes(), b"png")
            self.assertFalse((dst_dir / "screenshots").exists())


if __name__ == "__main__":
    _ = unittest.main()
