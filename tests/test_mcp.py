import asyncio
import datetime
import json
import os
import platform
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.parametrize("backend", [None, "cuda", "rocm"])
def test_real_stdio_status_and_input_rejection(tmp_path, backend):
    if backend:
        if (
            platform.system() == "Darwin"
            or (backend == "rocm" and platform.system() != "Linux")
            or platform.machine().lower() not in {"amd64", "x86_64"}
        ):
            pytest.skip("GPU backend is not supported on this platform")
        (tmp_path / "backend.json").write_text(json.dumps({"backend": backend}))

    async def probe():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-I", "-m", "agent_audio.mcp_server"],
            env={**os.environ, "AGENT_AUDIO_HOME": str(tmp_path)},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(
                read, write, read_timeout_seconds=datetime.timedelta(seconds=30)
            ) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert {t.name for t in tools.tools} == {
                    "audio_status",
                    "generate_audio",
                }
                status = await session.call_tool("audio_status", {})
                assert not status.isError
                if backend:
                    assert status.structuredContent["selected_backend"] == backend
                assert status.structuredContent["runtime_ready"] is False
                assert (
                    status.structuredContent["capabilities"]["negative_prompt"] is False
                )
                assert (
                    status.structuredContent["readiness"]["generation"] == "not_checked"
                )
                result = await session.call_tool(
                    "generate_audio", {"prompt": "test", "seconds": 0}
                )
                assert result.isError
                rejected = await session.call_tool(
                    "generate_audio",
                    {"prompt": "impact", "seconds": 3, "negative_prompt": "music"},
                )
                assert rejected.isError
                assert any(
                    "negative_prompt is unsupported" in getattr(block, "text", "")
                    for block in rejected.content
                )

    asyncio.run(probe())
