# Reviewed AngelSix integration

Source: https://github.com/angelsix/solidworks-api
Pinned develop commit: 58787e2cefdcc03aebc15a51bd52ba151f3969d4.
Read: SolidDna/AngelSix.SolidDna/AngelSix.SolidDna.csproj,
SolidWorks/Dimension/ModelDisplayDimension.cs, SolidWorks/Models/ModelExtension.cs,
and the repository license. License copy: angelsix-LICENSE.txt.

SolidDNA wraps C# COM objects, selection identities and document-type-sensitive inspection.
The reviewed project targets .NET Framework 4.7.2 and references its 2020 Interop directory;
those build settings are not a SW2023 acceptance record. Its References directory has
additional Dassault/SolidWorks usage terms. No DLL from that directory is redistributed here.

Adapted ideas: stable named dimensions, inspect before mutating, explicit model types,
COM threading and distinguishing unavailable mass/geometry from a valid zero result.
The application adds a fixed read-only dimension lookup to its existing C# controller,
compiling only against the user's local SW2023 PIA. No SolidDNA package dependency is added.

API references:
- IModelDoc2.Parameter (D1@Feature identity): https://help.solidworks.com/2023/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModelDoc2~Parameter.html
- IDimension.SystemValue (legacy read property, available in SW2023): https://help.solidworks.com/2023/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IDimension~SystemValue.html

SystemValue is marked obsolete in favor of configuration-aware GetSystemValue3; this adapter
reads only the active configuration and does not claim values for every configuration.
