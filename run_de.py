# 打包成 exe 用的啟動程式：DE 差值擴張竄改偵測（tkinter 視窗）
import os
import tkinter as tk

import DE

if __name__ == "__main__":
    root = tk.Tk()
    DE.DEApp(root)
    if os.environ.get("SELFTEST") == "1":          # GitHub Actions 自動測試用
        def done():
            # 順便測一次核心運算：嵌入再擷取要能還原
            xp, yp = DE.de_embed(100, 105)
            bits, x, y = DE.de_extract(xp, yp)
            assert bits == [0, 0] and (x, y) == (100, 105)
            open(os.environ.get("SELFTEST_OUT", "selftest_ok.txt"), "w").write("ok")
            root.destroy()
        root.after(4000, done)
    root.mainloop()
