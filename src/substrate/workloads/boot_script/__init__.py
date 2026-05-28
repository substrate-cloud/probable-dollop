"""Boot-script workload builder.

# API-OPEN-QUESTION (plan doc §11.1): the exact `launch_configuration` shape for
# non-Docker workloads is not yet documented by the Substrate MCP API. This
# module ships under the assumption:
#
#     launch_configuration: { type: "script", script_configuration: { script: "..." } }
#
# If the API confirms a different shape, only `models/launch_config.py` needs to
# change — the rest of this builder (which only produces a bash string) keeps
# working. See substrate.models.launch_config.ScriptConfiguration.
"""

from __future__ import annotations

from substrate.workloads.boot_script.builder import BootScript
from substrate.workloads.boot_script.workload import BootScriptWorkload

__all__ = ["BootScript", "BootScriptWorkload"]
