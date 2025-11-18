import re
import threading
import time
import random
import sys

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "Dependência faltando",
        "O módulo 'pyserial' não está instalado.\n\n"
        "No terminal, execute:\n"
        "python -m pip install pyserial"
    )
    sys.exit(1)

import tkinter as tk
from tkinter import ttk, messagebox

# parâmetros gerais
BOT_TURN_TIMEOUT = 3.0          # janela para agrupar linhas da IA
SLEEP_TIMEOUT = 20.0            # tempo parado até marcar como desconectada
SIDE_CYCLE_INTERVAL = 100_000   # troca automática de aba (Projeto/Equipe/QR)


# -------------------- parse de linha do ESP --------------------

regex_info = re.compile(r"^I\s*\((\d+)\)\s+(.+?):\s*(.*)")
regex_warn = re.compile(r"^W\s*\((\d+)\)\s+(.+?):\s*(.*)")
regex_error = re.compile(r"^E\s*\((\d+)\)\s+(.+?):\s*(.*)")


def parse_line(line: str):
    line = line.strip("\r\n")

    m = regex_info.match(line)
    if m:
        _ts, tag, msg = m.groups()
        return {"type": "info", "tag": tag, "content": msg}

    m = regex_warn.match(line)
    if m:
        _ts, tag, msg = m.groups()
        return {"type": "warn", "tag": tag, "content": msg}

    m = regex_error.match(line)
    if m:
        _ts, tag, msg = m.groups()
        return {"type": "error", "tag": tag, "content": msg}

    if "STATE:" in line:
        return {"type": "state", "tag": "STATE", "content": line}

    return {"type": "other", "tag": None, "content": line}


# -------------------- rosto da Alicia --------------------

