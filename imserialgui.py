"""
Symbios Showcase v7
- Robust serial handling with reconnect
- Better conversation accumulation and timeout logic
- "Sleeping" animation when ESP32 not connected / idle for long
- Dynamic wraplength updated on resize to avoid word cut
- Side panel fixed width, larger readable fonts
- Logs buffered and shown in side panel (no separate window)
- Exit button (discrete), removed Restart button
- Assistant name: Symba (female voice)
Usage:
    python xiaozhi_symbios_gui_v7.py
Adjust PORT and BAUDRATE at top if needed.
"""
import re
import threading
import time
import random
import serial
import tkinter as tk
from tkinter import ttk

# ===================== CONFIGURAÇÕES =====================
PORT = "COM3"      # <<< PORTA DO SEU ESP32
BAUDRATE = 115200  # <<< Igual ao Serial.begin() no ESP
RECONNECT_INTERVAL = 3.0     # segundos entre tentativas de reconectar quando desconectado
SIDE_CYCLE_INTERVAL = 100_000  # ms: alternar PROJETO/EQUIPE/QR
PARTICLE_COUNT = 22            # partículas de fundo
BOT_TURN_TIMEOUT = 3.0         # segundos sem << para considerar nova resposta
SLEEP_TIMEOUT = 20.0           # segundos sem atividade para entrar em "sleep"
# =========================================================

# Regex para logs do ESP-IDF
regex_info = re.compile(r"^I\s*\((\d+)\)\s+(.+?):\s*(.*)")
regex_warn = re.compile(r"^W\s*\((\d+)\)\s+(.+?):\s*(.*)")
regex_error = re.compile(r"^E\s*\((\d+)\)\s+(.+?):\s*(.*)")


def parse_line(line: str):
    line = line.strip("\r\n")
    m_info = regex_info.match(line)
    m_warn = regex_warn.match(line)
    m_error = regex_error.match(line)

    if m_info:
        ts, tag, content = m_info.groups()
        return {"type": "info", "timestamp": ts, "tag": tag, "content": content}
    if m_warn:
        ts, tag, content = m_warn.groups()
        return {"type": "warn", "timestamp": ts, "tag": tag, "content": content}
    if m_error:
        ts, tag, content = m_error.groups()
        return {"type": "error", "timestamp": ts, "tag": tag, "content": content}
    if "STATE:" in line:
        return {"type": "state", "timestamp": None, "tag": "STATE", "content": line}
    return {"type": "other", "timestamp": None, "tag": None, "content": line}


