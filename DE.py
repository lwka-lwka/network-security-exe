# -*- coding: utf-8 -*-
"""
通訊及網路安全 — DE（差值擴張）數字資料竄改偵測實作（視窗版）

執行：python3 DE.py

操作流程
  1. 按「選擇檔案」→ 選老師的測試數據(原始資料).xlsx
  2. 按「① 嵌入」→ 每兩個數字一組，用 DE 擴張兩次嵌入驗證訊號 00
       - 產生「測試數據(原始資料)_DE嵌入.xlsx」（數值已擴張；老師的原始檔不會被動到）
       - 左邊顯示：修改前擷取出的圖（全黑）
       - 會自動用 Numbers / Excel 打開嵌入後的檔案
  3. 在 Numbers / Excel 裡直接改幾個數字，存檔
       （Numbers 會存成 .numbers 也沒關係，程式兩種都讀得到）
  4. 回到視窗按「② 檢查」→ 右邊顯示擷取出的圖：白點 = 被改過的數值對，
       下方文字說明哪些地方被改過
  5. （可選）按「③ 存還原檔」→ 把數值還原成原始資料存檔

DE 公式（每擴張一次嵌入 1 bit b）
    m = ⌊(x+y)/2⌋,  d = x − y,  d' = 2d + b
    x' = m + ⌊(d'+1)/2⌋,  y' = m − ⌊d'/2⌋
  擴張兩次嵌入 00 → d'' = 4d，合法的 d'' 一定是 4 的倍數
  擷取：m 不變；b = d' mod 2, d = ⌊d'/2⌋（做兩次）；還原 x = m + ⌊(d+1)/2⌋, y = m − ⌊d/2⌋
  數字資料沒有 0~255 的上下限，不會溢位，所以不需要 Location Map

需要的套件：pandas numpy matplotlib openpyxl xlsxwriter
讀 .numbers 檔另外需要：python3 -m pip install numbers-parser
"""
import json
import os
import subprocess
import sys
from decimal import Decimal

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
import matplotlib

import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # noqa: E402

matplotlib.rcParams["font.sans-serif"] = ["Heiti TC", "PingFang TC", "Microsoft JhengHei",
                                          "Noto Sans CJK TC", "Arial Unicode MS", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

SIGNAL = [0, 0]           # 2 bits 驗證訊號 00（純黑）


# ============================================================ DE 核心
def de_embed(x, y, bits=SIGNAL):
    m = (x + y) // 2
    d = x - y
    for b in bits:                    # 每嵌 1 bit 擴張一次
        d = 2 * d + b
    return m + (d + 1) // 2, m - d // 2


def de_extract(xp, yp, n_bits=len(SIGNAL)):
    m = (xp + yp) // 2
    d = xp - yp
    bits = []
    for _ in range(n_bits):           # 反向取出
        bits.append(d % 2)
        d //= 2
    bits.reverse()
    return bits, m + (d + 1) // 2, m - d // 2


# ============================================================ 讀寫檔案
def to_int(v):
    """格子內容 → 整數；不是數字（'--'、空白、文字）回傳 None。"""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating, Decimal)):
        v = float(v)
        return None if np.isnan(v) else int(round(v))
    if isinstance(v, str):
        s = v.replace(",", "").strip()
        try:
            return int(float(s))
        except ValueError:
            return None
    return None


