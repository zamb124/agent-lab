"""Обрезка сгенерированных token ids до eos и без хвостового pad для format_markdown."""

from __future__ import annotations

import torch

from apps.provider_litserve.markdown_format.engines import (
    markdown_trim_generated_token_ids,
    normalize_litserve_eos_token_id,
)


def test_markdown_trim_truncates_at_single_eos_id() -> None:
    row = torch.tensor([10, 20, 5, 99, 100])
    out = markdown_trim_generated_token_ids(row, eos_token_id=5, pad_token_id=0)
    assert out.tolist() == [10, 20]


def test_markdown_trim_truncates_at_first_matching_eos_in_list() -> None:
    row = torch.tensor([1, 7, 3])
    out = markdown_trim_generated_token_ids(row, eos_token_id=[5, 7, 9], pad_token_id=None)
    assert out.tolist() == [1]


def test_markdown_trim_strips_trailing_pad_without_eos() -> None:
    row = torch.tensor([3, 4, 0, 0])
    out = markdown_trim_generated_token_ids(row, eos_token_id=None, pad_token_id=0)
    assert out.tolist() == [3, 4]


def test_markdown_trim_eos_before_pad() -> None:
    row = torch.tensor([8, 9, 12, 0, 0])
    out = markdown_trim_generated_token_ids(row, eos_token_id=12, pad_token_id=0)
    assert out.tolist() == [8, 9]


def test_normalize_eos_single_element_tensor() -> None:
    t = torch.tensor([[151645]])
    assert normalize_litserve_eos_token_id(t) == 151645


def test_normalize_eos_multi_element_tuple() -> None:
    assert normalize_litserve_eos_token_id((11, 22)) == [11, 22]
