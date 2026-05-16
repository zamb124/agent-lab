"""
Builtin flow tools package.

Runtime registration uses `apps.flows.tools.builtin_specs.BUILTIN_TOOL_SPECS`
and imports concrete tool modules explicitly. The package initializer must stay
side-effect free: eager tool imports pull platform services and the flows
container into low-level eval imports.
"""

__all__: list[str] = []