def read_table(path):
    """讀 .xlsx / .csv / .numbers，回傳 DataFrame（第一列是標題）。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".numbers":
        try:
            from numbers_parser import Document
        except ImportError:
            raise RuntimeError("要讀 .numbers 檔需要先安裝套件：\n\n"
                               "python3 -m pip install numbers-parser\n\n"
                               "或在 Numbers 用「檔案 → 輸出為 → Excel」存成 .xlsx。")
        doc = Document(path)
        for sheet in doc.sheets:
            for table in sheet.tables:
                rows = table.rows(values_only=True)
                df = pd.DataFrame(rows[1:], columns=rows[0])
                if "公司名稱" in df.columns:
                    return df
        raise RuntimeError("在 .numbers 檔裡找不到有「公司名稱」欄位的表格")
    if ext == ".csv":
        return pd.read_csv(path)
    for df in pd.read_excel(path, sheet_name=None).values():   # Numbers 匯出可能多一張摘要
        if "公司名稱" in df.columns:
            return df.reset_index(drop=True)
    raise RuntimeError("找不到有「公司名稱」欄位的工作表")


def write_xlsx(df, path, marks=()):
    """用 xlsxwriter 存檔（Numbers / Excel 都打得開）。marks = [(欄名, 列, 底色)]"""
    try:
        import xlsxwriter  # noqa: F401
    except ImportError:
        raise RuntimeError("缺少 xlsxwriter 套件，請在終端機執行：\npython3 -m pip install xlsxwriter")
    with pd.ExcelWriter(path, engine="xlsxwriter") as xw:
        df.to_excel(xw, index=False, sheet_name="Sheet1")
        wb, ws = xw.book, xw.sheets["Sheet1"]
        ws.set_column(0, len(df.columns) - 1, 16)
        fmts = {}
        for c, r, color in marks:
            fmts.setdefault(color, wb.add_format({"bg_color": color, "bold": True,
                                                  "font_color": "#C00000"}))
            ws.write(r + 1, list(df.columns).index(c), df.at[r, c], fmts[color])


def cell_name(cols, col, row):
    """欄名 + 列 index → Excel 儲存格名稱（第 1 列是標題）"""
    idx = list(cols).index(col)
    letters = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(65 + rem) + letters
    return f"{letters}{row + 2}"


def make_pairs(df, num_cols):
    """同一欄裡由上往下，相鄰的兩個「數字」配成一組（'--' 跳過）。"""
    pairs = []
    for c in num_cols:
        rows = [r for r in df.index if to_int(df.at[r, c]) is not None]
        for k in range(0, len(rows) - 1, 2):
            pairs.append((c, int(rows[k]), int(rows[k + 1])))
    return pairs


def open_with_default_app(path):
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif sys.platform.startswith("win"):
            os.startfile(path)  # noqa
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


# ============================================================ 畫圖
def draw_map(fig, bits, title, labels=None):
    """bits[k] = 取出的位元（None 表示這組已經不是數字）。00 → 黑；其他 → 白"""
    fig.clear()
    ax = fig.add_subplot(111)
    n = len(bits)
    side = int(np.ceil(np.sqrt(n)))
    img = np.zeros((side, side))
    bad = [k for k, b in enumerate(bits) if b != SIGNAL]
    for k in bad:
        img[k // side, k % side] = 1
    ax.imshow(img, cmap="gray", vmin=0, vmax=1, interpolation="nearest")
    for k in bad:
        r, c = divmod(k, side)
        ax.add_patch(Rectangle((c - .5, r - .5), 1, 1, fill=False, ec="red", lw=1.5))
        if labels:
            ax.annotate(labels[k], (c, r), xytext=(4, -6), textcoords="offset points",
                        color="#FF6666", fontsize=8, weight="bold")
    ax.set_title(title, fontsize=11)
    ax.set_xlabel(f"數值對編號 mod {side}", fontsize=9)
    ax.set_ylabel(f"數值對編號 // {side}", fontsize=9)
    ax.tick_params(labelsize=8)
    fig.tight_layout()


# ============================================================ 視窗
class DEApp:
    def __init__(self, root):
        self.root = root
        root.title("DE 差值擴張 — 數字資料竄改偵測")
        root.geometry("1200x900")

        self.src = None          # 老師的原始檔
        self.emb_path = None     # 嵌入後的 xlsx
        self.meta_path = None    # 嵌入紀錄（配對方式＋嵌入後數值）
        self.meta = None
        self.last_check = None   # (df, rest, flagged)

        # ---- 上方按鈕列
        bar = tk.Frame(root, padx=8, pady=6)
        bar.pack(fill="x")
        tk.Button(bar, text="選擇檔案", command=self.choose_file).pack(side="left")
        self.file_lbl = tk.Label(bar, text="（尚未選擇）", fg="gray", width=40, anchor="w")
        self.file_lbl.pack(side="left", padx=6)
        self.btn_embed = tk.Button(bar, text="① 嵌入", command=self.do_embed, state="disabled")
        self.btn_embed.pack(side="left", padx=3)
        self.btn_open = tk.Button(bar, text="打開嵌入後的檔案", command=self.open_emb, state="disabled")
        self.btn_open.pack(side="left", padx=3)
        self.btn_check = tk.Button(bar, text="② 檢查", command=self.do_check, state="disabled")
        self.btn_check.pack(side="left", padx=3)
        self.btn_pick = tk.Button(bar, text="選別的檔案檢查…", command=self.check_other, state="disabled")
        self.btn_pick.pack(side="left", padx=3)
        self.btn_restore = tk.Button(bar, text="③ 存還原檔", command=self.do_restore, state="disabled")
        self.btn_restore.pack(side="left", padx=3)

        # ---- 中間兩張圖
        mid = tk.Frame(root)
        mid.pack(fill="both", expand=True)
        left = tk.LabelFrame(mid, text=" 修改前（剛嵌入完） ", padx=4, pady=4)
        left.pack(side="left", fill="both", expand=True, padx=(8, 4))
        right = tk.LabelFrame(mid, text=" 修改後（按下檢查） ", padx=4, pady=4)
        right.pack(side="left", fill="both", expand=True, padx=(4, 8))
        self.fig_l = Figure(figsize=(5.5, 5.5), dpi=90)
        self.fig_r = Figure(figsize=(5.5, 5.5), dpi=90)
        self.can_l = FigureCanvasTkAgg(self.fig_l, master=left)
        self.can_r = FigureCanvasTkAgg(self.fig_r, master=right)
        self.can_l.get_tk_widget().pack(fill="both", expand=True)
        self.can_r.get_tk_widget().pack(fill="both", expand=True)
        for fig, msg in ((self.fig_l, "按「① 嵌入」後顯示"), (self.fig_r, "按「② 檢查」後顯示")):
            fig.text(0.5, 0.5, msg, ha="center", va="center", fontsize=13, color="gray")
        self.can_l.draw(); self.can_r.draw()

        # ---- 下方說明
        bottom = tk.LabelFrame(root, text=" 說明 ", padx=4, pady=4)
        bottom.pack(fill="both", padx=8, pady=(0, 8))
        self.log = ScrolledText(bottom, height=14, font=("Menlo", 12), wrap="word")
        self.log.pack(fill="both", expand=True)
        self.say("請先按「選擇檔案」，選老師的「測試數據(原始資料).xlsx」。", clear=True)

    # ------------------------------------------------ 小工具
    def say(self, text, clear=False):
        if clear:
            self.log.delete("1.0", "end")
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def error(self, e):
        messagebox.showerror("錯誤", str(e))

    # ------------------------------------------------ 按鈕
    def choose_file(self):
        path = filedialog.askopenfilename(
            title="選擇測試數據",
            filetypes=[("Excel / CSV / Numbers", "*.xlsx *.xls *.csv *.numbers"), ("所有檔案", "*.*")])
        if not path:
            return
        self.src = path
        stem = os.path.splitext(path)[0]
        if stem.endswith("_DE嵌入"):           # 選到的就是已經嵌入過的檔案 → 直接可以檢查
            self.emb_path = stem + ".xlsx"
            self.meta_path = stem + ".json"
        else:
            self.emb_path = stem + "_DE嵌入.xlsx"
            self.meta_path = stem + "_DE嵌入.json"
        self.file_lbl.config(text=os.path.basename(path), fg="black")
        self.btn_embed.config(state="normal")
        self.meta = None
        if os.path.exists(self.meta_path):
            with open(self.meta_path, encoding="utf-8") as f:
                self.meta = json.load(f)
            for b in (self.btn_open, self.btn_check, self.btn_pick):
                b.config(state="normal")
            self.say(f"已選擇：{path}\n找到之前的嵌入紀錄，可以直接按「② 檢查」，或重新按「① 嵌入」。",
                     clear=True)
        else:
            self.say(f"已選擇：{path}\n下一步：按「① 嵌入」。", clear=True)

    def do_embed(self):
        try:
            if self.src.endswith("_DE嵌入.xlsx"):
                if not messagebox.askyesno("確認", "這個檔案看起來已經嵌入過了，確定要再嵌入一次嗎？\n"
                                                   "（建議選老師的原始檔）"):
                    return
            orig = read_table(self.src)
            num_cols = list(orig.columns[5:12])            # F ~ L：七個現金流量數字欄
            pairs = make_pairs(orig, num_cols)
            emb = orig.copy()
            for c, rx, ry in pairs:
                emb.at[rx, c], emb.at[ry, c] = de_embed(to_int(orig.at[rx, c]), to_int(orig.at[ry, c]))
            write_xlsx(emb, self.emb_path)
            # 嵌入紀錄：配對方式＋嵌入後的數值（檢查時用來對照「實際改了哪一格」）
            self.meta = {"columns": [str(c) for c in orig.columns], "num_cols": num_cols,
                         "pairs": pairs,
                         "emb": [[to_int(emb.at[rx, c]), to_int(emb.at[ry, c])] for c, rx, ry in pairs],
                         "orig": [[to_int(orig.at[rx, c]), to_int(orig.at[ry, c])] for c, rx, ry in pairs]}
            with open(self.meta_path, "w", encoding="utf-8") as f:
                json.dump(self.meta, f, ensure_ascii=False)
        except Exception as e:
            return self.error(e)

        # 修改前：直接從嵌入後的數值擷取 → 應該全部是 00 → 全黑
        bits = [de_extract(x, y)[0] for x, y in self.meta["emb"]]
        draw_map(self.fig_l, bits, f"擷取出的驗證訊號：全黑（{len(bits)} 組全部是 00）")
        self.can_l.draw()
        self.fig_r.clear(); self.fig_r.text(0.5, 0.5, "去改數字，存檔後按「② 檢查」",
                                             ha="center", va="center", fontsize=13, color="gray")
        self.can_r.draw()
        for b in (self.btn_open, self.btn_check, self.btn_pick):
            b.config(state="normal")
        self.btn_restore.config(state="disabled")

        self.say("【① 嵌入完成】", clear=True)
        self.say(f"共 {len(orig)} 家公司 × {len(num_cols)} 個數字欄 → {len(pairs)} 組數值對"
                 f"（同一欄上下相鄰兩個數字一組，'--' 不參與）")
        self.say(f"嵌入後的檔案：{self.emb_path}\n（老師的原始檔沒有被修改）\n")
        self.say("為什麼數字變了？DE 會把每組的差值擴張 4 倍（d'' = 4d，藏進 00），這就是「數值已擴張」。"
                 "擷取時可以 100% 還原。前 5 組：")
        for k, (c, rx, ry) in enumerate(pairs[:5]):
            (x, y), (xp, yp) = self.meta["orig"][k], self.meta["emb"][k]
            self.say(f"  {cell_name(orig.columns, c, rx)}/{cell_name(orig.columns, c, ry)}："
                     f"({x}, {y}) → ({xp}, {yp})    差值 {x - y} → {xp - yp}")
        self.say("\n下一步：在打開的 Numbers / Excel 裡改幾個數字並存檔，再回來按「② 檢查」。"
                 "\n小提醒：改的量不是 4 的倍數（例如 +1、+3、−7）才會被抓到；+4、+100 會漏抓。")
        self.open_emb()

    def open_emb(self):
        if self.emb_path and os.path.exists(self.emb_path):
            open_with_default_app(self.emb_path)

    def newest_edited_file(self):
        """找最新被存過的版本：嵌入後的 .xlsx，或 Numbers 另存的同名 .numbers"""
        stem = os.path.splitext(self.emb_path)[0]
        cands = [p for p in (self.emb_path, stem + ".numbers", stem + ".csv") if os.path.exists(p)]
        return max(cands, key=os.path.getmtime) if cands else None

    def do_check(self, path=None):
        if not self.meta:
            return self.error("找不到嵌入紀錄，請先按「① 嵌入」。")
        path = path or self.newest_edited_file()
        if not path:
            return self.error("找不到嵌入後的檔案，請先按「① 嵌入」。")
        try:
            df = read_table(path)
        except Exception as e:
            return self.error(e)

        cols = self.meta["columns"]
        if [str(c) for c in df.columns] != cols:
            df.columns = cols[:len(df.columns)] if len(df.columns) <= len(cols) else df.columns
        pairs = [tuple(p) for p in self.meta["pairs"]]
        bits, rest, labels, changed = [], df.copy(), {}, []
        for k, (c, rx, ry) in enumerate(pairs):
            labels[k] = f"{cell_name(cols, c, rx)}/{cell_name(cols, c, ry)}"
            xp = to_int(df.at[rx, c]) if rx < len(df) else None
            yp = to_int(df.at[ry, c]) if ry < len(df) else None
            if xp is None or yp is None:               # 數字被刪掉或改成文字
                bits.append(None)
            else:
                b, x, y = de_extract(xp, yp)
                bits.append(b)
                rest.at[rx, c], rest.at[ry, c] = x, y
            for r, now, before in ((rx, xp, self.meta["emb"][k][0]), (ry, yp, self.meta["emb"][k][1])):
                if now != before:
                    changed.append((k, c, r, before, now))
        flagged = [k for k, b in enumerate(bits) if b != SIGNAL]
        self.last_check = (df, rest, flagged, pairs)

        draw_map(self.fig_r, bits, f"擷取出的驗證訊號：{len(flagged)} 個白點 = 被改過的數值對", labels)
        self.can_r.draw()
        self.btn_restore.config(state="normal")

        name = lambda r: df.at[r, "公司名稱"] if "公司名稱" in df.columns else ""
        self.say(f"【② 檢查】讀取：{os.path.basename(path)}", clear=True)
        if not flagged:
            self.say(f"擷取出的 {len(bits)} 組全部是 00 → 全黑圖，沒有偵測到竄改。")
        else:
            self.say(f"擷取出 {len(bits)} 組，其中 {len(flagged)} 組不是 00 → 這些數值對被改過：\n")
            for k in flagged:
                c, rx, ry = pairs[k]
                why = ("有一格已經不是數字（被刪掉或改成文字）" if bits[k] is None
                       else f"取出位元 {''.join(map(str, bits[k]))} ≠ 00")
                self.say(f"  ● {labels[k]:<10} {name(rx)} / {name(ry)}　欄位：{c}"
                         f"\n      {why} → 這兩格中至少有一格被改過")
            self.say("\n  說明：DE 一次只能定位到「一組」數值對（pairwise），"
                     "無法分辨是上面那格還是下面那格被改。")

        # 對照嵌入紀錄（不是 DE 偵測，是用來驗證結果）
        if changed:
            self.say(f"\n—— 對照嵌入時的紀錄，你實際改了 {len(changed)} 格 ——")
            for k, c, r, before, now in changed:
                diff = "" if (before is None or now is None) else f"（{now - before:+d}）"
                hit = "✔ 已偵測" if k in flagged else "✘ 漏抓"
                shown = "（非數字）" if now is None else now
                self.say(f"  {cell_name(cols, c, r):<6} {name(r)}：{before} → {shown}{diff}　{hit}")
            missed = sorted({k for k, *_ in changed} - set(flagged))
            if missed:
                self.say("\n  漏抓原因：改動量剛好讓差值 d'' 還是 4 的倍數（例如 +4、+100），"
                         "取出仍是 00。用 2 bits 驗證訊號時，隨機竄改約有 1/4 機率發生，"
                         "所以老師建議擴張兩次以上。")
        else:
            self.say("\n（和嵌入時比，檔案裡的數字都沒有變。如果你有改，請確認有按儲存。"
                     "\n Numbers 另存的 .numbers 檔要和嵌入檔同名、放在同一個資料夾，"
                     "或用「選別的檔案檢查…」直接選它。）")
        ok = [k for k in range(len(pairs)) if k not in flagged and k not in {kk for kk, *_ in changed}]
        same = all([to_int(rest.at[pairs[k][1], pairs[k][0]]), to_int(rest.at[pairs[k][2], pairs[k][0]])]
                   == self.meta["orig"][k] for k in ok)
        self.say(f"\n沒被改到的 {len(ok)} 組，擷取後還原成原始數值：{'全部正確 ✔' if same else '有誤'}")

    def check_other(self):
        path = filedialog.askopenfilename(
            title="選擇修改後的檔案",
            initialdir=os.path.dirname(self.emb_path) if self.emb_path else None,
            filetypes=[("Excel / CSV / Numbers", "*.xlsx *.xls *.csv *.numbers"), ("所有檔案", "*.*")])
        if path:
            self.do_check(path)

    def do_restore(self):
        if not self.last_check:
            return
        df, rest, flagged, pairs = self.last_check
        out = os.path.splitext(self.emb_path)[0].replace("_DE嵌入", "") + "_DE還原.xlsx"
        try:
            write_xlsx(rest, out, [(pairs[k][0], r, "#FF9999") for k in flagged for r in pairs[k][1:]])
        except Exception as e:
            return self.error(e)
        self.say(f"\n【③ 已存還原檔】{out}\n  紅底 = 偵測到被改過的數值對（這些格子的還原值不可信）")
        open_with_default_app(out)


if __name__ == "__main__":
    root = tk.Tk()
    DEApp(root)
    root.mainloop()
