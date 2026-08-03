import os
import sys
import subprocess
import PyInstaller.__main__
import customtkinter

def build_executable():
    print("Building EfStrGenerator executable...")
    
    # Get customtkinter folder location
    ctk_path = os.path.dirname(customtkinter.__file__)
    sep = ";" if sys.platform == "win32" else ":"
    add_data_ctk = f"{ctk_path}{sep}customtkinter"

    args = [
        "main.py",
        "--name=EfStrGenerator",
        "--onedir",
        "--windowed",
        f"--add-data={add_data_ctk}",
        "--hidden-import=crisperwhisper",
        "--hidden-import=imageio_ffmpeg",
        "--clean",
        "-y"
    ]

    print(f"Running PyInstaller with arguments: {args}")
    PyInstaller.__main__.run(args)
    print("Build complete! Executable is located in the dist/ directory.")

if __name__ == "__main__":
    build_executable()