class FaceWidget:
    def __init__(self, parent):
        self.canvas = tk.Canvas(parent, bg="#020308", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.estado = "sleep"  # idle | listening | speaking | sleep
        self.boca_fase = 0.0
        self.glow_fase = 0.0

        self.piscando = False
        self.ultimo_piscar = time.time()
        self.intervalo_piscar = 4.0
        self.intervalo_piscar_sono = 10.0

        self.particulas = []
        self._init_particulas()

        self.fala_ate = 0.0  # anima boca mais forte até este timestamp

        self.canvas.after(60, self._loop)

    def _init_particulas(self):
        self.particulas.clear()
        for _ in range(18):
            self.particulas.append(
                {
                    "x": random.random(),
                    "y": random.random(),
                    "r": random.uniform(1.5, 3.5),
                    "vy": random.uniform(0.001, 0.003),
                }
            )

    def set_estado(self, estado: str):
        self.estado = estado
        if estado == "speaking":
            self.boca_fase = 0.0

    def marcar_fala(self, segundos=2.0):
        agora = time.time()
        self.fala_ate = max(self.fala_ate, agora + segundos)

    def _loop(self):
        if self.estado == "speaking":
            self.boca_fase += 1.0
        else:
            self.boca_fase = max(0.0, self.boca_fase - 0.5)

        self.glow_fase += 0.6
        self._desenhar()
        self.canvas.after(60, self._loop)

    def _desenhar(self):
        self.canvas.delete("all")
        w = self.canvas.winfo_width() or 800
        h = self.canvas.winfo_height() or 450

        self._desenhar_fundo(w, h)
        self._desenhar_visor(w, h)

    def _desenhar_fundo(self, w, h):
        topo = (4, 9, 24)
        meio = (9, 10, 32)
        base = (6, 5, 16)
        passos = 7

        for i in range(passos):
            t = i / (passos - 1)
            if t < 0.5:
                a = t * 2
                r = int(topo[0] + (meio[0] - topo[0]) * a)
                g = int(topo[1] + (meio[1] - topo[1]) * a)
                b = int(topo[2] + (meio[2] - topo[2]) * a)
            else:
                a = (t - 0.5) * 2
                r = int(meio[0] + (base[0] - meio[0]) * a)
                g = int(meio[1] + (base[1] - meio[1]) * a)
                b = int(meio[2] + (base[2] - meio[2]) * a)
            self.canvas.create_rectangle(
                0,
                i * (h / passos),
                w,
                (i + 1) * (h / passos),
                fill=f"#{r:02x}{g:02x}{b:02x}",
                outline="",
            )

        for p in self.particulas:
            fator = 0.25 if self.estado == "sleep" else 1.0
            p["y"] -= p["vy"] * fator
            if p["y"] < 0:
                p["y"] = 1.0
                p["x"] = random.random()

            r = p["r"]
            x = p["x"] * w
            y = p["y"] * h
            self.canvas.create_oval(
                x - r, y - r, x + r, y + r, fill="#1B2B33", outline=""
            )

    def _round_rect(self, x1, y1, x2, y2, radius=25, **kwargs):
        pts = [
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
        self.canvas.create_polygon(pts, smooth=True, **kwargs)

    def _desenhar_visor(self, w, h):
        margem_x = w * 0.20
        margem_y = h * 0.18
        x1, y1 = margem_x, margem_y
        x2, y2 = w - margem_x, h - margem_y
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        raio = min(w, h) * 0.05

        if self.estado == "speaking":
            base = 78
        elif self.estado == "listening":
            base = 68
        else:
            base = 52
        brilho = base + int(24 * abs((self.glow_fase % 40) - 20) / 20)
        cor_borda = f"#{brilho:02x}{(brilho+30):02x}{(brilho+70):02x}"

        self._round_rect(
            x1, y1, x2, y2,
            radius=raio,
            fill="#050508",
            outline=cor_borda,
            width=5,
        )

        margem_int = max(6, int(min(w, h) * 0.01))
        self._round_rect(
            x1 + margem_int,
            y1 + margem_int,
            x2 - margem_int,
            y2 - margem_int,
            radius=max(8, raio - 6),
            fill="#020307",
            outline="",
        )

        if self.estado == "speaking":
            cor_olho = "#7CFF2F"
        elif self.estado == "listening":
            cor_olho = "#00E5FF"
        elif self.estado == "sleep":
            cor_olho = "#4E656F"
        else:
            cor_olho = "#4FFFB2"

        espacamento = (x2 - x1) * 0.34
        r_olho = min((x2 - x1), (y2 - y1)) * 0.11
        olho_esq = (cx - espacamento / 2, cy - r_olho * 0.25)
        olho_dir = (cx + espacamento / 2, cy - r_olho * 0.25)

        agora = time.time()
        intervalo = (
            self.intervalo_piscar_sono if self.estado == "sleep"
            else self.intervalo_piscar
        )
        if not self.piscando and (agora - self.ultimo_piscar) > intervalo:
            self.piscando = True
            self.ultimo_piscar = agora
        elif self.piscando and (agora - self.ultimo_piscar) > 0.18:
            self.piscando = False

        if self.estado == "sleep":
            for ex, ey in (olho_esq, olho_dir):
                self.canvas.create_line(
                    ex - r_olho * 0.9,
                    ey + 1,
                    ex + r_olho * 0.9,
                    ey + 1,
                    fill=cor_olho,
                    width=5,
                    capstyle=tk.ROUND,
                )
        else:
            if self.piscando:
                for ex, ey in (olho_esq, olho_dir):
                    self.canvas.create_line(
                        ex - r_olho,
                        ey,
                        ex + r_olho,
                        ey,
                        fill=cor_olho,
                        width=6,
                        capstyle=tk.ROUND,
                    )
            else:
                for ex, ey in (olho_esq, olho_dir):
                    self.canvas.create_oval(
                        ex - r_olho,
                        ey - r_olho,
                        ex + r_olho,
                        ey + r_olho,
                        outline=cor_olho,
                        width=5,
                    )
                    self.canvas.create_line(
                        ex - r_olho * 0.78,
                        ey,
                        ex + r_olho * 0.78,
                        ey,
                        fill=cor_olho,
                        width=5,
                        capstyle=tk.ROUND,
                    )

        largura_boca = (x2 - x1) * 0.48
        base_altura = (y2 - y1) * 0.22

        intensidade = 0.0
        if self.estado == "speaking":
            resto = self.fala_ate - agora
            intensidade = 0.65 if resto > 0 else 0.35
        elif self.estado == "listening":
            intensidade = 0.12
        elif self.estado == "sleep":
            intensidade = 0.05
        else:
            intensidade = 0.22

        amp = base_altura * intensidade
        altura = base_altura + amp * abs((self.boca_fase % 18) - 9) / 9
        y_boca = cy + r_olho * 1.4

        self.canvas.create_arc(
            cx - largura_boca / 2,
            y_boca - altura / 2,
            cx + largura_boca / 2,
            y_boca + altura / 2,
            start=200,
            extent=140,
            style=tk.ARC,
            outline=cor_olho,
            width=6,
        )

        h_barra = max(4, int((y2 - y1) * 0.03))
        comp_barra = (y2 - y1) * 0.34
        self.canvas.create_line(
            x1 + 14, cy - comp_barra / 2, x1 + 14, cy + comp_barra / 2,
            fill=cor_olho, width=h_barra,
        )
        self.canvas.create_line(
            x2 - 14, cy - comp_barra / 2, x2 - 14, cy + comp_barra / 2,
            fill=cor_olho, width=h_barra,
        )

        self.canvas.create_text(
            cx,
            y2 + h * 0.03,
            text="Alicia",
            fill="#FFFFFF",
            font=("Segoe UI", max(20, int(h * 0.04)), "bold"),
        )


# -------------------- painel lateral --------------------

class SidePanel:
    MODOS = ("PROJETO", "EQUIPE", "QR", "CONFIG")

    def __init__(self, parent, exit_cb):
        self.frame = tk.Frame(parent, bg="#050509", width=440)
        self.frame.pack(side=tk.RIGHT, fill=tk.Y)
        self.frame.pack_propagate(False)

        self.on_enter_config = None  # callback para atualizar portas

        titulo = tk.Label(
            self.frame,
            text="Alicia – Assistente de voz",
            bg="#050509",
            fg="#FFFFFF",
            font=("Segoe UI", 22, "bold"),
            wraplength=400,
            pady=10,
        )
        titulo.pack(fill=tk.X, pady=(18, 4))

        sub = tk.Label(
            self.frame,
            text="ESP32-S3 + Xiaozhi",
            bg="#050509",
            fg="#B0BEC5",
            font=("Segoe UI", 14),
            wraplength=400,
        )
        sub.pack(fill=tk.X)

        ttk.Separator(self.frame, orient="horizontal").pack(
            fill=tk.X, padx=16, pady=8
        )

        self.container = tk.Frame(self.frame, bg="#050509")
        self.container.pack(fill=tk.BOTH, expand=True, padx=16, pady=6)

        self.page_projeto = tk.Frame(self.container, bg="#050509")
        self.page_equipe = tk.Frame(self.container, bg="#050509")
        self.page_qr = tk.Frame(self.container, bg="#050509")
        self.page_config = tk.Frame(self.container, bg="#050509")

        for p in (self.page_projeto, self.page_equipe, self.page_qr, self.page_config):
            p.place(relx=0, rely=0, relwidth=1, relheight=1)

        self._build_projeto()
        self._build_equipe()
        self._build_qr()
        self._build_config()

        ttk.Separator(self.frame, orient="horizontal").pack(
            fill=tk.X, padx=16, pady=8
        )

        bf = tk.Frame(self.frame, bg="#050509")
        bf.pack(fill=tk.X, padx=16, pady=(0, 10))

        btn_style = {
            "bg": "#161824",
            "fg": "#FFFFFF",
            "activebackground": "#263238",
            "activeforeground": "#FFFFFF",
            "relief": tk.FLAT,
            "padx": 8,
            "pady": 7,
            "font": ("Segoe UI", 12),
        }

        tk.Button(bf, text="Projeto", command=lambda: self.set_modo("PROJETO"), **btn_style).pack(fill=tk.X, pady=3)
        tk.Button(bf, text="Equipe", command=lambda: self.set_modo("EQUIPE"), **btn_style).pack(fill=tk.X, pady=3)
        tk.Button(bf, text="QR + Links", command=lambda: self.set_modo("QR"), **btn_style).pack(fill=tk.X, pady=3)
        tk.Button(bf, text="Configurações", command=lambda: self.set_modo("CONFIG"), **btn_style).pack(fill=tk.X, pady=(8, 3))

        tk.Button(
            bf,
            text="Sair",
            command=exit_cb,
            bg="#111118",
            fg="#CFD8DC",
            activebackground="#263238",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            padx=8,
            pady=6,
            font=("Segoe UI", 11),
        ).pack(fill=tk.X, pady=(10, 2))


        self.modo = "PROJETO"
        self.idx_auto = 0
        self.auto = True
        self._raise_page(self.page_projeto)

    def _build_projeto(self):
        tk.Label(
            self.page_projeto,
            text="Sobre o projeto",
            bg="#050509",
            fg="#FFFFFF",
            font=("Segoe UI", 18, "bold"),
            anchor="nw",
            wraplength=380,
        ).pack(anchor="nw", pady=(0, 8))

        texto = (
            "Alicia é uma assistente de voz criada para ser uma opção mais acessível "
            "e personalizável do que os assistentes comerciais, usando ESP32-S3 e o "
            "firmware Xiaozhi.\n\n"
            "Na prática, o usuário pode:\n"
            "• Falar comandos (como faria com uma Alexa ou Google Assistente);\n"
            "• Receber respostas de IA diretamente no dispositivo;\n"
            "• Integrar a assistente com luzes, sensores, portas, ventiladores e outros "
            "dispositivos do ambiente;\n"
            "• Adaptar o comportamento da IA ao contexto de uso ou gostos pessoais.\n\n"
        )

        tk.Label(
            self.page_projeto,
            text=texto,
            bg="#050509",
            fg="#CFD8DC",
            font=("Segoe UI", 13),
            anchor="nw",
            justify="left",
            wraplength=380,
        ).pack(anchor="nw")

    def _build_equipe(self):
        tk.Label(
            self.page_equipe,
            text="Equipe",
            bg="#050509",
            fg="#FFFFFF",
            font=("Segoe UI", 18, "bold"),
            anchor="nw",
        ).pack(anchor="nw", pady=(0, 8))

        membros = [
            "• Josiel de Souza – Suporte de software",
            "• Thiago – Suporte de software",
            "• Cauan – Montagem e apoio técnico",
        ]
        for m in membros:
            tk.Label(
                self.page_equipe,
                text=m,
                bg="#050509",
                fg="#CFD8DC",
                font=("Segoe UI", 13),
                anchor="nw",
                wraplength=380,
            ).pack(anchor="nw")

    def _build_qr(self):
        tk.Label(
            self.page_qr,
            text="Outros projetos",
            bg="#050509",
            fg="#FFFFFF",
            font=("Segoe UI", 18, "bold"),
            anchor="nw",
        ).pack(anchor="nw", pady=(0, 8))

        tk.Label(
            self.page_qr,
            text="Aponte a câmera para o QR Code para conhecer nossos outros "
                 "projetos:",
            bg="#050509",
            fg="#CFD8DC",
            font=("Segoe UI", 13),
            anchor="nw",
            wraplength=380,
        ).pack(anchor="nw", pady=(0, 8))

        tk.Label(
            self.page_qr,
            text="QR CODE AQUI",
            bg="#0F1518",
            fg="#90CAF9",
            font=("Segoe UI", 15, "bold"),
            relief=tk.GROOVE,
            bd=1,
            padx=16,
            pady=36,
        ).pack(fill=tk.X, pady=6)


    def _build_config(self):
        tk.Label(
            self.page_config,
            text="Configurações",
            bg="#050509",
            fg="#FFFFFF",
            font=("Segoe UI", 18, "bold"),
            anchor="nw",
        ).pack(anchor="nw", pady=(0, 6))

        self.config_serial_host = tk.Frame(self.page_config, bg="#050509")
        self.config_serial_host.pack(fill=tk.X, pady=(4, 10))

        tk.Label(
            self.page_config,
            text="Logs",
            bg="#050509",
            fg="#FFFFFF",
            font=("Segoe UI", 14, "bold"),
            anchor="nw",
        ).pack(anchor="nw", pady=(8, 2))

        logs_container = tk.Frame(self.page_config, bg="#050509")
        logs_container.pack(fill=tk.BOTH, expand=True)

        self.text_logs = tk.Text(
            logs_container,
            bg="#0E1114",
            fg="#D8DEE9",
            font=("Consolas", 11),
            relief=tk.FLAT,
        )
        scroll = ttk.Scrollbar(
            logs_container, orient="vertical", command=self.text_logs.yview
        )
        self.text_logs.config(yscrollcommand=scroll.set)

        self.text_logs.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=(4, 0))
        scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=(4, 0))

        self.text_logs.config(state=tk.DISABLED)
        self.buffer_logs = []

    def set_modo(self, modo: str):
        if modo not in self.MODOS:
            return
        self.modo = modo
        self.auto = modo not in ("CONFIG",)

        if modo == "PROJETO":
            self._raise_page(self.page_projeto)
        elif modo == "EQUIPE":
            self._raise_page(self.page_equipe)
        elif modo == "QR":
            self._raise_page(self.page_qr)
        else:
            if callable(self.on_enter_config):
                self.on_enter_config()
            self._raise_page(self.page_config)

    def _raise_page(self, page):
        page.tkraise()

    def add_log(self, nivel, tag, msg):
        self.buffer_logs.append((nivel, tag, msg))
        if self.modo == "CONFIG":
            self.text_logs.config(state=tk.NORMAL)
            pref = {"warn": "⚠️ ", "error": "❌ ", "state": "🎛 "}.get(nivel, "ℹ️ ")
            tag_str = f"[{tag}] " if tag else ""
            self.text_logs.insert(tk.END, f"{pref}{tag_str}{msg}\n")
            self.text_logs.see(tk.END)
            self.text_logs.config(state=tk.DISABLED)

    def ciclo_auto(self):
        if not self.auto:
            return
        self.idx_auto = (self.idx_auto + 1) % 3
        self.set_modo(("PROJETO", "EQUIPE", "QR")[self.idx_auto])


