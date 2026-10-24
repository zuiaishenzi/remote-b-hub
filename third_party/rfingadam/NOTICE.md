# RFingAdam/mcp-blender

Upstream: https://github.com/RFingAdam/mcp-blender

Pinned commit: `efbafb6a9e019a03a5887ff943462715e0f386dc`

The `blender_mcp_addon` directory is the unmodified upstream addon source, distributed under **AGPL-3.0-or-later**, according to upstream LICENSE and pyproject.toml. Upstream README's MIT sentence contradicts those files; this integration follows LICENSE. The full license is in [LICENSE](LICENSE). Original README is retained in UPSTREAM_README.md for provenance, not as this application's instructions.

`windows-b/blender-tools.json` extracts upstream server.py's 218 tool descriptions and input schemas without changing their meaning. The complete source needed by the Blender-side integration is published in this repository, bundled in both EXEs, and included in exported addon ZIPs. `windows-b/blender_bridge.py` is the replacement transport and main-thread dispatch wrapper, licensed AGPL-3.0-or-later. `windows-b/blender_schema.py`, shared with the addon, is also AGPL-3.0-or-later. Modifications and sources remain available at https://github.com/zuiaishenzi/remote-b-hub .

The original upstream socket server and external MCP process are **not started**. The replacement listens only on 127.0.0.1, authenticates a separate local secret, bounds messages and journals requests/results. The B agent remains the authenticated NAS client; A does not contact Blender TCP ports across the network.

External AI backends, asset downloads, flight simulator pipelines and all 218 commands are not blanket-validated. They may require additional dependencies, account credentials, running services, Blender contexts and version-specific APIs. No external AI credentials or telemetry are configured by Remote B Hub.
