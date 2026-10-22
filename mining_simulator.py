"""Blockchain 挖礦模擬器

不斷產生隨機字串 → SHA-256 → 比對雜湊的前 N 個位元是否等於使用者設定的目標。
"""
import hashlib
import queue
import random
import re
import string
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

ALPHABET = string.ascii_letters + string.digits + "!@#$%&*?"
INPUT_LEN = 10          # 隨機 input 長度
BATCH = 4096            # 每批嘗試次數（批與批之間檢查停止旗標、回報樣本）
TABLE_ROWS = 100        # 表格最多保留幾列
POLL_MS = 100           # GUI 更新間隔（毫秒）

FONT = ("Microsoft JhengHei", 10)
FONT_BOLD = ("Microsoft JhengHei", 10, "bold")
MONO = ("Consolas", 10)
YELLOW = "#FFFFC0"


def to_bin(digest: bytes) -> str:
    """把 32 bytes 的雜湊轉成 256 位的 0/1 字串。"""
    return format(int.from_bytes(digest, "big"), "0256b")


class Miner(threading.Thread):
    """背景挖礦執行緒，避免 GUI 卡住。"""

    def __init__(self, target_bits: str, events: queue.Queue, stop_event: threading.Event):
        super().__init__(daemon=True)
        k = len(target_bits)
        self.nbytes = (k + 7) // 8              # 只需要取雜湊前幾個 byte 來比
        self.shift = self.nbytes * 8 - k        # 再右移掉多出來的位元
        self.target = int(target_bits, 2)
        self.events = events
        self.stop_event = stop_event
        self.tries = 0
        self.hit_time = None

    def run(self):
        # 區域變數化，迴圈內少做屬性查找，速度快不少
        sha256 = hashlib.sha256
        choices = random.choices
        join = "".join
        from_bytes = int.from_bytes
        alphabet, n = ALPHABET, INPUT_LEN
        nbytes, shift, target = self.nbytes, self.shift, self.target

        while not self.stop_event.is_set():
            for i in range(BATCH):
                s = join(choices(alphabet, k=n))
                d = sha256(s.encode()).digest()
                # 用整數比對前 k 位，不必每次都轉成 0/1 字串
                if from_bytes(d[:nbytes], "big") >> shift == target:
                    self.hit_time = time.perf_counter()
                    self.tries += i + 1
                    self.events.put(("hit", s, d))
                    return
            self.tries += BATCH
            self.events.put(("sample", s, d))   # 每批回報一筆給表格顯示


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Blockchain 挖礦模擬器")
        self.geometry("1000x740")
        self.minsize(820, 660)
        self.option_add("*Font", FONT)

        self.events: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.miner: Miner | None = None
        self.base_tries = 0          # 之前幾次「開始→停止」累積的次數
        self.base_elapsed = 0.0      # 之前累積的秒數
        self.run_start = None
        self.active_target = None
        self.found = False

        self._build()
        self._set_running(False)
        self._update_stats()
        self.after(POLL_MS, self._poll)

    # ---------- 版面 ----------
    def _build(self):
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)

        # 設定目標
        top = ttk.Frame(outer)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text="設定目標：", font=FONT_BOLD).grid(row=0, column=0, padx=(0, 6))
        self.target_var = tk.StringVar(value="000001111101010101010000010101")
        self.target_var.trace_add("write", lambda *_: self._on_target_change())
        self.target_entry = tk.Entry(top, textvariable=self.target_var, font=MONO)
        self.target_entry.grid(row=0, column=1, sticky="ew", ipady=3)
        self.len_label = ttk.Label(top, width=10)
        self.len_label.grid(row=0, column=2, padx=(6, 0))
        self._on_target_change()

        # 控制區
        ctrl = ttk.LabelFrame(outer, text="控制", padding=10)
        ctrl.grid(row=1, column=0, sticky="nsw", padx=(0, 10))
        self.btn_start = ttk.Button(ctrl, text="開始挖礦", command=self._start, width=16)
        self.btn_stop = ttk.Button(ctrl, text="停止", command=self._stop, width=16)
        self.btn_clear = ttk.Button(ctrl, text="清除", command=self._clear, width=16)
        for b in (self.btn_start, self.btn_stop, self.btn_clear):
            b.pack(pady=4, ipady=3)
        self.stats_label = ttk.Label(ctrl, justify="center")
        self.stats_label.pack(pady=(14, 0))

        # Input / Hash 表格
        right = ttk.Frame(outer)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        style = ttk.Style(self)
        style.configure("Treeview", font=MONO, rowheight=22)
        style.configure("Treeview.Heading", font=FONT_BOLD)
        self.tree = ttk.Treeview(right, columns=("input", "hash"), show="headings", height=10)
        self.tree.heading("input", text="Input")
        self.tree.heading("hash", text="Hash（二進位）")
        self.tree.column("input", width=120, stretch=False)
        self.tree.column("hash", width=2150, stretch=False)
        ys = ttk.Scrollbar(right, orient="vertical", command=self.tree.yview)
        xs = ttk.Scrollbar(right, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        self.status_label = tk.Label(right, font=FONT_BOLD)
        self.status_label.grid(row=2, column=0, pady=(6, 0))

        # 命中橫幅
        self.banner = tk.Label(outer, text="命中目標（挖到！）", font=("Microsoft JhengHei", 12, "bold"),
                               relief="groove", bd=2, pady=6)
        self.banner.grid(row=2, column=0, columnspan=2, sticky="ew", pady=10)
        self._banner_off()

        # 結果
        res = ttk.Frame(outer)
        res.grid(row=3, column=0, columnspan=2, sticky="ew")
        res.columnconfigure(1, weight=1)

        def ro_entry(parent):
            return tk.Entry(parent, font=MONO, state="readonly", readonlybackground=YELLOW)

        self.res_vars = {k: tk.StringVar() for k in ("tries", "secs", "input")}
        ttk.Label(res, text="共測試").grid(row=0, column=0, sticky="w")
        e = ro_entry(res); e.configure(textvariable=self.res_vars["tries"])
        e.grid(row=0, column=1, sticky="ew", pady=3, ipady=2)
        ttk.Label(res, text="組資料").grid(row=0, column=2, sticky="w", padx=6)

        ttk.Label(res, text="共花費").grid(row=1, column=0, sticky="w")
        e = ro_entry(res); e.configure(textvariable=self.res_vars["secs"])
        e.grid(row=1, column=1, sticky="ew", pady=3, ipady=2)
        ttk.Label(res, text="秒").grid(row=1, column=2, sticky="w", padx=6)

        ttk.Label(res, text="命中的 input 為：").grid(row=2, column=0, sticky="w")
        e = ro_entry(res); e.configure(textvariable=self.res_vars["input"])
        e.grid(row=2, column=1, columnspan=2, sticky="ew", pady=3, ipady=2)

        ttk.Label(res, text="其 Hash Value：").grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.hash_text = tk.Text(res, height=6, font=MONO, bg=YELLOW, wrap="char", state="disabled")
        self.hash_text.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(2, 0))

    # ---------- 狀態 ----------
    def _on_target_change(self):
        n = len(self.target_var.get().strip())
        self.len_label.configure(text=f"（{n} 位數）")

    def _set_running(self, running: bool):
        self.btn_start.configure(state="disabled" if running else "normal")
        self.btn_stop.configure(state="normal" if running else "disabled")
        self.target_entry.configure(state="disabled" if running else "normal")
        if running:
            self.status_label.configure(text="（啟動狀態）", fg="#C00000")
        else:
            self.status_label.configure(text="（停止狀態）", fg="#808080")

    def _banner_off(self):
        self.banner.configure(bg="#DDDDDD", fg="#999999")

    def _banner_on(self):
        self.banner.configure(bg="#2E7D32", fg="white")

    def _current(self):
        tries = self.base_tries + (self.miner.tries if self.miner else 0)
        elapsed = self.base_elapsed
        if self.run_start is not None:
            elapsed += time.perf_counter() - self.run_start
        return tries, elapsed

    def _update_stats(self):
        tries, elapsed = self._current()
        rate = tries / elapsed if elapsed > 0 else 0
        self.stats_label.configure(
            text=f"已嘗試 {tries:,} 次\n耗時 {elapsed:,.2f} 秒\n速率 {rate:,.0f} hash/s")

    def _reset_counters(self):
        self.base_tries = 0
        self.base_elapsed = 0.0
        self.found = False
        self.tree.delete(*self.tree.get_children())
        for v in self.res_vars.values():
            v.set("")
        self._set_hash_text("")
        self._banner_off()

    def _set_hash_text(self, text):
        self.hash_text.configure(state="normal")
        self.hash_text.delete("1.0", "end")
        self.hash_text.insert("1.0", text)
        self.hash_text.configure(state="disabled")

    # ---------- 按鈕 ----------
    def _start(self):
        target = self.target_var.get().strip()
        if not re.fullmatch(r"[01]{1,256}", target):
            messagebox.showwarning("目標格式錯誤", "目標只能是 0 和 1，長度 1～256 位。")
            return
        # 換了目標或上次已挖到 → 重新計算；否則延續上次停止時的進度
        if target != self.active_target or self.found:
            self._reset_counters()
        self.active_target = target

        self.stop_event = threading.Event()
        self.miner = Miner(target, self.events, self.stop_event)
        self.run_start = time.perf_counter()
        self.miner.start()
        self._set_running(True)

    def _stop(self, end_time=None):
        if self.miner is None:
            return
        self.stop_event.set()
        end = end_time or time.perf_counter()
        self.base_tries += self.miner.tries
        self.base_elapsed += end - self.run_start
        self.miner = None
        self.run_start = None
        self._set_running(False)
        self._update_stats()

    def _clear(self):
        self._stop()
        self.active_target = None
        self._reset_counters()
        self._update_stats()

    # ---------- 定時更新 ----------
    def _poll(self):
        samples = []
        try:
            while True:
                ev = self.events.get_nowait()
                if ev[0] == "sample":
                    if self.miner is not None:
                        samples.append(ev)
                else:
                    self._on_hit(ev[1], ev[2])
        except queue.Empty:
            pass

        for _, s, d in samples[-10:]:          # 每次最多插 10 列，避免拖慢介面
            self.tree.insert("", 0, values=(s, to_bin(d)))
        rows = self.tree.get_children()
        if len(rows) > TABLE_ROWS:
            self.tree.delete(*rows[TABLE_ROWS:])

        self._update_stats()
        self.after(POLL_MS, self._poll)

    def _on_hit(self, s: str, d: bytes):
        if self.miner is not None:
            self._stop(end_time=self.miner.hit_time)
        self.found = True
        self.tree.insert("", 0, values=(s, to_bin(d)))
        self.res_vars["tries"].set(f"{self.base_tries:,}")
        self.res_vars["secs"].set(f"{self.base_elapsed:.2f}")
        self.res_vars["input"].set(s)
        self._set_hash_text(f"[Binary]\n{to_bin(d)}\n\n[Hex]\n{d.hex()}")
        self._banner_on()
        self.bell()


if __name__ == "__main__":
    App().mainloop()
