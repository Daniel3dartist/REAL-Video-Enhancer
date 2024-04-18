import os
import platform

homedir = os.path.expanduser(r"~")
operating_system = platform.system()
global flatpak
if operating_system == "Darwin":
    flatpak = False
    if os.path.exists(f"{homedir}/Library/REAL-Video-Enhancer") == False:
        os.system(f'mkdir -p "{homedir}/Library/REAL-Video-Enhancer"')
if operating_system == "Linux":
    if os.path.exists(f"{homedir}/.local/share/REAL-Video-Enhancer") == False:
        os.system(f'mkdir -p "{homedir}/.local/share/REAL-Video-Enhancer"')

    flatpak = False
    if "FLATPAK_ID" in os.environ:
        flatpak = True
if operating_system == "Windows":
    if not os.path.exists(os.path.join(f"{homedir}",r"REAL-Video-Enhancer")):
	    os.makedirs(os.path.join(f"{homedir}",r"REAL-Video-Enhancer"))
print(os.path.join("C:\\","Program Files (x86)","REAL-Video-Enhancer"))
        
def thisdir():
    if operating_system == "Linux":
        if flatpak == True:
            if (
                os.path.exists(
                    f"{homedir}/.var/app/io.github.tntwise.REAL-Video-Enhancer"
                )
                == False
            ):
                os.system(
                    f'mkdir -p "{homedir}/.var/app/io.github.tntwise.REAL-Video-Enhancer"'
                )
            return f"{homedir}/.var/app/io.github.tntwise.REAL-Video-Enhancer"
        return f"{homedir}/.local/share/REAL-Video-Enhancer"
    if operating_system == "Darwin":
        return f"{homedir}/Library/REAL-Video-Enhancer"
    
    if operating_system == "Windows":
        return os.path.join("C:\\","Program Files (x86)","REAL-Video-Enhancer")
