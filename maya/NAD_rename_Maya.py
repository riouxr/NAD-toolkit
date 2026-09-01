import maya.cmds as cmds
import re

def _join_name_parts(*parts):
    return "_".join(p for p in parts if p)

def nad_rename_tool():
    # Prompt user for up to 3 name parts, joined by underscores
    fields = []
    for i in range(1, 4):
        result = cmds.promptDialog(
            title='NAD Toolset - Rename',
            message=f'Enter name part {i} (leave empty to skip):',
            button=['OK','Cancel'],
            defaultButton='OK',
            cancelButton='Cancel',
            dismissString='Cancel')

        if result != 'OK':
            return

        fields.append(cmds.promptDialog(query=True, text=True).strip())

    base_name = _join_name_parts(*fields)
    if not base_name:
        cmds.warning("No name entered!")
        return

    # Get selected objects
    selection = cmds.ls(selection=True)
    if not selection:
        cmds.warning("No objects selected!")
    else:
        selected_set = set(selection)
        pattern = re.compile(rf"^SM_{re.escape(base_name)}_(\d+)$")

        # Find highest existing number for this base name
        max_num = 0
        for obj in cmds.ls():
            if obj in selected_set:
                continue
            m = pattern.match(obj)
            if m:
                max_num = max(max_num, int(m.group(1)))

        for i, obj in enumerate(selection, max_num + 1):
            new_name = f"SM_{base_name}_{i:02d}"
            cmds.rename(obj, new_name)
        cmds.inViewMessage(amg='Objects renamed!', pos='topCenter', fade=True)

# Call the function so it runs when you press the shelf button
nad_rename_tool()
