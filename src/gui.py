import os
import sys
import traceback
import threading
import subprocess
import time
import requests
from tkinter import filedialog, messagebox
import customtkinter as ctk
import glob
import ctypes
import ctypes.util

# Monkeypatch CTkScrollableFrame to handle cases where event.widget is a string (known Tkinter/Linux bug)
original_check_if_valid_scroll = ctk.CTkScrollableFrame._check_if_valid_scroll

def patched_check_if_valid_scroll(self, widget):
    if isinstance(widget, str):
        try:
            widget = self.nametowidget(widget)
        except Exception:
            return False
    return original_check_if_valid_scroll(self, widget)

ctk.CTkScrollableFrame._check_if_valid_scroll = patched_check_if_valid_scroll
ctk.DrawEngine.preferred_drawing_method = "circle_shapes"


from src.constants import LANGUAGE_MAPPING
from src.transcriber import transcribe_media_file
from src.audio import is_media_file
from src.backend import initialize_docker_backend
from src.api_client import submit_job, poll_job

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
ctk.set_widget_scaling(1)


def check_and_setup_cuda_libraries():
    """
    Checks if required cuBLAS and cuDNN shared libraries are available.
    When found, preloads them via ctypes.CDLL(RTLD_GLOBAL) so that
    ctranslate2's dlopen() calls succeed within the current process.
    Also updates LD_LIBRARY_PATH for any child processes.
    Returns a tuple (cublas_found, cudnn_found).
    """
    cublas_found = False
    cudnn_found = False
    cublas_path = None
    cudnn_path = None

    def _add_to_ld_library_path(directory):
        """Helper to prepend a directory to LD_LIBRARY_PATH (for child processes)."""
        ld_path = os.environ.get("LD_LIBRARY_PATH", "")
        if directory not in ld_path.split(":"):
            if ld_path:
                os.environ["LD_LIBRARY_PATH"] = f"{directory}:{ld_path}"
            else:
                os.environ["LD_LIBRARY_PATH"] = directory

    # 1. Check user-local directory ~/.local/share/EfStrGenerator/cuda_libs
    user_cuda_dir = os.path.expanduser("~/.local/share/EfStrGenerator/cuda_libs")
    if os.path.isdir(user_cuda_dir):
        user_cublas = glob.glob(os.path.join(user_cuda_dir, "libcublas.so*"))
        user_cudnn = glob.glob(os.path.join(user_cuda_dir, "libcudnn.so*"))
        if user_cublas or user_cudnn:
            _add_to_ld_library_path(user_cuda_dir)
        if user_cublas and not cublas_found:
            cublas_path = user_cublas[0]
            cublas_found = True
        if user_cudnn and not cudnn_found:
            cudnn_path = user_cudnn[0]
            cudnn_found = True

    # 2. Check if they are findable by the system linker via ctypes
    if not cublas_found:
        for name in ["cublas", "cublas.so.12", "libcublas.so.12", "cublas.so.11", "libcublas.so.11"]:
            result = ctypes.util.find_library(name)
            if result is not None:
                cublas_found = True
                cublas_path = result
                break

    if not cudnn_found:
        for name in ["cudnn", "cudnn.so.9", "libcudnn.so.9", "cudnn.so.8", "libcudnn.so.8"]:
            result = ctypes.util.find_library(name)
            if result is not None:
                cudnn_found = True
                cudnn_path = result
                break

    # 3. Check the directory of the running application / sys._MEIPASS
    search_dirs = []
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            search_dirs.append(sys._MEIPASS)
        search_dirs.append(os.path.dirname(sys.executable))
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        search_dirs.append(script_dir)
        search_dirs.append(os.path.abspath(os.path.join(script_dir, "..")))

    for d in search_dirs:
        if not cublas_found:
            matches = glob.glob(os.path.join(d, "libcublas.so*"))
            if matches:
                cublas_path = matches[0]
                cublas_found = True
                _add_to_ld_library_path(d)
        if not cudnn_found:
            matches = glob.glob(os.path.join(d, "libcudnn.so*"))
            if matches:
                cudnn_path = matches[0]
                cudnn_found = True
                _add_to_ld_library_path(d)

    # 4. Check python environment packages (nvidia-cublas-cu12, nvidia-cudnn-cu12)
    if not cublas_found:
        try:
            import nvidia.cublas
            for path in getattr(nvidia.cublas, "__path__", []):
                matches = glob.glob(os.path.join(path, "lib", "libcublas.so*"))
                if matches:
                    cublas_path = matches[0]
                    cublas_found = True
                    _add_to_ld_library_path(os.path.join(path, "lib"))
                    break
        except ImportError:
            pass

    if not cudnn_found:
        try:
            import nvidia.cudnn
            for path in getattr(nvidia.cudnn, "__path__", []):
                matches = glob.glob(os.path.join(path, "lib", "libcudnn.so*"))
                if matches:
                    cudnn_path = matches[0]
                    cudnn_found = True
                    _add_to_ld_library_path(os.path.join(path, "lib"))
                    break
        except ImportError:
            pass

    # 5. Preload .so files into the current process so ctranslate2's dlopen() finds them.
    #    Setting LD_LIBRARY_PATH alone is NOT enough — the dynamic linker only reads it
    #    at process startup, not after os.environ is modified at runtime.
    if cublas_found and cublas_path:
        try:
            ctypes.CDLL(cublas_path, mode=ctypes.RTLD_GLOBAL)
        except OSError as e:
            print(f"WARNING: Found cuBLAS at {cublas_path} but failed to preload: {e}")
            cublas_found = False

    if cudnn_found and cudnn_path:
        try:
            ctypes.CDLL(cudnn_path, mode=ctypes.RTLD_GLOBAL)
        except OSError as e:
            print(f"WARNING: Found cuDNN at {cudnn_path} but failed to preload: {e}")
            cudnn_found = False

    return cublas_found, cudnn_found


class EfStrGeneratorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("EfStrGenerator - AI Subtitle Generator")
        self.geometry("1000x800")
        # self.minsize(760, 640)

        self.is_processing = False

        self._create_widgets()

        if sys.platform == "win32":
            self.generate_btn.configure(state="disabled", text="⏳ Connecting to backend...")
            threading.Thread(target=self._initialize_backend, daemon=True).start()
        elif sys.platform.startswith("linux"):
            self.after(100, self._check_gpu_dependencies)

    # ------------------------------------------------------------------
    # Backend init (Windows only)
    # ------------------------------------------------------------------

    def _initialize_backend(self):
        initialize_docker_backend(
            status_callback=lambda msg: self.status_label.configure(text=msg)
        )
        current_text = self.status_label.cget("text")
        if current_text.startswith("⚠️"):
            # Backend unavailable — keep button disabled with a clear label
            self.after(
                0,
                lambda: self.generate_btn.configure(
                    state="disabled", text="⚠️ Backend unavailable"
                ),
            )
            self.after(
                0,
                lambda: messagebox.showwarning(
                    "Connection Warning",
                    "Could not connect to the backend server, and launching Docker Compose failed.\n\n"
                    "Please make sure Docker Desktop is started and run:\n"
                    "docker compose up -d",
                ),
            )
        else:
            # Backend ready — enable the button
            self.after(
                0,
                lambda: self.generate_btn.configure(
                    state="normal", text="⚡ Generate SRT Subtitles"
                ),
            )

    # ------------------------------------------------------------------
    # Widget construction
    # ------------------------------------------------------------------

    def _create_widgets(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self.body_frame = self._build_body()
        self._build_file_card(self.body_frame)
        self._build_config_card(self.body_frame)
        self._build_progress_card(self.body_frame)
        self._build_buttons(self.body_frame)

    def _build_header(self):
        header_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray85", "gray14"))
        header_frame.grid(row=0, column=0, sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header_frame,
            text="🎬 EfStrGenerator",
            font=ctk.CTkFont(family="Inter", size=24, weight="bold"),
            text_color=("gray10", "gray90"),
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(16, 4))

        ctk.CTkLabel(
            header_frame,
            text="Extract high-precision SRT subtitles from audio & video using CrisperWhisper AI",
            font=ctk.CTkFont(family="Inter", size=13),
            text_color=("gray40", "gray60"),
        ).grid(row=1, column=0, sticky="w", padx=24, pady=(0, 16))

    def _build_body(self) -> ctk.CTkScrollableFrame:
        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=24, pady=16)
        body.grid_columnconfigure(0, weight=1)
        return body

    def _build_file_card(self, parent):
        card = ctk.CTkFrame(parent, corner_radius=12)
        card.grid(row=0, column=0, sticky="ew", pady=(0, 16), padx=2)
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card, text="📁 File Selection", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(14, 10)
        )

        ctk.CTkLabel(card, text="Media File:", font=ctk.CTkFont(weight="bold")).grid(
            row=1, column=0, sticky="w", padx=(16, 8), pady=8
        )
        self.input_entry = ctk.CTkEntry(
            card, placeholder_text="Select audio or video file (.mp4, .mkv, .mp3, .wav, etc.)"
        )
        self.input_entry.grid(row=1, column=1, sticky="ew", padx=8, pady=8)
        ctk.CTkButton(card, text="Browse...", width=100, command=self._browse_input_file).grid(
            row=1, column=2, sticky="e", padx=(8, 16), pady=8
        )

        ctk.CTkLabel(card, text="SRT Output:", font=ctk.CTkFont(weight="bold")).grid(
            row=2, column=0, sticky="w", padx=(16, 8), pady=(8, 16)
        )
        self.output_entry = ctk.CTkEntry(card, placeholder_text="Auto-generated output file (.srt)")
        self.output_entry.grid(row=2, column=1, sticky="ew", padx=8, pady=(8, 16))
        ctk.CTkButton(
            card,
            text="Save As...",
            width=100,
            fg_color="transparent",
            border_width=1,
            text_color=("gray10", "gray90"),
            command=self._browse_output_file,
        ).grid(row=2, column=2, sticky="e", padx=(8, 16), pady=(8, 16))

    def _build_config_card(self, parent):
        card = ctk.CTkFrame(parent, corner_radius=12)
        card.grid(row=1, column=0, sticky="ew", pady=(0, 16), padx=2)
        card.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkLabel(
            card, text="⚙️ Transcription Settings", font=ctk.CTkFont(size=16, weight="bold")
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(14, 10))

        for col, (label, values, default) in enumerate(
            [
                ("Conversation Language:", list(LANGUAGE_MAPPING.keys()), "English"),
                ("Model Size:", ["large", "turbo", "medium", "small"], "large"),
                ("Transcription Mode:", ["verbatim", "intended"], "verbatim"),
            ]
        ):
            ctk.CTkLabel(card, text=label, font=ctk.CTkFont(weight="bold")).grid(
                row=1, column=col, sticky="w", padx=16, pady=(4, 2)
            )
            dropdown = ctk.CTkOptionMenu(card, values=values)
            dropdown.set(default)
            dropdown.grid(row=2, column=col, sticky="ew", padx=16, pady=(0, 16))
            if col == 0:
                self.lang_dropdown = dropdown
            elif col == 1:
                self.model_dropdown = dropdown
            else:
                self.mode_dropdown = dropdown

    def _build_progress_card(self, parent):
        card = ctk.CTkFrame(parent, corner_radius=12)
        card.grid(row=2, column=0, sticky="ew", pady=(0, 16), padx=2)
        card.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            card,
            text="Ready to generate subtitles.",
            font=ctk.CTkFont(size=13),
            text_color=("gray30", "gray70"),
        )
        self.status_label.grid(row=0, column=0, sticky="w", padx=16, pady=(16, 6))

        self.progress_bar = ctk.CTkProgressBar(card)
        self.progress_bar.set(0.0)
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 16))

    def _build_buttons(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=3, column=0, sticky="ew", pady=(0, 16))
        frame.grid_columnconfigure(0, weight=1)

        self.generate_btn = ctk.CTkButton(
            frame,
            text="⚡ Generate SRT Subtitles",
            font=ctk.CTkFont(size=16, weight="bold"),
            height=46,
            command=self._start_generation,
        )
        self.generate_btn.grid(row=0, column=0, sticky="ew")

        self.open_folder_btn = ctk.CTkButton(
            frame,
            text="📂 Open Output Folder",
            font=ctk.CTkFont(size=14),
            height=38,
            fg_color="transparent",
            border_width=1,
            text_color=("gray10", "gray90"),
            command=self._open_output_folder,
        )
        self.open_folder_btn.grid_remove()

    # ------------------------------------------------------------------
    # File browsing
    # ------------------------------------------------------------------

    def _browse_input_file(self):
        filetypes = [
            ("Media Files", "*.mp4 *.mkv *.avi *.mov *.webm *.mp3 *.wav *.ogg *.flac *.m4a *.aac *.wma"),
            ("Video Files", "*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv"),
            ("Audio Files", "*.mp3 *.wav *.ogg *.flac *.m4a *.aac *.wma"),
            ("All Files", "*.*"),
        ]
        filename = filedialog.askopenfilename(title="Select Media File", filetypes=filetypes)
        if filename:
            self.input_entry.delete(0, "end")
            self.input_entry.insert(0, filename)
            self._auto_generate_output_path(filename)

    def _auto_generate_output_path(self, input_path: str):
        if not input_path:
            return
        base_name, _ = os.path.splitext(input_path)
        self.output_entry.delete(0, "end")
        self.output_entry.insert(0, f"{base_name}.srt")

    def _browse_output_file(self):
        current_val = self.output_entry.get().strip()
        filename = filedialog.asksaveasfilename(
            title="Save Subtitles As",
            defaultextension=".srt",
            filetypes=[("SRT Subtitle File", "*.srt"), ("All Files", "*.*")],
            initialdir=os.path.dirname(current_val) if current_val else None,
            initialfile=os.path.basename(current_val) if current_val else "subtitles.srt",
        )
        if filename:
            self.output_entry.delete(0, "end")
            self.output_entry.insert(0, filename)

    # ------------------------------------------------------------------
    # Generation dispatch
    # ------------------------------------------------------------------

    def _start_generation(self):
        if self.is_processing:
            return

        input_path = self.input_entry.get().strip()
        output_path = self.output_entry.get().strip()

        if not input_path or not os.path.exists(input_path):
            messagebox.showerror("Error", "Please select a valid existing input audio or video file.")
            return

        if not output_path:
            self._auto_generate_output_path(input_path)
            output_path = self.output_entry.get().strip()

        lang_code = LANGUAGE_MAPPING.get(self.lang_dropdown.get(), "en")
        model_size = self.model_dropdown.get()
        mode = self.mode_dropdown.get()

        self.is_processing = True
        self.generate_btn.configure(state="disabled", text="⏳ Processing...")
        self.open_folder_btn.grid_remove()
        self.progress_bar.set(0.05)

        if sys.platform == "win32":
            self.status_label.configure(text="Creating remote transcription task on FastAPI server...")
            target = self._run_remote_transcription
        else:
            self.status_label.configure(text="Initializing local transcription pipeline...")
            target = self._run_local_transcription

        threading.Thread(
            target=target,
            args=(input_path, output_path, lang_code, model_size, mode),
            daemon=True,
        ).start()

    def _run_remote_transcription(self, input_path, output_path, lang_code, model_size, mode):
        abs_input_path = os.path.abspath(input_path)
        try:
            job_id = submit_job(abs_input_path, lang_code, model_size, mode)

            consecutive_failures = 0
            max_failures = 5

            while True:
                time.sleep(3.0)
                try:
                    job_status = poll_job(job_id)
                    consecutive_failures = 0  # reset on success
                except Exception as poll_err:
                    traceback.print_exc()
                    consecutive_failures += 1
                    print(f"Polling failed (attempt {consecutive_failures}/{max_failures}): {poll_err}")
                    if consecutive_failures >= max_failures:
                        raise poll_err
                    continue

                status = job_status["status"]
                self._update_progress(f"[{status.upper()}] {job_status['status_text']}", job_status["progress"])

                if status == "completed":
                    srt_content = job_status["result_srt"]
                    with open(output_path, "w", encoding="utf-8") as f:
                        f.write(srt_content)
                    count = self._count_subtitle_blocks(output_path)
                    self.after(0, lambda: self._on_transcription_success({"output_filepath": output_path, "subtitle_count": count}))
                    break
                elif status == "failed":
                    error_msg = job_status["error"] or "Unknown worker error"
                    self.after(0, lambda msg=error_msg: self._on_transcription_failure(msg))
                    break
        except Exception as e:
            traceback.print_exc()
            self.after(0, lambda err=e: self._on_transcription_failure(f"API Connection error: {err}"))

    def _run_local_transcription(self, input_path, output_path, lang_code, model_size, mode):
        try:
            res = transcribe_media_file(
                input_filepath=input_path,
                output_filepath=output_path,
                language_code=lang_code,
                model_size=model_size,
                mode=mode,
                progress_callback=self._update_progress,
            )
            self.after(0, lambda: self._on_transcription_success(res))
        except Exception as e:
            traceback.print_exc()
            err_msg = str(e)
            self.after(0, lambda: self._on_transcription_failure(err_msg))

    @staticmethod
    def _count_subtitle_blocks(srt_path: str) -> int:
        count = 0
        with open(srt_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().isdigit():
                    count = int(line.strip())
        return count

    # ------------------------------------------------------------------
    # Progress & result callbacks
    # ------------------------------------------------------------------

    def _update_progress(self, status: str, percentage: float):
        self.after(0, lambda: (
            self.status_label.configure(text=status),
            self.progress_bar.set(percentage),
        ))

    def _on_transcription_success(self, res: dict):
        self.is_processing = False
        self.generate_btn.configure(state="normal", text="⚡ Generate SRT Subtitles")
        output_filepath = res.get("output_filepath", "")
        count = res.get("subtitle_count", 0)
        self.status_label.configure(
            text=f"✅ Success! Saved {count} subtitle entries to {os.path.basename(output_filepath)}"
        )
        self.progress_bar.set(1.0)
        self.open_folder_btn.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        messagebox.showinfo(
            "Success",
            f"SRT Subtitle generated successfully!\n\nLocation: {output_filepath}\nSubtitle blocks: {count}",
        )

    def _on_transcription_failure(self, error_msg: str):
        self.is_processing = False
        self.generate_btn.configure(state="normal", text="⚡ Generate SRT Subtitles")
        self.status_label.configure(text="❌ Error occurred during processing.")
        self.progress_bar.set(0.0)
        messagebox.showerror("Transcription Error", f"An error occurred while generating subtitles:\n\n{error_msg}")

    # ------------------------------------------------------------------
    # Output folder
    # ------------------------------------------------------------------

    def _open_output_folder(self):
        output_path = self.output_entry.get().strip()
        if not output_path:
            return
        folder = os.path.dirname(output_path)
        if not folder or not os.path.exists(folder):
            return
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.run(["open", folder])
        else:
            subprocess.run(["xdg-open", folder])

    # ------------------------------------------------------------------
    # GPU dependency check (Linux only)
    # ------------------------------------------------------------------

    def _check_gpu_dependencies(self):
        cublas_ok, cudnn_ok = check_and_setup_cuda_libraries()
        if not cublas_ok or not cudnn_ok:
            missing = []
            if not cublas_ok:
                missing.append("cuBLAS (libcublas.so)")
            if not cudnn_ok:
                missing.append("cuDNN (libcudnn.so)")
            
            missing_str = " and ".join(missing)
            warning_msg = (
                f"NVIDIA {missing_str} libraries were not found on your system.\n"
                "GPU acceleration for transcription will not be available, and the application "
                "will fall back to CPU (which is significantly slower).\n"
                "To enable GPU acceleration, please install nvidia-cublas-cu12 and nvidia-cudnn-cu12, "
                "or place their .so files in ~/.local/share/EfStrGenerator/cuda_libs/."
            )
            print(f"WARNING: {warning_msg.replace(chr(10), ' ')}")
            
            banner_msg = (
                f"⚠️ GPU Acceleration Unavailable: {missing_str} not installed. Performance will be slower.\n"
                "👉 Click here to automatically download and install these libraries (requires internet)."
            )
            self._show_warning_banner(banner_msg)

    def _show_warning_banner(self, message):
        self.warning_frame = ctk.CTkFrame(
            self,
            corner_radius=0,
            fg_color="#ea580c",  # Premium dark orange warning color
            cursor="hand2"
        )
        self.warning_frame.grid(row=1, column=0, sticky="ew")
        self.warning_frame.grid_columnconfigure(0, weight=1)
        
        warning_lbl = ctk.CTkLabel(
            self.warning_frame,
            text=message,
            font=ctk.CTkFont(family="Inter", size=13, weight="bold"),
            text_color="#ffffff",
            anchor="center",
            justify="center"
        )
        warning_lbl.grid(row=0, column=0, padx=16, pady=8, sticky="ew")
        
        # Configure dynamic wraplength to prevent text cropping on resize
        def update_wraplength(event):
            warning_lbl.configure(wraplength=event.width - 32)
            
        self.warning_frame.bind("<Configure>", update_wraplength)
        
        # Bind click events
        warning_lbl.bind("<Button-1>", lambda e: self._start_cuda_download(warning_lbl))
        
        # Shift body frame to row 2
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)
        self.body_frame.grid(row=2, column=0, sticky="nsew", padx=24, pady=16)

    def _start_cuda_download(self, warning_lbl):
        # Unbind click events to prevent duplicate clicks
        self.warning_frame.unbind("<Button-1>")
        warning_lbl.unbind("<Button-1>")
        
        # Change cursor to default to show it is no longer clickable
        self.warning_frame.configure(cursor="")
        warning_lbl.configure(cursor="")
        
        # Spawn daemon thread
        threading.Thread(
            target=self._download_and_extract_cuda_thread,
            args=(warning_lbl,),
            daemon=True
        ).start()

    def _download_and_extract_cuda_thread(self, warning_lbl):
        import zipfile
        import shutil
        
        def update_status(text):
            self.after(0, lambda: warning_lbl.configure(text=text))
            
        try:
            user_cuda_dir = os.path.expanduser("~/.local/share/EfStrGenerator/cuda_libs")
            os.makedirs(user_cuda_dir, exist_ok=True)
            
            packages = [
                ("nvidia-cublas-cu12", "12.9.2.10"),
                ("nvidia-cudnn-cu12", "9.24.0.43")
            ]
            
            for package_name, version in packages:
                update_status(f"⏳ Querying PyPI for {package_name}...")
                
                # Fetch JSON metadata from PyPI
                api_url = f"https://pypi.org/pypi/{package_name}/{version}/json"
                resp = requests.get(api_url, timeout=15)
                resp.raise_for_status()
                metadata = resp.json()
                
                # Find the direct wheel download URL matching manylinux and x86_64
                download_url = None
                for u in metadata.get("urls", []):
                    if u.get("packagetype") == "bdist_wheel" and "manylinux" in u.get("filename", "") and "x86_64" in u.get("filename", ""):
                        download_url = u["url"]
                        break
                        
                if not download_url:
                    raise RuntimeError(f"Could not find a suitable wheel for {package_name} on PyPI.")
                
                # Download wheel file to target dir
                temp_whl_path = os.path.join(user_cuda_dir, f"temp_{package_name}.whl")
                update_status(f"⏳ Downloading {package_name} (0%)...")
                
                with requests.get(download_url, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    total_size = int(r.headers.get("content-length", 0))
                    downloaded = 0
                    
                    with open(temp_whl_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total_size > 0:
                                    percent = int((downloaded / total_size) * 100)
                                    update_status(f"⏳ Downloading {package_name} ({percent}%)...")
                                    
                # Extract .so files
                update_status(f"⏳ Extracting shared libraries from {package_name}...")
                with zipfile.ZipFile(temp_whl_path, "r") as zip_ref:
                    for member in zip_ref.infolist():
                        basename = os.path.basename(member.filename)
                        if not basename:
                            continue
                        if ".so" in basename:
                            target_path = os.path.join(user_cuda_dir, basename)
                            with zip_ref.open(member) as source, open(target_path, "wb") as target:
                                shutil.copyfileobj(source, target)
                                
                # Cleanup temp wheel file
                os.remove(temp_whl_path)
                
            update_status("⚡ All libraries installed successfully! Restarting application...")
            time.sleep(2)
            
            # Restart the application
            os.execv(sys.executable, [sys.executable] + sys.argv)
            
        except Exception as e:
            traceback.print_exc()
            err_msg = f"❌ Installation failed: {str(e)}\n👉 Click here to try again."
            update_status(err_msg)
            
            # Restore cursor and rebind click events to allow retry
            self.after(0, lambda: (
                self.warning_frame.configure(cursor="hand2"),
                warning_lbl.configure(cursor="hand2"),
                self.warning_frame.bind("<Button-1>", lambda e: self._start_cuda_download(warning_lbl)),
                warning_lbl.bind("<Button-1>", lambda e: self._start_cuda_download(warning_lbl))
            ))


def main():
    if sys.platform == "win32":
        from src.watchdog import spawn_watchdog
        spawn_watchdog()
    app = EfStrGeneratorApp()
    app.mainloop()