class FaceWidget:
    """
    Improved face with:
    - Proper 'sleep' state when disconnected or idle long
    - Stronger speaking animation
    - Background particles and subtle gradient
    """

    def __init__(self, parent):
        self.parent = parent
        self.canvas = tk.Canvas(parent, bg="#020308", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # states: idle, listening, speaking, sleep
        self.state = "idle"
        self.last_blink = time.time()
        self.blink_interval = 4.0
        self.blinking = False
        self.mouth_phase = 0
        self.glow_phase = 0

        # sleeping animation parameters
        self.sleep_blink_interval = 10.0
        self.sleeping = False
        self.sleep_z_phase = 0

        # particles
        self.particles = []
        self._init_particles()
        self.canvas.after(60, self._animate)

    def _init_particles(self):
        self.particles = []
        for _ in range(PARTICLE_COUNT):
            self.particles.append({
                "x": random.random(),
                "y": random.random(),
                "r": random.uniform(1.8, 4.2),
                "vy": random.uniform(0.0008, 0.003),
                "alpha": random.uniform(0.15, 0.6),
            })

    def set_state(self, state: str):
        # Accept states and manage sleeping flag
        if state == "sleep":
            self.sleeping = True
            self.state = "sleep"
        else:
            self.sleeping = False
            self.state = state

        # when going to speaking, speed up glow and mouth
        if self.state == "speaking":
            self.mouth_phase = 0

    def _update_particles(self):
        for p in self.particles:
            # slower motion when sleeping
            factor = 0.25 if self.sleeping else 1.0
            p["y"] -= p["vy"] * factor
            if p["y"] < 0:
                p["y"] = 1.0
                p["x"] = random.random()
                p["vy"] = random.uniform(0.0008, 0.003)
                p["r"] = random.uniform(1.8, 4.2)
                p["alpha"] = random.uniform(0.15, 0.6)

    def _draw_gradient_bg(self, w, h):
        # simple vertical gradient: draw a few rectangles for performance
        # colors chosen to be subtle and not overpower the face
        top = (6, 10, 30)
        mid = (10, 8, 28)
        bottom = (8, 6, 20)
        steps = 8
        for i in range(steps):
            t = i / (steps - 1)
            # interpolate in two ranges
            if t < 0.5:
                a = t * 2
                r = int(top[0] + (mid[0] - top[0]) * a)
                g = int(top[1] + (mid[1] - top[1]) * a)
                b = int(top[2] + (mid[2] - top[2]) * a)
            else:
                a = (t - 0.5) * 2
                r = int(mid[0] + (bottom[0] - mid[0]) * a)
                g = int(mid[1] + (bottom[1] - mid[1]) * a)
                b = int(mid[2] + (bottom[2] - mid[2]) * a)
            self.canvas.create_rectangle(0, i * (h / steps), w, (i + 1) * (h / steps),
                                         fill=f"#{r:02x}{g:02x}{b:02x}", outline="")

    def _draw_face(self):
        self.canvas.delete("all")
        w = self.canvas.winfo_width() or 900
        h = self.canvas.winfo_height() or 480

        # background gradient
        self._draw_gradient_bg(w, h)

        # particles in the background
        self._update_particles()
        for p in self.particles:
            px = p["x"] * w
            py = p["y"] * h
            r = p["r"]
            # draw subtle circles
            col = "#1B2B33"
            self.canvas.create_oval(px - r, py - r, px + r, py + r, fill=col, outline="")

        # visor dimensions - tuned to be less stretched horizontally
        pad_x = w * 0.20
        pad_y = h * 0.18
        x1, y1 = pad_x, pad_y
        x2, y2 = w - pad_x, h - pad_y
        radius = min(w, h) * 0.05

        # visor glow intensity depends on state
        glow_base = 70 if self.state == "speaking" else 45
        glow = glow_base + int(25 * abs((self.glow_phase % 40) - 20) / 20)
        visor_border_color = f"#{glow:02x}{(glow+30):02x}{(glow+60):02x}"

        # visor (rounded rect)
        self._round_rect(x1, y1, x2, y2, radius, fill="#07070B", outline=visor_border_color, width=5)

        # inner visor
        inner_margin = max(6, int(min(w, h) * 0.01))
        self._round_rect(x1 + inner_margin, y1 + inner_margin, x2 - inner_margin, y2 - inner_margin,
                         radius=max(8, radius - 6), fill="#06050A", outline="")

        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2

        # compute eye color and behaviors
        if self.state == "speaking":
            eye_color = "#7CFF2F"
        elif self.state == "listening":
            eye_color = "#00E5FF"
        elif self.state == "sleep":
            eye_color = "#47636F"
        else:
            eye_color = "#4FFFB2"

        # eye geometry
        eye_spacing = (x2 - x1) * 0.34
        eye_radius = min((x2 - x1), (y2 - y1)) * 0.11

        left_eye_center = (cx - eye_spacing / 2, cy - eye_radius * 0.25)
        right_eye_center = (cx + eye_spacing / 2, cy - eye_radius * 0.25)

        # blinking behavior: in sleep, very slow; else normal
        blink_interval = self.sleep_blink_interval if self.sleeping else self.blink_interval
        now = time.time()
        if not self.blinking and (now - self.last_blink) > blink_interval:
            self.blinking = True
            self.last_blink = now
        elif self.blinking and (now - self.last_blink) > 0.18:
            self.blinking = False

        if self.state == "sleep":
            # eyes almost closed (gentle line)
            for ex, ey in (left_eye_center, right_eye_center):
                self.canvas.create_line(ex - eye_radius * 0.9, ey + 2, ex + eye_radius * 0.9, ey + 2,
                                        fill=eye_color, width=5, capstyle=tk.ROUND)
        else:
            if self.blinking:
                for ex, ey in (left_eye_center, right_eye_center):
                    self.canvas.create_line(ex - eye_radius, ey, ex + eye_radius, ey,
                                            fill=eye_color, width=6, capstyle=tk.ROUND)
            else:
                for ex, ey in (left_eye_center, right_eye_center):
                    self.canvas.create_oval(ex - eye_radius, ey - eye_radius, ex + eye_radius, ey + eye_radius,
                                            outline=eye_color, width=5)
                    # horizontal cut line to mimic the shown style
                    self.canvas.create_line(ex - eye_radius * 0.78, ey, ex + eye_radius * 0.78, ey,
                                            fill=eye_color, width=5, capstyle=tk.ROUND)

        # mouth animation
        mouth_width = (x2 - x1) * 0.48
        base_mouth_height = (y2 - y1) * 0.22

        if self.state == "speaking":
            amp = base_mouth_height * 0.5
            mouth_height = base_mouth_height + amp * abs((self.mouth_phase % 18) - 9) / 9
        elif self.state == "listening":
            mouth_height = base_mouth_height * 0.9
        elif self.state == "sleep":
            mouth_height = base_mouth_height * 0.25
        else:
            mouth_height = base_mouth_height * 0.6

        mouth_y = cy + eye_radius * 1.4

        self.canvas.create_arc(cx - mouth_width / 2, mouth_y - mouth_height / 2,
                               cx + mouth_width / 2, mouth_y + mouth_height / 2,
                               start=200, extent=140, style=tk.ARC, outline=eye_color, width=6)

        # subtle side lights
        bar_h = max(4, int((y2 - y1) * 0.03))
        bar_len = (y2 - y1) * 0.34
        self.canvas.create_line(x1 + 14, cy - bar_len / 2, x1 + 14, cy + bar_len / 2, fill=eye_color, width=bar_h)
        self.canvas.create_line(x2 - 14, cy - bar_len / 2, x2 - 14, cy + bar_len / 2, fill=eye_color, width=bar_h)

        # Title text under visor
        self.canvas.create_text(cx, y2 + (h * 0.03),
                                text="SYMBA",
                                fill="#FFFFFF",
                                font=("Segoe UI", max(18, int(h * 0.04)), "bold"))

        # If sleeping, add small Zzz animation near top-right of visor
        if self.sleeping:
            zz_x = x2 - 60
            zz_y = y1 + 20
            # animate Z positions slightly
            self.sleep_z_phase += 1
            z1_y = zz_y - (self.sleep_z_phase % 20) * 0.6
            z2_y = zz_y - (self.sleep_z_phase % 40) * 0.45
            self.canvas.create_text(zz_x, z1_y, text="Z", font=("Segoe UI", 20), fill="#7a8b8f")
            self.canvas.create_text(zz_x + 18, z2_y, text="z", font=("Segoe UI", 14), fill="#65757b")

    def _round_rect(self, x1, y1, x2, y2, radius=25, **kwargs):
        points = [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1,
        ]
        self.canvas.create_polygon(points, smooth=True, **kwargs)

    def _animate(self):
        now = time.time()
        # blinking handled in draw
        if self.state == "speaking":
            self.mouth_phase += 1
        else:
            # decay mouth_phase slowly
            self.mouth_phase = max(0, self.mouth_phase - 0.8)

        self.glow_phase += 0.6
        self._draw_face()
        self.canvas.after(60, self._animate)


class SidePanel:
    """
    Fixed-width side panel that shows project info, team, QR and logs.
    """

    MODES = ("PROJETO", "EQUIPE", "QR", "LOGS")

    def __init__(self, parent, exit_callback):
        self.frame = tk.Frame(parent, bg="#050509", width=420)
        self.frame.pack(side=tk.RIGHT, fill=tk.Y)
        self.frame.pack_propagate(False)

        self.current_mode = "PROJETO"
        self.mode_cycle_index = 0
        self.cycle_enabled = True

        # header
        title = tk.Label(self.frame, text="Symbios – SENAC Taboão da Serra",
                         bg="#050509", fg="#FFFFFF", font=("Segoe UI", 20, "bold"),
                         justify="center", pady=10, wraplength=380)
        title.pack(fill=tk.X, pady=(18, 6))

        project = tk.Label(self.frame, text="Assistente de Voz Symba\nESP32-S3 + Xiaozhi",
                           bg="#050509", fg="#B0BEC5", font=("Segoe UI", 14),
                           justify="center", wraplength=380)
        project.pack(fill=tk.X, pady=(0, 8))

        ttk.Separator(self.frame, orient="horizontal").pack(fill=tk.X, padx=16, pady=6)

        # dynamic content area
        self.dynamic_frame = tk.Frame(self.frame, bg="#050509")
        self.dynamic_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=6)

        # logs text widget (used when mode=LOGS)
        self.logs_text = tk.Text(self.dynamic_frame, bg="#0E1114", fg="#D8DEE9",
                                 font=("Consolas", 11), relief=tk.FLAT)
        self.logs_scroll = ttk.Scrollbar(self.dynamic_frame, orient="vertical", command=self.logs_text.yview)
        self.logs_text.config(yscrollcommand=self.logs_scroll.set)
        self.log_buffer = []

        self._show_project_mode()

        ttk.Separator(self.frame, orient="horizontal").pack(fill=tk.X, padx=16, pady=6)

        btn_frame = tk.Frame(self.frame, bg="#050509")
        btn_frame.pack(fill=tk.X, padx=16, pady=(0, 10))

        btn_style = {
            "bg": "#151520",
            "fg": "#FFFFFF",
            "activebackground": "#263238",
            "activeforeground": "#FFFFFF",
            "relief": tk.FLAT,
            "padx": 8,
            "pady": 7,
            "font": ("Segoe UI", 12),
        }

        tk.Button(btn_frame, text="Projeto", command=lambda: self.set_mode("PROJETO"), **btn_style).pack(fill=tk.X, pady=3)
        tk.Button(btn_frame, text="Equipe", command=lambda: self.set_mode("EQUIPE"), **btn_style).pack(fill=tk.X, pady=3)
        tk.Button(btn_frame, text="QR + Links", command=lambda: self.set_mode("QR"), **btn_style).pack(fill=tk.X, pady=3)
        tk.Button(btn_frame, text="Logs", command=lambda: self.set_mode("LOGS"), **btn_style).pack(fill=tk.X, pady=(8, 3))

        tk.Button(btn_frame, text="Sair", command=exit_callback, bg="#111118", fg="#CFD8DC",
                  activebackground="#263238", activeforeground="#FFFFFF", relief=tk.FLAT,
                  padx=8, pady=6, font=("Segoe UI", 11)).pack(fill=tk.X, pady=(10, 2))

        footer = tk.Label(self.frame, text="Symbios • ESP32-S3 • Xiaozhi",
                          bg="#050509", fg="#9AA7B2", font=("Segoe UI", 10), pady=8)
        footer.pack(side=tk.BOTTOM, fill=tk.X)

    def clear_dynamic_frame(self):
        for w in self.dynamic_frame.winfo_children():
            w.destroy()

    def set_mode(self, mode: str):
        if mode not in self.MODES:
            return
        self.current_mode = mode
        self.cycle_enabled = mode != "LOGS"
        if mode == "PROJETO":
            self._show_project_mode()
        elif mode == "EQUIPE":
            self._show_team_mode()
        elif mode == "QR":
            self._show_qr_mode()
        elif mode == "LOGS":
            self._show_logs_mode()

    def _show_project_mode(self):
        self.clear_dynamic_frame()
        title = tk.Label(self.dynamic_frame, text="Sobre o Symbios", bg="#050509", fg="#FFFFFF",
                         font=("Segoe UI", 18, "bold"), anchor="nw", justify="left", wraplength=360)
        title.pack(anchor="nw", pady=(0, 8))
        desc = tk.Label(self.dynamic_frame,
                        text=("Symbios conecta pessoas à assistente de voz Symba\n"
                              "rodando em um ESP32-S3 com o firmware Xiaozhi.\n\n"
                              "• Comandos de voz em tempo real\n"
                              "• Respostas naturais e expressivas\n"
                              "• Visualização ampliada para apresentações"),
                        bg="#050509", fg="#CFD8DC", font=("Segoe UI", 14), justify="left", anchor="nw", wraplength=360)
        desc.pack(anchor="nw")

    def _show_team_mode(self):
        self.clear_dynamic_frame()
        title = tk.Label(self.dynamic_frame, text="Equipe", bg="#050509", fg="#FFFFFF",
                         font=("Segoe UI", 18, "bold"), anchor="nw", wraplength=360)
        title.pack(anchor="nw", pady=(0, 8))

        members = [
            "• Nome 1 – Função",
            "• Nome 2 – Função",
            "• Nome 3 – Função",
            "• Nome 4 – Função",
        ]
        for m in members:
            tk.Label(self.dynamic_frame, text=m, bg="#050509", fg="#CFD8DC", font=("Segoe UI", 14),
                     anchor="nw", wraplength=360).pack(anchor="nw")
        hint = tk.Label(self.dynamic_frame, text="\nAtualize com a equipe real.", bg="#050509", fg="#9AA7B2",
                        font=("Segoe UI", 12), anchor="nw", wraplength=360)
        hint.pack(anchor="nw")

    def _show_qr_mode(self):
        self.clear_dynamic_frame()
        title = tk.Label(self.dynamic_frame, text="Outros Projetos", bg="#050509", fg="#FFFFFF",
                         font=("Segoe UI", 18, "bold"), anchor="nw", wraplength=360)
        title.pack(anchor="nw", pady=(0, 8))

        desc = tk.Label(self.dynamic_frame, text="Aponte a câmera para o QR Code para acessar:",
                        bg="#050509", fg="#CFD8DC", font=("Segoe UI", 14), justify="left", anchor="nw", wraplength=360)
        desc.pack(anchor="nw", pady=(0, 10))

        qr_placeholder = tk.Label(self.dynamic_frame, text="QR CODE AQUI", bg="#0F1518", fg="#90CAF9",
                                  font=("Segoe UI", 15, "bold"), relief=tk.GROOVE, bd=1, padx=16, pady=36)
        qr_placeholder.pack(pady=6, fill=tk.X)

        info = tk.Label(self.dynamic_frame, text="GitHub da equipe, página do curso, portfólio e outros projetos.",
                        bg="#050509", fg="#9AA7B2", font=("Segoe UI", 13), justify="left", anchor="nw", wraplength=360)
        info.pack(anchor="nw", pady=(8, 0))

    def _show_logs_mode(self):
        self.clear_dynamic_frame()
        title = tk.Label(self.dynamic_frame, text="Logs do Sistema", bg="#050509", fg="#FFFFFF",
                         font=("Segoe UI", 16, "bold"), anchor="nw", wraplength=360)
        title.pack(anchor="nw", pady=(0, 6))

        self.logs_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=(4, 0))
        self.logs_scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=(4, 0))
        self.logs_text.config(state=tk.NORMAL)
        self.logs_text.delete("1.0", tk.END)
        for lvl, tag, txt in self.log_buffer:
            prefix = {"warn": "⚠️ ", "error": "❌ ", "state": "🎛 "}.get(lvl, "ℹ️ ")
            tag_str = f"[{tag}] " if tag else ""
            self.logs_text.insert(tk.END, f"{prefix}{tag_str}{txt}\n")
        self.logs_text.see(tk.END)
        self.logs_text.config(state=tk.DISABLED)

    def add_log(self, level, tag, text):
        self.log_buffer.append((level, tag, text))
        if self.current_mode == "LOGS":
            self.logs_text.config(state=tk.NORMAL)
            prefix = {"warn": "⚠️ ", "error": "❌ ", "state": "🎛 "}.get(level, "ℹ️ ")
            tag_str = f"[{tag}] " if tag else ""
            self.logs_text.insert(tk.END, f"{prefix}{tag_str}{text}\n")
            self.logs_text.see(tk.END)
            self.logs_text.config(state=tk.DISABLED)

    def cycle_mode(self):
        if not self.cycle_enabled:
            return
        self.mode_cycle_index = (self.mode_cycle_index + 1) % 3
        mode = ("PROJETO", "EQUIPE", "QR")[self.mode_cycle_index]
        self.set_mode(mode)


