# -*- coding: utf-8 -*-
"""
固定錨點可逆式差值擴張法 (FADE) — 圖形介面版
--------------------------------------------------------------
使用方式：
  1. 把本程式和「測試數據(10筆).csv」放在同一個資料夾，執行本程式
  2. 選擇欄位（預設：匯率變動對現金及約當現金之影響）→【讀取資料】
  3. 【藏匿】：依編碼端步驟藏入驗證訊號，並把結果寫回測試數據檔
     （該欄換成藏匿後數值，最後多一欄「驗證訊號」）
  4. 用 Excel / Numbers / 文字編輯器修改測試數據檔中藏匿後的數值並存檔
  5. 【檢測】：重新讀檔，依解碼端步驟比對，遭竄改者以紅色標示
  6. 【還原原始資料】：把藏匿後數值還原回原值（可逆）

編碼端
  1. 依序將每個數值送進 SHA256，取雜湊值最後 4 個位元
  2. 將這 4 個位元放進另一欄位（僅為視覺化）
  3. PRNG 搭配 key 產生一串隨機數字作為錨值
  4. 非對稱差值擴張：一個數值配一個錨值，藏入 4 個位元
解碼端
  1. 用 key 搭配 PRNG 產生同一串錨值
  2. 依序將每個數值送進 SHA256，取其最後 4 個位元（數值現況）
  3. 非對稱差值擴張擷取內藏的 4 個位元
  4. 擷取出的 4 個位元與第 2 步的 4 個位元比對
  5. 相同者為正確原數值，不同者為遭竄改的數值
  6. 完成自動竄改偵測與驗證
"""
import csv
import glob
import hashlib
import io
import os
import random
import shutil
import tkinter as tk
from decimal import Decimal, InvalidOperation
from tkinter import filedialog, messagebox, ttk

# ---------------- 參數 ----------------
BITS = 4                 # 每個數值藏 4 bits
M = 2 ** BITS            # 擴張倍數 16
DEFAULT_KEY = 20261008   # 預設金鑰
ANCHOR_RANGE = (1, 99)   # 錨值範圍
DEFAULT_COL = "匯率變動對現金及約當現金之影響"
SIGNAL_PREFIX = "驗證訊號"
HERE = os.path.dirname(os.path.abspath(__file__))


# ================= FADE 演算法 =================
def hash_bits(x: int) -> int:
    """SHA256(數值字串) 的最後 4 個位元"""
    return hashlib.sha256(str(x).encode("utf-8")).digest()[-1] & (M - 1)


def gen_anchors(key: int, n: int) -> list:
    """PRNG + key 產生錨值數列（同 key 必得同一串）"""
    rng = random.Random(key)
    return [rng.randint(*ANCHOR_RANGE) for _ in range(n)]


def embed(x: int, a: int, bit: int) -> int:
    """x>A: 16x-15A+bit ； x<A: 16x-15A-bit ； x=A: 不擴張"""
    if x > a:
        return M * x - (M - 1) * a + bit
    if x < a:
        return M * x - (M - 1) * a - bit
    return x


def extract(xp: int, a: int):
    """回傳 (還原值, 擷取出的 bits)；x'=A 時沒有藏資料"""
    if xp > a:
        return a + (xp - a) // M, (xp - a) % M
    if xp < a:
        return a - (a - xp) // M, (a - xp) % M
    return a, None


def b4(v):
    return "—" if v is None else format(v, "04b")


# ================= 檔案讀寫 =================
def read_csv(path):
    """自動判斷編碼（UTF-8 / Big5），回傳 (表頭, 資料列, 編碼)"""
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "cp950", "big5"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("無法判斷檔案編碼")
    rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    return rows[0], rows[1:], enc


