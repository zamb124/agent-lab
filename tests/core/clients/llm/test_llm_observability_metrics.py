from core.clients.llm.logging import compute_llm_output_tokens_per_second


def test_compute_llm_output_tokens_per_second_uses_generation_phase() -> None:
    tps = compute_llm_output_tokens_per_second(
        output_tokens=100,
        duration_ms=5000.0,
        ttft_ms=1000.0,
    )
    assert tps == 25.0


def test_compute_llm_output_tokens_per_second_zero_output() -> None:
    tps = compute_llm_output_tokens_per_second(
        output_tokens=0,
        duration_ms=5000.0,
        ttft_ms=1000.0,
    )
    assert tps == 0.0
