import os
import sys
import subprocess
import PyInstaller.__main__


def build_executable():
    print("Building EfStrGenerator executable...")

    args = [
        "main.py",
        "--name=EfStrGenerator",
        "--onedir",
        "--windowed",
        "--collect-data=customtkinter",
        "--hidden-import=imageio_ffmpeg",
        "--hidden-import=stable_whisper",
        "--hidden-import=faster_whisper",
        "--strip",
        # torchaudio IS needed (stable-ts uses it for Silero VAD resampling) --
        # only torchvision is genuinely unused
        "--exclude-module=torchvision",
        "--exclude-module=matplotlib",
        "--exclude-module=pandas",
        "--exclude-module=IPython",
        "--exclude-module=notebook",
        "--exclude-module=jupyter",
        "--exclude-module=sympy",
        "--exclude-module=pytest",
        "--exclude-module=nvidia",
        "--exclude-module=nvidia.cublas",
        "--exclude-module=nvidia.cudnn",
        "--clean",
        "-y"
    ]

    print(f"Running PyInstaller with arguments: {args}")
    PyInstaller.__main__.run(args)
    print("Build complete! Executable is located in the dist/ directory.")


if __name__ == "__main__":
    build_executable()
 
