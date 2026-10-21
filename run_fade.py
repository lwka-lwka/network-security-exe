# 打包成 exe 用的啟動程式：FADE 數字資料安全技術（tkinter 視窗）
import os
import sys

import fade_gui

# exe 執行時 __file__ 會指到暫存資料夾，改成「exe 所在的資料夾」，
# 才找得到放在 exe 旁邊的「測試數據(10筆).csv」
if getattr(sys, "frozen", False):
    fade_gui.HERE = os.path.dirname(sys.executable)

if __name__ == "__main__":
    app = fade_gui.App()
    if os.environ.get("SELFTEST") == "1":          # GitHub Actions 自動測試用
        def done():
            open(os.environ.get("SELFTEST_OUT", "selftest_ok.txt"), "w").write("ok")
            app.destroy()
        app.after(4000, done)
    app.mainloop()
