#!/usr/bin/env python3
# esp32_chat_ui.py
# WhatsApp-style simple chat UI for ESP32 TCP server (receiver).
# Connects as a TCP client to IP/PORT, sends lines, and displays received lines.
#
# Author: ChatGPT
# License: MIT

import socket
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
import os
import sys

DEFAULT_HOST = "172.20.10.3"
DEFAULT_PORT = 8080
LOG_DIR = os.path.join(os.path.expanduser("~"), ".esp32_chat_logs")
os.makedirs(LOG_DIR, exist_ok=True)

def now():
    return datetime.now().strftime("%H:%M:%S")

class TcpClient:
    def __init__(self, host, port, on_message, on_status):
        self.host = host
        self.port = int(port)
        self.on_message = on_message   # callback(str)
        self.on_status = on_status     # callback(str)
        self.sock = None
        self._rx_thread = None
        self._stop = threading.Event()
        self.lock = threading.Lock()

    def connect(self):
        with self.lock:
            if self.sock:
                return True
            try:
                self.on_status(f"Connecting to {self.host}:{self.port} ...")
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5)
                s.connect((self.host, self.port))
                s.settimeout(0.5)  # non-blocking-ish for recv loop
                self.sock = s
                self._stop.clear()
                self._rx_thread = threading.Thread(target=self._recv_loop, daemon=True)
                self._rx_thread.start()
                self.on_status("Connected")
                return True
            except Exception as e:
                self.on_status(f"Connect failed: {e}")
                self.sock = None
                return False

    def _recv_loop(self):
        buf = b""
        while not self._stop.is_set():
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    raise ConnectionError("Peer closed")
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    try:
                        text = line.decode("utf-8", errors="replace")
                    except:
                        text = line.decode("latin1", errors="replace")
                    # strip CR
                    text = text.rstrip("\r")
                    self.on_message(text)
            except (socket.timeout, BlockingIOError):
                continue
            except Exception as e:
                self.on_status(f"Disconnected: {e}")
                self.close()
                break

    def send_line(self, text):
        with self.lock:
            if not self.sock:
                raise ConnectionError("Not connected")
            data = (text + "\n").encode("utf-8")
            self.sock.sendall(data)

    def close(self):
        with self.lock:
            self._stop.set()
            if self.sock:
                try:
                    self.sock.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    self.sock.close()
                except Exception:
                    pass
            self.sock = None

class ChatUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ESP32 Chat UI")
        self.geometry("720x600")
        self.minsize(600, 480)

        self.host_var = tk.StringVar(value=DEFAULT_HOST)
        self.port_var = tk.StringVar(value=str(DEFAULT_PORT))
        self.autoconnect_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Disconnected")

        self.msg_queue = queue.Queue()
        self.status_queue = queue.Queue()
        self.client = None

        self._build_ui()
        self._setup_text_tags()

        self.after(100, self._drain_queues)

        # Optional auto-connect at startup
        self.bind("<Control-Return>", lambda e: self._send())
        self.bind("<Return>", lambda e: self._send())
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- UI ----------
    def _build_ui(self):
        top = ttk.Frame(self, padding=(10, 10, 10, 0))
        top.pack(fill="x")

        ttk.Label(top, text="ESP32 IP:").pack(side="left")
        ttk.Entry(top, textvariable=self.host_var, width=16).pack(side="left", padx=(5, 12))
        ttk.Label(top, text="Port:").pack(side="left")
        ttk.Entry(top, textvariable=self.port_var, width=6).pack(side="left", padx=(5, 12))

        self.connect_btn = ttk.Button(top, text="Connect", command=self._connect)
        self.connect_btn.pack(side="left", padx=(0, 6))
        ttk.Button(top, text="Disconnect", command=self._disconnect).pack(side="left")

        ttk.Checkbutton(top, text="Auto-connect", variable=self.autoconnect_var,
                        command=self._toggle_autoconnect).pack(side="left", padx=(12, 0))

        ttk.Button(top, text="Save Log", command=self._save_log).pack(side="right")

        # Chat area
        mid = ttk.Frame(self, padding=10)
        mid.pack(fill="both", expand=True)

        self.text = tk.Text(mid, wrap="word", state="disabled", spacing3=6)
        self.text_scroll = ttk.Scrollbar(mid, command=self.text.yview)
        self.text.configure(yscrollcommand=self.text_scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        self.text_scroll.pack(side="right", fill="y")

        # Entry area
        bottom = ttk.Frame(self, padding=(10, 0, 10, 10))
        bottom.pack(fill="x")
        self.entry = ttk.Entry(bottom)
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry.focus_set()
        ttk.Button(bottom, text="Send", command=self._send).pack(side="left")

        # Status bar
        status = ttk.Frame(self, padding=(10, 0, 10, 10))
        status.pack(fill="x")
        ttk.Label(status, textvariable=self.status_var).pack(side="left")

        # Apply a little style for a chat feel
        style = ttk.Style(self)
        try:
            self.call("tk", "scaling", 1.1)
        except Exception:
            pass
        if sys.platform == "win32":
            style.theme_use("vista")
        else:
            try:
                style.theme_use("clam")
            except Exception:
                pass

    def _setup_text_tags(self):
        # Tags for left/right aligned bubbles
        self.text.tag_configure("time", foreground="#888888", font=("Segoe UI", 8))
        self.text.tag_configure("me", lmargin1=200, lmargin2=200, spacing1=4, spacing3=6,
                                background="#DCF8C6")  # greenish bubble
        self.text.tag_configure("peer", rmargin=200, spacing1=4, spacing3=6,
                                background="#FFFFFF")  # white bubble
        self.text.tag_configure("me_wrap", lmargin1=200, lmargin2=200)
        self.text.tag_configure("peer_wrap", rmargin=200)

    # ---------- Networking ----------
    def _connect(self):
        host = self.host_var.get().strip()
        port = self.port_var.get().strip()
        if not host or not port.isdigit():
            messagebox.showerror("Error", "Please enter a valid IP and port.")
            return
        if self.client:
            self._disconnect()
        self.client = TcpClient(host, int(port), self._on_rx_line, self._on_status)
        ok = self.client.connect()
        if ok:
            self._append_system(f"Connected to {host}:{port}")
        else:
            self._append_system("Connection failed")

    def _disconnect(self):
        if self.client:
            self.client.close()
            self.client = None
            self._append_system("Disconnected")

    def _toggle_autoconnect(self):
        if self.autoconnect_var.get() and not self.client:
            self._connect()

    def _on_rx_line(self, line):
        self.msg_queue.put(("peer", line))

    def _on_status(self, text):
        self.status_queue.put(text)

    # ---------- UI helpers ----------
    def _append_system(self, text):
        self._append_text(f"[{now()}] {text}\n", ("time",))

    def _append_message(self, who, text):
        timestamp = f"{now()}"
        if who == "me":
            header = f"You  •  {timestamp}\n"
            self._append_text(header, ("time",))
            self._append_text(text + "\n", ("me", "me_wrap"))
        else:
            header = f"ESP32  •  {timestamp}\n"
            self._append_text(header, ("time",))
            self._append_text(text + "\n", ("peer", "peer_wrap"))
        # autoscroll
        self.text.see("end")

    def _append_text(self, content, tags=()):
        self.text.configure(state="normal")
        self.text.insert("end", content, tags)
        self.text.configure(state="disabled")

    def _drain_queues(self):
        # Messages from ESP32
        while True:
            try:
                who, line = self.msg_queue.get_nowait()
            except queue.Empty:
                break
            self._append_message(who, line)

        # Status updates
        while True:
            try:
                s = self.status_queue.get_nowait()
            except queue.Empty:
                break
            self.status_var.set(s)

            # auto-reconnect if enabled
            if "Disconnected" in s and self.autoconnect_var.get():
                self.after(1200, self._connect)

        # re-run
        self.after(80, self._drain_queues)

    # ---------- Actions ----------
    def _send(self):
        text = self.entry.get().strip()
        if not text:
            return
        try:
            if not self.client:
                raise ConnectionError("Not connected")
            self.client.send_line(text)
            self._append_message("me", text)
            self.entry.delete(0, "end")
        except Exception as e:
            messagebox.showwarning("Send failed", str(e))
            self._append_system(f"Send failed: {e}")

    def _save_log(self):
        # Export the current text content to a file
        content = self.text.get("1.0", "end").strip()
        if not content:
            messagebox.showinfo("Save Log", "No messages to save yet.")
            return
        fname_default = datetime.now().strftime("esp32_chat_%Y%m%d_%H%M%S.txt")
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialdir=LOG_DIR,
            initialfile=fname_default,
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content + "\n")
            messagebox.showinfo("Save Log", f"Saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Save Log", f"Failed to save:\n{e}")

    def on_close(self):
        try:
            if self.client:
                self.client.close()
        finally:
            self.destroy()

if __name__ == "__main__":
    app = ChatUI()
    # Optionally auto-connect on start:
    # app.autoconnect_var.set(True)
    # app._connect()
    app.mainloop()