class StatusBar:
    def __init__(self, parent):
        self.frame = tk.Frame(parent, bg="#050509", height=36)
        self.frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.state_label = tk.Label(self.frame, text="Symba está pronta",
                                    bg="#050509", fg="#FFFFFF", font=("Segoe UI", 13), anchor="w")
        self.state_label.pack(side=tk.LEFT, padx=16)

        self.dot_label = tk.Label(self.frame, text="", bg="#050509", fg="#00E5FF",
                                  font=("Consolas", 12, "bold"), anchor="w")
        self.dot_label.pack(side=tk.LEFT)

        self.current_state = "idle"
        self.dot_phase = 0
        self.frame.after(350, self._animate)

    def set_state(self, state: str):
        self.current_state = state
        if state == "listening":
            text = "Symba está ouvindo"
        elif state == "speaking":
            text = "Symba está respondendo"
        elif state == "sleep":
            text = "Symba em modo descanso (sem conexão)"
        else:
            text = "Symba está pronta"
        self.state_label.config(text=text)

    def _animate(self):
        if self.current_state in ("listening", "speaking"):
            dots = "." * ((self.dot_phase % 3) + 1)
        else:
            dots = ""
        self.dot_label.config(text=dots)
        self.dot_phase += 1
        self.frame.after(350, self._animate)


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Symbios – Assistente de Voz Symba (ESP32-S3 + Xiaozhi)")
        self.root.configure(bg="#000000")
        self.root.attributes("-fullscreen", True)
        self.fullscreen = True

        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Escape>", self.exit_fullscreen)
        # Also handle resize to update wraplength
        self.root.bind("<Configure>", self._on_root_configure)

        # main layout
        self.main_frame = tk.Frame(self.root, bg="#000000")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.left_frame = tk.Frame(self.main_frame, bg="#020308")
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # face container
        self.face_container = tk.Frame(self.left_frame, bg="#020308")
        self.face_container.pack(fill=tk.BOTH, expand=True)
        self.face = FaceWidget(self.face_container)

        # text area (only last user and last full bot response)
        self.text_container = tk.Frame(self.left_frame, bg="#020308", height=260)
        self.text_container.pack(fill=tk.X, side=tk.BOTTOM)
        self.text_container.pack_propagate(False)

        # large wrap; will be updated on resize
        self.wrap_length = 1200

        self.user_label = tk.Label(self.text_container, text="", bg="#020308", fg="#7FD3FF",
                                   font=("Segoe UI", 20, "italic"), anchor="w", justify="left",
                                   wraplength=self.wrap_length)
        self.user_label.pack(fill=tk.X, padx=44, pady=(12, 4))

        # Use a disabled Text widget for bot responses to avoid label wrapping quirks
        self.bot_text_widget = tk.Text(self.text_container, bg="#020308", fg="#FFFFFF",
                                       font=("Segoe UI", 28, "bold"), wrap="word",
                                       relief=tk.FLAT, height=3)
        self.bot_text_widget.pack(fill=tk.BOTH, padx=44, pady=(0, 18))
        self.bot_text_widget.config(state=tk.DISABLED)

        # side panel and statusbar
        self.side_panel = SidePanel(self.main_frame, exit_callback=self.on_close)
        self.status_bar = StatusBar(self.root)

        # conversation state
        self.bot_text = ""
        self.in_bot_turn = False
        self.last_bot_line_time = 0.0
        self.last_activity_time = time.time()

        # serial
        self.ser = None
        self.reader_thread = None
        self.reader_running = False
        self.connecting_lock = threading.Lock()

        # start background serial connect loop
        threading.Thread(target=self._serial_connect_loop, daemon=True).start()

        # automatic side panel cycle
        self.root.after(SIDE_CYCLE_INTERVAL, self._side_cycle)

    def _on_root_configure(self, event):
        # Update wraplength proportionally to left_frame width when window resized
        try:
            left_width = self.left_frame.winfo_width()
            # subtract margins
            self.wrap_length = max(600, left_width - 180)
            self.user_label.config(wraplength=self.wrap_length)
            # text widget width handled by pack; font size large but wrap works
        except Exception:
            pass

    # Serial connection management
    def _serial_connect_loop(self):
        while True:
            if self.ser is None:
                self._try_connect_serial()
            time.sleep(RECONNECT_INTERVAL)

    def _try_connect_serial(self):
        with self.connecting_lock:
            try:
                self.ser = serial.Serial(PORT, BAUDRATE, timeout=1)
                self._on_serial_connected()
            except Exception as e:
                # keep face in sleep mode and show message
                self.ser = None
                self._set_disconnected(e)

    def _on_serial_connected(self):
        self._log("info", "SYSTEM", f"Conectado à porta {PORT} @ {BAUDRATE}")
        self.reader_running = True
        self.reader_thread = threading.Thread(target=self._serial_reader_loop, daemon=True)
        self.reader_thread.start()
        # ensure face and status reflect connection
        self.face.set_state("idle")
        self.status_bar.set_state("idle")
        self.last_activity_time = time.time()

    def _set_disconnected(self, err=None):
        msg = f"Não foi possível abrir porta {PORT}: {err}" if err else f"Desconectado ({PORT})"
        self._log("error", "SYSTEM", msg)
        # set sleeping face
        self.face.set_state("sleep")
        self.status_bar.set_state("sleep")
        self.face.sleeping = True

    def _serial_reader_loop(self):
        while self.reader_running and self.ser is not None:
            try:
                raw = self.ser.readline()
                if not raw:
                    # check idle -> possibly enter sleep after SLEEP_TIMEOUT
                    if time.time() - self.last_activity_time > SLEEP_TIMEOUT:
                        # go to sleep state
                        self.face.set_state("sleep")
                        self.status_bar.set_state("sleep")
                    time.sleep(0.01)
                    continue
                try:
                    line = raw.decode("utf-8", errors="ignore").strip()
                except Exception:
                    continue
                if not line:
                    continue
                self.last_activity_time = time.time()
                self.root.after(0, self._handle_serial_line, line)
            except Exception as e:
                # something happened, close and mark disconnected
                self._log("error", "SYSTEM", f"Erro leitura serial: {e}")
                try:
                    if self.ser:
                        self.ser.close()
                except Exception:
                    pass
                self.ser = None
                self.reader_running = False
                # set sleeping/disconnected UI
                self.face.set_state("sleep")
                self.status_bar.set_state("sleep")
                break

    # Serial line handling
    def _handle_serial_line(self, raw_line):
        parsed = parse_line(raw_line)
        t = parsed["type"]
        content = parsed["content"]
        tag = parsed["tag"]

        user_prefix = ">>"
        bot_prefix = "<<"
        is_user = user_prefix in content
        is_bot = bot_prefix in content
        clean_content = content.replace(user_prefix, "").replace(bot_prefix, "").strip()

        now = time.time()

        if is_user:
            # new user turn: clear pending bot turn and display user's text
            self.user_label.config(text=f"Você: {clean_content}")
            # start fresh bot turn afterwards
            self.bot_text = ""
            self._set_bot_text(self.bot_text)
            self.in_bot_turn = False
            self.last_bot_line_time = 0.0

            self.face.set_state("listening")
            self.status_bar.set_state("listening")
            self._log("info", tag or "Application", f"Usuário: {clean_content}")

        elif is_bot:
            # accumulate bot response; if more than timeout since last bot line, start new
            if (not self.in_bot_turn) or (now - self.last_bot_line_time) > BOT_TURN_TIMEOUT:
                # start new bot response
                self.bot_text = clean_content
                self.in_bot_turn = True
            else:
                # continuing previous response
                self.bot_text += ("\n" + clean_content)
            self.last_bot_line_time = now
            # update display
            self._set_bot_text(self.bot_text)

            self.face.set_state("speaking")
            self.status_bar.set_state("speaking")
            self._log("info", tag or "Application", f"Symba: {clean_content}")

        else:
            # states and logs
            if t == "state":
                self._log("state", tag, content)
                lc = content.lower()
                if "listening" in lc:
                    # firmware says listening -> stop bot turn
                    self.face.set_state("listening")
                    self.status_bar.set_state("listening")
                    self.in_bot_turn = False
                elif "speaking" in lc:
                    self.face.set_state("speaking")
                    self.status_bar.set_state("speaking")
                else:
                    self.face.set_state("idle")
                    self.status_bar.set_state("idle")
            elif t in ("info", "warn", "error"):
                self._log(t, tag, content)
            else:
                self._log("info", tag, content)

    # UI helpers
    def _set_bot_text(self, text):
        # set text in the disabled Text widget, preserving line breaks and avoiding layout flicker
        self.bot_text_widget.config(state=tk.NORMAL)
        self.bot_text_widget.delete("1.0", tk.END)
        self.bot_text_widget.insert(tk.END, text)
        self.bot_text_widget.config(state=tk.DISABLED)

    def _log(self, level, tag, text):
        # forward to side panel
        self.side_panel.add_log(level, tag, text)

    # side panel cycling
    def _side_cycle(self):
        try:
            self.side_panel.cycle_mode()
        finally:
            self.root.after(SIDE_CYCLE_INTERVAL, self._side_cycle)

    # app lifecycle
    def toggle_fullscreen(self, event=None):
        self.fullscreen = not self.fullscreen
        self.root.attributes("-fullscreen", self.fullscreen)

    def exit_fullscreen(self, event=None):
        self.fullscreen = False
        self.root.attributes("-fullscreen", False)

    def on_close(self):
        # stop serial reader gracefully
        self.reader_running = False
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
        self.root.destroy()


def main():
    root = tk.Tk()
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()