# -------------------- status bar --------------------

class StatusBar:
    def __init__(self, parent):
        self.frame = tk.Frame(parent, bg="#050509", height=32)
        self.frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.lbl = tk.Label(
            self.frame,
            text="Alicia desconectada",
            bg="#050509",
            fg="#FFFFFF",
            font=("Segoe UI", 13),
            anchor="w",
        )
        self.lbl.pack(side=tk.LEFT, padx=16)

        self.lbl_dots = tk.Label(
            self.frame,
            text="",
            bg="#050509",
            fg="#00E5FF",
            font=("Consolas", 12, "bold"),
            anchor="w",
        )
        self.lbl_dots.pack(side=tk.LEFT)

        self.estado = "sleep"
        self.fase = 0
        self.frame.after(350, self._loop)

    def set_estado(self, estado: str):
        self.estado = estado
        if estado == "listening":
            txt = "Alicia está ouvindo"
        elif estado == "speaking":
            txt = "Alicia está respondendo"
        elif estado == "sleep":
            txt = "Alicia desconectada"
        else:
            txt = "Alicia pronta"
        self.lbl.config(text=txt)

    def _loop(self):
        if self.estado in ("listening", "speaking"):
            dots = "." * ((self.fase % 3) + 1)
        else:
            dots = ""
        self.lbl_dots.config(text=dots)
        self.fase += 1
        self.frame.after(350, self._loop)


