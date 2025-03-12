from ..ovapi import OmniverseAPI
import omni.kit.commands

app = OmniverseAPI()

@app.request
def command_execute(name: str, **kwargs) -> bool:
    omni.kit.commands.execute(name, **kwargs)
    return True

@app.request
def command_undo() -> bool:
    omni.kit.undo.undo()
    return True
