# Recipe adapter

Use `computer_b_plan_part` for these deterministic templates:

| template | parameters (mm) | result |
| --- | --- | --- |
| box | length_mm, width_mm, height_mm | centered rectangle + boss |
| cylinder | radius_mm, depth_mm, cx_mm, cy_mm | explicitly positioned circle + boss |
| tube | outer_radius_mm, inner_radius_mm, depth_mm | circular boss + coaxial circular cut |
| two_hole_plate | length_mm, width_mm, thickness_mm, hole_radius_mm, hole_spacing_mm | centered base + two circular cuts at x=±spacing/2 |

Returned defaults are assumptions and must be checked against the user's request before submission.
The tube/plate templates need real cut-direction/topology acceptance; valid JSON does not prove a through hole.
No arbitrary code, paths, COM methods, macro names or upstream op lists are accepted as template parameters.

Full recipe part example (not executed by reading this reference):

```json
{"doc_type":"part","name":"Example_Cylinder","operations":[{"op":"boss_extrude","plane":"front","profile":{"type":"circle","cx_mm":0,"cy_mm":0,"radius_mm":10},"depth_mm":10}]}
```

For assemblies use the existing schema: components reference simple SLDPRT filenames in B's output
directory; mates use explicit planes or named entities. Verify every intended mate and degrees of freedom.
The planner does not manufacture precision gear features or claim a motion study.