def write_csv(path, header, rows):
    """以 UTF-8 (含 BOM) 寫回，Excel / Numbers / VS Code 皆可正確開啟中文"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    os.replace(tmp, path)


def to_int(s: str) -> int:
    s = str(s).strip().replace(",", "").replace('"', "")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"「{s}」不是數字")
    if d != d.to_integral_value():
        raise ValueError(f"「{s}」不是整數")
    return int(d)


def find_default_file():
    for pat in ("測試數據*.csv", "*.csv"):
        found = sorted(f for f in glob.glob(os.path.join(HERE, pat))
                       if "原始備份" not in f)
        if found:
            return found[0]
    return ""


# ================= 圖形介面 =================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FADE 固定錨點可逆式差值擴張法 — 數值資料竄改偵測")
        self.geometry("1280x760")
        self.minsize(1000, 600)

        style = ttk.Style(self)
        style.theme_use("clam")                       # clam 才能顯示列底色
        style.configure("Treeview", rowheight=26, font=("PingFang TC", 13))
        style.configure("Treeview.Heading", font=("PingFang TC", 12, "bold"))
        style.configure("Big.TButton", font=("PingFang TC", 13, "bold"), padding=6)

        self.path = tk.StringVar(value=find_default_file())
        self.col = tk.StringVar(value=DEFAULT_COL)
        self.key = tk.StringVar(value=str(DEFAULT_KEY))
        self.status = tk.StringVar(value="請按【讀取資料】")

        self._build()
        if self.path.get():
            self.load_file()

    # ---------- 版面 ----------
    def _build(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="測試數據檔：").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.path, width=70).grid(row=0, column=1, columnspan=3, sticky="we")
        ttk.Button(top, text="選擇檔案…", command=self.pick_file).grid(row=0, column=4, padx=4)

        ttk.Label(top, text="選擇欄位：").grid(row=1, column=0, sticky="w", pady=6)
        self.col_box = ttk.Combobox(top, textvariable=self.col, width=40, state="readonly")
        self.col_box.grid(row=1, column=1, sticky="w")
        ttk.Label(top, text="金鑰 key：").grid(row=1, column=2, sticky="e")
        ttk.Entry(top, textvariable=self.key, width=14).grid(row=1, column=3, sticky="w")
        top.columnconfigure(1, weight=1)

        btns = ttk.Frame(self, padding=(10, 0))
        btns.pack(fill="x")
        ttk.Button(btns, text="① 讀取資料", style="Big.TButton", command=self.load_file).pack(side="left", padx=4)
        ttk.Button(btns, text="② 藏匿（編碼端）", style="Big.TButton", command=self.do_embed).pack(side="left", padx=4)
        ttk.Button(btns, text="③ 檢測（解碼端）", style="Big.TButton", command=self.do_detect).pack(side="left", padx=4)
        ttk.Button(btns, text="④ 還原原始資料", style="Big.TButton", command=self.do_restore).pack(side="left", padx=4)

        body = ttk.PanedWindow(self, orient="vertical")
        body.pack(fill="both", expand=True, padx=10, pady=8)

        tf = ttk.Frame(body)
        self.tree = ttk.Treeview(tf, show="headings")
        ys = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        xs = ttk.Scrollbar(tf, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        tf.rowconfigure(0, weight=1)
        tf.columnconfigure(0, weight=1)
        self.tree.tag_configure("bad", background="#F8CBAD")
        self.tree.tag_configure("ok", background="#E2F0D9")
        self.tree.tag_configure("emb", background="#FFF2CC")
        body.add(tf, weight=3)

        lf = ttk.LabelFrame(body, text="執行步驟")
        self.log = tk.Text(lf, height=10, font=("Menlo", 12), wrap="word")
        self.log.pack(fill="both", expand=True)
        self.log.tag_configure("h", font=("PingFang TC", 13, "bold"), foreground="#1F4E79")
        self.log.tag_configure("bad", foreground="#C00000")
        self.log.tag_configure("ok", foreground="#2E7D32")
        body.add(lf, weight=2)

        ttk.Label(self, textvariable=self.status, padding=(10, 2, 10, 8),
                  font=("PingFang TC", 13, "bold")).pack(fill="x")

    # ---------- 小工具 ----------
    def write(self, text, tag=None):
        self.log.insert("end", text + "\n", tag)
        self.log.see("end")

    def clear_log(self):
        self.log.delete("1.0", "end")

    def show_table(self, columns, rows, tags=None):
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = columns
        for c in columns:
            self.tree.heading(c, text=c)
            w = 80 if c in ("序號", "公司代號", "錨值 A") else 150
            self.tree.column(c, width=w, anchor="center", stretch=True)
        for i, r in enumerate(rows):
            self.tree.insert("", "end", values=r, tags=(tags[i],) if tags and tags[i] else ())

    def get_key(self):
        try:
            return int(self.key.get().strip())
        except ValueError:
            messagebox.showerror("金鑰錯誤", "key 請輸入整數")
            return None

    def pick_file(self):
        p = filedialog.askopenfilename(initialdir=HERE, filetypes=[("CSV", "*.csv")])
        if p:
            self.path.set(p)
            self.load_file()

    def signal_col_name(self):
        return f"{SIGNAL_PREFIX}（{self.col.get()}）"

    def read_current(self):
        """讀檔並取出目前選擇欄位；回傳 dict"""
        path = self.path.get().strip()
        if not path or not os.path.exists(path):
            raise FileNotFoundError(f"找不到測試數據檔：\n{path or '(未選擇)'}\n請放在程式同一個資料夾")
        header, rows, enc = read_csv(path)
        col = self.col.get()
        if col not in header:
            raise KeyError(f"檔案中沒有「{col}」這一欄")
        ci = header.index(col)
        si = next((i for i, h in enumerate(header) if h.startswith(SIGNAL_PREFIX)), None)
        name_i = header.index("公司名稱") if "公司名稱" in header else None
        code_i = header.index("公司代號") if "公司代號" in header else None
        vals = []
        for n, r in enumerate(rows, 2):
            try:
                vals.append(to_int(r[ci]))
            except (ValueError, IndexError) as e:
                raise ValueError(f"第 {n} 列「{col}」讀取失敗：{e}")
        return dict(path=path, header=header, rows=rows, enc=enc, ci=ci, si=si,
                    vals=vals,
                    names=[r[name_i] if name_i is not None else "" for r in rows],
                    codes=[r[code_i] if code_i is not None else str(k + 1) for k, r in enumerate(rows)])

    # ---------- ① 讀取 ----------
    def load_file(self):
        self.clear_log()
        try:
            path = self.path.get().strip()
            header, _, enc = read_csv(path)
            num_cols = [h for h in header[5:] if not h.startswith(SIGNAL_PREFIX)] or header
            self.col_box["values"] = num_cols
            if self.col.get() not in num_cols:
                self.col.set(DEFAULT_COL if DEFAULT_COL in num_cols else num_cols[0])
            d = self.read_current()
        except Exception as e:
            messagebox.showerror("讀取失敗", str(e))
            self.status.set("讀取失敗")
            return
        embedded = d["si"] is not None
        self.write(f"讀取：{os.path.basename(d['path'])}（編碼 {d['enc']}）", "h")
        self.write(f"欄位：{self.col.get()}，共 {len(d['vals'])} 筆")
        if embedded:
            self.write(f"此檔已藏匿過（最後一欄「{d['header'][d['si']]}」），可直接按【③ 檢測】。")
            cols = ["序號", "公司代號", "公司名稱", "藏匿後數值 x'", d["header"][d["si"]]]
            rows = [(k + 1, d["codes"][k], d["names"][k], f"{v:,}", d["rows"][k][d["si"]] if d["si"] < len(d["rows"][k]) else "")
                    for k, v in enumerate(d["vals"])]
            self.show_table(cols, rows, ["emb"] * len(rows))
            self.status.set("已讀取藏匿後的資料 → 可修改檔案後按【③ 檢測】")
        else:
            cols = ["序號", "公司代號", "公司名稱", "原始數值 x"]
            rows = [(k + 1, d["codes"][k], d["names"][k], f"{v:,}") for k, v in enumerate(d["vals"])]
            self.show_table(cols, rows)
            self.status.set("已讀取原始資料 → 請按【② 藏匿】")

    # ---------- ② 藏匿（編碼端） ----------
    def do_embed(self):
        key = self.get_key()
        if key is None:
            return
        try:
            d = self.read_current()
        except Exception as e:
            messagebox.showerror("讀取失敗", str(e))
            return
        if d["si"] is not None:
            messagebox.showwarning("已藏匿過",
                                   "這個檔案已經藏匿過驗證訊號了。\n請先按【④ 還原原始資料】再重新藏匿，"
                                   "或直接修改檔案後按【③ 檢測】。")
            return

        vals = d["vals"]
        self.clear_log()
        self.write("【編碼端】", "h")

        # 步驟 1、2：SHA256 取末 4 bits
        bits = [hash_bits(x) for x in vals]
        self.write("1. 依序將每個數值送進 SHA256，取雜湊值最後 4 個位元")
        for k, x in enumerate(vals):
            dg = hashlib.sha256(str(x).encode()).hexdigest()
            self.write(f"   {d['names'][k]:　<4} x={x:>12}  SHA256=…{dg[-8:]}  → 末4位元 {b4(bits[k])}")
        self.write("2. 將 4 個位元放進最後一欄「驗證訊號」（僅為視覺化）")

        # 步驟 3：PRNG + key 產生錨值
        anchors = gen_anchors(key, len(vals))
        self.write(f"3. PRNG 搭配 key={key} 產生錨值：{anchors}")

        # 步驟 4：非對稱差值擴張
        stego = [embed(x, a, b) for x, a, b in zip(vals, anchors, bits)]
        self.write("4. 非對稱差值擴張藏入驗證訊號（x>A: 16x−15A+bit；x<A: 16x−15A−bit）")
        for k in range(len(vals)):
            x, a, b, xp = vals[k], anchors[k], bits[k], stego[k]
            op = "+" if x > a else ("−" if x < a else "")
            formula = f"16×{x}−15×{a}{op}{b}" if op else "x=A 不擴張"
            self.write(f"   x={x:>12}, A={a:>2}, bit={b4(b)} → x' = {formula} = {xp}")
            if x == a:
                self.write("   ⚠ 此筆 x=A，無法藏入驗證訊號", "bad")

        # 寫回檔案：該欄換成藏匿後數值，最後加一欄驗證訊號
        backup = os.path.splitext(d["path"])[0] + "_原始備份.csv"
        if not os.path.exists(backup):
            shutil.copy2(d["path"], backup)
        header = d["header"] + [self.signal_col_name()]
        rows = []
        for k, r in enumerate(d["rows"]):
            r = list(r) + [""] * (len(d["header"]) - len(r))
            r[d["ci"]] = str(stego[k])
            rows.append(r + [b4(bits[k])])
        try:
            write_csv(d["path"], header, rows)
        except OSError as e:
            messagebox.showerror("寫檔失敗", f"{e}\n（檔案是否正被其他程式鎖住？）")
            return
        self.write(f"\n完成數字資料保護，已寫回：{os.path.basename(d['path'])}", "ok")
        self.write(f"原始檔備份：{os.path.basename(backup)}")
        self.write("→ 現在可以打開測試數據檔，修改幾個藏匿後的數值並存檔，再按【③ 檢測】。")

        cols = ["序號", "公司代號", "公司名稱", "原始數值 x", "錨值 A", "藏匿後數值 x'", self.signal_col_name()]
        table = [(k + 1, d["codes"][k], d["names"][k], f"{vals[k]:,}", anchors[k], f"{stego[k]:,}", b4(bits[k]))
                 for k in range(len(vals))]
        self.show_table(cols, table, ["emb"] * len(table))
        self.status.set("藏匿完成，已寫回測試數據檔（該欄為藏匿後數值，最後一欄為驗證訊號）")

    # ---------- ③ 檢測（解碼端） ----------
    def do_detect(self):
        key = self.get_key()
        if key is None:
            return
        try:
            d = self.read_current()           # 每次都重新讀檔 → 抓得到手動修改
        except Exception as e:
            messagebox.showerror("讀取失敗", str(e))
            return
        if d["si"] is None:
            messagebox.showwarning("尚未藏匿", "這個檔案還沒有藏匿驗證訊號，請先按【② 藏匿】。")
            return

        stego = d["vals"]
        self.clear_log()
        self.write("【解碼端】（已重新讀取測試數據檔）", "h")

        anchors = gen_anchors(key, len(stego))
        self.write(f"1. 用 key={key} 搭配 PRNG 產生同一串錨值：{anchors}")

        rec, hid, cur, res = [], [], [], []
        for xp, a in zip(stego, anchors):
            x, b = extract(xp, a)
            rec.append(x)
            hid.append(b)
        self.write("2. 還原數值並送進 SHA256，取數值現況雜湊值的最後 4 個位元")
        self.write("3. 非對稱差值擴張擷取內藏的 4 個位元（x'>A: (x'−A) mod 16；x'<A: (A−x') mod 16）")
        self.write("4. 比對擷取出的 4 位元 與 現況雜湊末 4 位元")
        bad = []
        for k in range(len(stego)):
            c = hash_bits(rec[k])
            cur.append(c)
            if hid[k] is None:
                r = "無法驗證(x'=A)"
            elif hid[k] == c:
                r = "正確"
            else:
                r = "遭竄改"
                bad.append(k)
            res.append(r)
            tag = "bad" if r == "遭竄改" else None
            self.write(f"   第{k + 1:>2}筆 {d['names'][k]:　<4} x'={stego[k]:>13}  A={anchors[k]:>2}  還原 x={rec[k]:>12}  "
                       f"擷取 {b4(hid[k])}  現況 {b4(c)}  → {r}", tag)

        self.write("5. 比對相同者為正確原數值，比對不同者為遭竄改的數值")
        if bad:
            msg = "、".join(f"第{k + 1}筆（{d['names'][k]}）" for k in bad)
            self.write(f"6. 檢測完成：偵測到 {len(bad)} 筆遭竄改 → {msg}", "bad")
            self.status.set(f"⚠ 檢測出錯誤：{len(bad)} 筆數值遭竄改（紅色列）")
        else:
            self.write("6. 檢測完成：全部數值驗證通過，未發現竄改", "ok")
            self.status.set("✓ 檢測完成：未發現竄改")

        cols = ["序號", "公司代號", "公司名稱", "目前檔案數值 x'", "錨值 A", "還原數值 x",
                "擷取出的 4bits", "現況雜湊末 4bits", "檢測結果"]
        table = [(k + 1, d["codes"][k], d["names"][k], f"{stego[k]:,}", anchors[k], f"{rec[k]:,}",
                  b4(hid[k]), b4(cur[k]), res[k]) for k in range(len(stego))]
        tags = ["bad" if r == "遭竄改" else "ok" for r in res]
        self.show_table(cols, table, tags)

        if bad:
            messagebox.showwarning("檢測出錯誤", f"偵測到 {len(bad)} 筆數值遭竄改：\n" +
                                   "\n".join(f"第{k + 1}筆　{d['codes'][k]} {d['names'][k]}" for k in bad))
        else:
            messagebox.showinfo("檢測完成", "全部數值驗證通過，未發現竄改。")

    # ---------- ④ 還原 ----------
    def do_restore(self):
        key = self.get_key()
        if key is None:
            return
        try:
            d = self.read_current()
        except Exception as e:
            messagebox.showerror("讀取失敗", str(e))
            return
        if d["si"] is None:
            messagebox.showinfo("不需還原", "這個檔案目前是原始資料，沒有藏匿驗證訊號。")
            return
        anchors = gen_anchors(key, len(d["vals"]))
        out = [extract(xp, a) for xp, a in zip(d["vals"], anchors)]
        bad = [k for k, (x, b) in enumerate(out) if b is not None and b != hash_bits(x)]
        if bad and not messagebox.askyesno(
                "有資料遭竄改",
                f"有 {len(bad)} 筆數值遭竄改，還原出的值不會是原值。\n仍要還原嗎？\n"
                f"（原始資料另有備份檔 *_原始備份.csv）"):
            return
        header = d["header"][:d["si"]] + d["header"][d["si"] + 1:]
        rows = []
        for k, r in enumerate(d["rows"]):
            r = list(r)
            r[d["ci"]] = str(out[k][0])
            if d["si"] < len(r):
                del r[d["si"]]
            rows.append(r)
        write_csv(d["path"], header, rows)
        self.clear_log()
        self.write("【還原】依解碼端公式把藏匿後數值還原，並移除驗證訊號欄", "h")
        for k, (x, _) in enumerate(out):
            self.write(f"   x'={d['vals'][k]:>13}, A={anchors[k]:>2} → x = {x}")
        self.write("已寫回檔案，資料恢復為原始數值（可逆）。", "ok")
        self.load_file_keep_log()

    def load_file_keep_log(self):
        d = self.read_current()
        cols = ["序號", "公司代號", "公司名稱", "原始數值 x"]
        self.show_table(cols, [(k + 1, d["codes"][k], d["names"][k], f"{v:,}") for k, v in enumerate(d["vals"])])
        self.status.set("已還原為原始資料 → 可再按【② 藏匿】")


if __name__ == "__main__":
    App().mainloop()