# -------------------- app principal --------------------

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Alicia – Assistente de voz (ESP32-S3 + Xiaozhi)")
        self.root.configure(bg="#000000")
        self.root.attributes("-fullscreen", True)
        self.fullscreen = True

        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Escape>", self.sair_fullscreen)
        self.root.bind("<Configure>", self._on_resize)

        self.main = tk.Frame(self.root, bg="#000000")
        self.main.pack(fill=tk.BOTH, expand=True)

        self.left = tk.Frame(self.main, bg="#020308")
        self.left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.face_frame = tk.Frame(self.left, bg="#020308")
        self.face_frame.pack(fill=tk.BOTH, expand=True)
        self.face = FaceWidget(self.face_frame)
        self.face.set_estado("sleep")

        self.text_frame = tk.Frame(self.left, bg="#020308", height=260)
        self.text_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.text_frame.pack_propagate(False)

        self.wrap_len = 1200
        self.lbl_user = tk.Label(
            self.text_frame,
            text="",
            bg="#020308",
            fg="#7FD3FF",
            font=("Segoe UI", 20, "italic"),
            anchor="w",
            wraplength=self.wrap_len,
        )
        self.lbl_user.pack(fill=tk.X, padx=44, pady=(12, 4))

        self.txt_ia = tk.Text(
            self.text_frame,
            bg="#020308",
            fg="#FFFFFF",
            font=("Segoe UI", 28, "bold"),
            wrap="word",
            relief=tk.FLAT,
            height=3,
        )
        self.txt_ia.pack(fill=tk.BOTH, padx=44, pady=(0, 18))
        self.txt_ia.config(state=tk.DISABLED)

        self.side_panel = SidePanel(self.main, exit_cb=self.on_close)
        self.side_panel.on_enter_config = self._atualizar_portas
        self.status_bar = StatusBar(self.root)
        self.status_bar.set_estado("sleep")

        self._montar_serial_ui(self.side_panel.config_serial_host)

        self.texto_ia = ""
        self.em_resposta = False
        self.ultimo_bot = 0.0
        self.ultimo_atividade = time.time()

        self.ser = None
        self.reader_thread = None
        self.reader_running = False
        self.serial_lock = threading.Lock()

        self.root.after(SIDE_CYCLE_INTERVAL, self._ciclo_painel)

    # --- UI de serial ---

    def _montar_serial_ui(self, parent):
        frame = tk.Frame(parent, bg="#050509")
        frame.pack(fill=tk.X)

        tk.Label(
            frame, text="Conexão serial", bg="#050509", fg="#FFFFFF",
            font=("Segoe UI", 12, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))

        tk.Label(
            frame, text="Porta:", bg="#050509", fg="#CFD8DC",
            font=("Segoe UI", 10),
        ).grid(row=1, column=0, sticky="w")

        self.cb_port = ttk.Combobox(frame, width=16, state="readonly")
        self.cb_port.grid(row=1, column=1, padx=4)

        tk.Button(
            frame, text="Atualizar",
            command=self._atualizar_portas,
            bg="#222532", fg="#FFFFFF",
            activebackground="#263238",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 9),
            padx=4, pady=2,
        ).grid(row=1, column=2, padx=4)

        tk.Label(
            frame, text="Baud:", bg="#050509", fg="#CFD8DC",
            font=("Segoe UI", 10),
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))

        self.cb_baud = ttk.Combobox(
            frame, width=16, state="readonly",
            values=["9600", "19200", "38400", "57600", "115200"],
        )
        self.cb_baud.grid(row=2, column=1, padx=4, pady=(4, 2))
        self.cb_baud.set("115200")

        self.btn_connect = tk.Button(
            frame, text="Conectar",
            command=self.conectar_serial,
            bg="#1B5E20", fg="#FFFFFF",
            activebackground="#2E7D32",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 10),
            padx=8, pady=2,
        )
        self.btn_connect.grid(row=3, column=0, columnspan=2, pady=(6, 4), sticky="we")

        self.btn_disconnect = tk.Button(
            frame, text="Desconectar",
            command=self.desconectar_serial,
            bg="#B71C1C", fg="#FFFFFF",
            activebackground="#C62828",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 10),
            padx=8, pady=2,
            state=tk.DISABLED,
        )
        self.btn_disconnect.grid(row=3, column=2, pady=(6, 4), sticky="we")

        self._atualizar_portas()
        self._sync_serial_buttons(False)

    def _atualizar_portas(self):
        ports = serial.tools.list_ports.comports()
        names = [p.device for p in ports]
        self.cb_port["values"] = names
        if names and not self.cb_port.get():
            self.cb_port.set(names[0])

    def _sync_serial_buttons(self, connected: bool):
        if connected:
            self.btn_connect.config(state=tk.DISABLED)
            self.btn_disconnect.config(state=tk.NORMAL)
        else:
            self.btn_connect.config(state=tk.NORMAL)
            self.btn_disconnect.config(state=tk.DISABLED)

    # --- serial ---

    def conectar_serial(self):
        port = self.cb_port.get()
        if not port:
            messagebox.showwarning("Serial", "Selecione uma porta.")
            return

        try:
            baud = int(self.cb_baud.get())
        except ValueError:
            messagebox.showwarning("Serial", "Baud inválido.")
            return

        with self.serial_lock:
            try:
                if self.ser and self.ser.is_open:
                    self.ser.close()
                self.ser = serial.Serial(port, baud, timeout=1)
            except Exception as e:
                messagebox.showerror("Serial", f"Erro ao abrir {port}: {e}")
                self._log("error", "SYSTEM", f"Erro ao abrir {port}: {e}")
                self.face.set_estado("sleep")
                self.status_bar.set_estado("sleep")
                self._sync_serial_buttons(False)
                return

            self._log("info", "SYSTEM", f"Conectado em {port} @ {baud}")
            self.reader_running = True
            self.reader_thread = threading.Thread(
                target=self._serial_loop, daemon=True
            )
            self.reader_thread.start()

        self._sync_serial_buttons(True)
        self.face.set_estado("idle")
        self.status_bar.set_estado("idle")
        self.ultimo_atividade = time.time()

    def desconectar_serial(self):
        with self.serial_lock:
            self.reader_running = False
            if self.ser:
                try:
                    self.ser.close()
                except Exception:
                    pass
                self.ser = None

        self._log("info", "SYSTEM", "Serial desconectada.")
        self._sync_serial_buttons(False)
        self.face.set_estado("sleep")
        self.status_bar.set_estado("sleep")

    def _serial_loop(self):
        while self.reader_running and self.ser is not None:
            try:
                raw = self.ser.readline()
                if not raw:
                    if time.time() - self.ultimo_atividade > SLEEP_TIMEOUT:
                        self.face.set_estado("sleep")
                        self.status_bar.set_estado("sleep")
                    time.sleep(0.01)
                    continue

                try:
                    line = raw.decode("utf-8", errors="ignore").strip()
                except Exception:
                    continue

                if not line:
                    continue

                self.ultimo_atividade = time.time()
                self.root.after(0, self._handle_line, line)

            except Exception as e:
                self._log("error", "SYSTEM", f"Erro na serial: {e}")
                with self.serial_lock:
                    try:
                        if self.ser:
                            self.ser.close()
                    except Exception:
                        pass
                    self.ser = None
                    self.reader_running = False
                self.root.after(0, self._serial_down)
                break

    def _serial_down(self):
        self._sync_serial_buttons(False)
        self.face.set_estado("sleep")
        self.status_bar.set_estado("sleep")

    # --- tratamento de linha ---

    def _handle_line(self, line: str):
        parsed = parse_line(line)
        tipo = parsed["type"]
        msg = parsed["content"]
        tag = parsed["tag"]

        pref_user = ">>"
        pref_bot = "<<"

        is_user = pref_user in msg
        is_bot = pref_bot in msg
        txt = msg.replace(pref_user, "").replace(pref_bot, "").strip()

        agora = time.time()

        if is_user:
            self.lbl_user.config(text=f"Você: {txt}")
            self.texto_ia = ""
            self._set_ia("")
            self.em_resposta = False
            self.ultimo_bot = 0.0

            self.face.set_estado("listening")
            self.status_bar.set_estado("listening")
            self._log("info", tag or "APP", f"Usuário: {txt}")
            return

        if is_bot:
            if (not self.em_resposta) or (agora - self.ultimo_bot) > BOT_TURN_TIMEOUT:
                self.texto_ia = txt
                self.em_resposta = True
            else:
                self.texto_ia += "\n" + txt
            self.ultimo_bot = agora
            self._set_ia(self.texto_ia)

            self.face.set_estado("speaking")
            self.status_bar.set_estado("speaking")
            self.face.marcar_fala(2.5)

            self._log("info", tag or "APP", f"Alicia: {txt}")
            return

        if tipo == "state":
            self._log("state", tag, msg)
            low = msg.lower()
            if "listening" in low:
                self.face.set_estado("listening")
                self.status_bar.set_estado("listening")
                self.em_resposta = False
            elif "speaking" in low:
                self.face.set_estado("speaking")
                self.status_bar.set_estado("speaking")
                self.face.marcar_fala(1.5)
            else:
                self.face.set_estado("idle")
                self.status_bar.set_estado("idle")
        elif tipo in ("info", "warn", "error"):
            self._log(tipo, tag, msg)
        else:
            self._log("info", tag, msg)

    # --- helpers GUI ---

    def _set_ia(self, txt: str):
        self.txt_ia.config(state=tk.NORMAL)
        self.txt_ia.delete("1.0", tk.END)
        self.txt_ia.insert(tk.END, txt)
        self.txt_ia.config(state=tk.DISABLED)

    def _log(self, nivel, tag, msg):
        self.side_panel.add_log(nivel, tag, msg)

    def _ciclo_painel(self):
        self.side_panel.ciclo_auto()
        self.root.after(SIDE_CYCLE_INTERVAL, self._ciclo_painel)

    def _on_resize(self, _event):
        try:
            w = self.left.winfo_width()
            self.wrap_len = max(600, w - 180)
            self.lbl_user.config(wraplength=self.wrap_len)
        except Exception:
            pass

    def toggle_fullscreen(self, _event=None):
        self.fullscreen = not self.fullscreen
        self.root.attributes("-fullscreen", self.fullscreen)

    def sair_fullscreen(self, _event=None):
        self.fullscreen = False
        self.root.attributes("-fullscreen", False)

    def on_close(self):
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
