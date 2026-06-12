"""Opt-in runtime profiling for pytest (event loop + FileLock waits).

Enable: PLATFORM_TEST_PROFILE_RUNTIME=1 pytest ...
Report: platform_test_runtime_profile.json (per xdist worker + merged summary on controller).
"""
