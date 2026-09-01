import maya.cmds as cmds
import re

def nad_rename_tool():
    # Prompt user for base name
    result = cmds.promptDialog(
        title='NAD Toolset - Rename',
        message='Enter base name:',
        button=['OK','Cancel'],
        defaultButton='OK',
        cancelButton='Cancel',
        dismissString='Cancel')

    if result == 'OK':
        base_name = cmds.promptDialog(query=True, text=True)

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
