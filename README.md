# NAD Toolset

Batch renamer (+ Sanity Check for Blender) used by NAD. Mirrors [riouxr/NAD-toolkit](https://github.com/riouxr/NAD-toolkit).

Naming convention: `SM_Name1_Name2_Name3_XX` (Blender adds a material-type suffix: `SM_Name1_Name2_Name3_SD_XX`).
Any of the three name fields can be left empty — empty fields are skipped so no double underscores are produced.

## blender/NAD_Toolset

Blender Extension (4.5+, uses `blender_manifest.toml`). Zip the `NAD_Toolset` folder and install via
*Preferences > Get Extensions > (dropdown) Install from Disk*.

## maya/NAD_rename_Maya.py

Maya shelf script. Run it from a shelf button; it prompts for up to 3 name fields, then renames the current selection.
