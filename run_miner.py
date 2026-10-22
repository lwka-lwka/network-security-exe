# 打包成 exe 用的啟動程式：Blockchain 挖礦模擬器（tkinter 視窗）
import os

import mining_simulator

if __name__ == "__main__":
    app = mining_simulator.App()
    if os.environ.get("SELFTEST") == "1":          # GitHub Actions 自動測試用
        def done():
            open(os.environ.get("SELFTEST_OUT", "selftest_ok.txt"), "w").write("ok")
            app.destroy()
        app.after(4000, done)
    app.mainloop()
