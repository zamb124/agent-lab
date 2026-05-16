"""
Inline Python evaluation package.

Import concrete APIs from their modules (`compiler`, `safe_eval`, `state_utils`,
`wrappers`). The package initializer intentionally has no eager re-exports: the
runner stack imports compiler/namespace during initialization, and a barrel here
creates real cycles.
"""

__all__: list[str] = []
