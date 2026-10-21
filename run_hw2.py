# 打包成 exe 用的啟動程式：文字浮水印嵌入 / 擷取系統（Gradio 網頁）
import os
import sys

PORT = 7860

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass
    print("正在啟動 文字浮水印嵌入 / 擷取系統，請稍候，瀏覽器會自動開啟……")
    print(f"如果瀏覽器沒有自動開啟，請手動前往 http://127.0.0.1:{PORT}")
    print("使用完畢後，關閉這個黑色視窗即可結束程式。")
    os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
    import HW2
    HW2.demo.launch(server_name="127.0.0.1", server_port=PORT,
                    inbrowser=os.environ.get("NO_BROWSER") != "1", share=False)
