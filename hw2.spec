# -*- mode: python ; coding: utf-8 -*-
# Gradio 需要用 spec 檔打包：gradio 要以原始碼 (.py) 形式收進去，並帶上前端靜態檔
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

datas = [("HW2.py", ".")]
hidden = []
for pkg in ("gradio", "gradio_client", "safehttpx", "groovy"):
    try:
        datas += collect_data_files(pkg)
        hidden += collect_submodules(pkg)
    except Exception:
        pass
for pkg in ("gradio", "gradio_client", "httpx", "fastapi", "starlette", "uvicorn", "pydantic"):
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass

a = Analysis(
    ["run_hw2.py"],
    pathex=["."],
    datas=datas,
    hiddenimports=hidden + ["HW2"],
    module_collection_mode={"gradio": "py", "gradio_client": "py"},
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="TextWatermark",
          console=True, upx=False)
