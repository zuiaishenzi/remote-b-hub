# Source and compatibility

Selected source: https://github.com/LTGOz/solidworks-agent-skill
Pinned revision: 693386f5d76cca57ee3d80359c3b19128660366c
License: MIT, Copyright (c) 2026 LTGOz; see upstream-LICENSE.txt.

The upstream author describes SW2023 testing. We reviewed its SKILL.md, recipe workflow,
API-pitfalls reference and dependencies. This adapter applies the recipe-first workflow,
unit awareness, staged verification and explicit API compatibility checks to remote-b-hub.
The upstream bridge, macros, dependencies and broad feature list are not installed as executable backend code.
In particular, upstream automatic feature retries, dimension changes and macro fallback are not enabled.

Other candidates reviewed during selection:
- https://github.com/delancy827/solidworks-skills : contains SW2024-specific workflows;
  not treated as SW2023 acceptance evidence.
- https://github.com/wzyn20051216/solidworks-automation-skill : broader COM/MCP toolkit;
  not a drop-in backend for this project's restricted API.

Version authority: installed SW revision/type library and official SW2023 API documentation,
not a generic claim that an API works on a different workstation or release.
https://help.solidworks.com/2023/english/api/sldworksapiprogguide/Welcome.htm

The application's existing fixes remain authoritative for selection, property-vs-method COM reads,
typed null datums, dimension-input suppression and explicit circle-center dimensions.
For legacy FullyDefineSketch type mismatch, inspect B's actual executing version and traceback.
The local adapter neither rewrites the COM engine nor bypasses its strict checks.
