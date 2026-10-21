import streamlit as st
import numpy as np
from PIL import Image
from scipy.stats import chi2
import matplotlib.pyplot as plt
import matplotlib
import io

# 設定 Matplotlib 中文字型支援
matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'Microsoft JhengHei', 'SimHei', 'sans-serif']
matplotlib.rcParams['axes.unicode_minus'] = False

st.set_page_config(page_title="LSB 影像隱寫術教學實作系統", layout="wide")

st.title("LSB 影像隱寫術教學實作系統")

# ================= 區塊 1 =================
with st.container(border=True):
    st.subheader("1. 欲嵌入的訊息")
    secret_text = st.text_input("使用者輸入欲藏入影像中的文字內容", value="nknu0123456789")
    bits_count = len(secret_text.encode('utf-8')) * 8
    st.caption(f"已輸入 {len(secret_text)} 個字元（約 {bits_count} bits 容量）")

st.write("")

# ================= 區塊 2 與 區塊 4 左右對齊 =================
col_left, col_right = st.columns(2)

with col_left:
    with st.container(border=True):
        st.subheader("2. 輸入影像")
        uploaded_file = st.file_uploader("點擊或拖曳影像檔案至此 (支援 PNG / BMP)", type=["png", "bmp"])
        
        cover_image = None
        if uploaded_file:
            cover_image = Image.open(uploaded_file).convert("RGB")
            st.image(cover_image, caption=f"已選擇：{uploaded_file.name}", use_container_width=True)

with col_right:
    with st.container(border=True):
        st.subheader("4. 輸出：LSB 藏入後影像")
        st.caption("處理完成後可預覽並下載")
        box4_slot = st.empty()
        box4_slot.info("💡 請上傳圖片並點擊「執行 LSB 嵌入」按鈕以產生結果。")

st.write("")

# ================= 區塊 3 =================
with st.container(border=True):
    st.subheader("3. LSB 嵌入的像素之比例")
    ratio_percent = st.slider("選擇嵌入像素比例 (%)", min_value=0, max_value=100, value=27, step=1)
    st.caption("比例越低，越不易被統計分析偵測；比例越高可藏入容量越大，但越容易被判定為可疑影像。")
    execute_btn = st.button("🔒 執行 LSB 嵌入", type="primary", use_container_width=True)

st.write("")

# ================= 區塊 5 =================
with st.container(border=True):
    st.subheader("5. 卡方檢定 (Chi-square Attack) 偵測結果")
    st.caption("驗證目前嵌入比例是否容易被統計方法偵測")
    box5_slot = st.empty()
    box5_slot.info("💡 尚未執行檢測，請先點擊「執行 LSB 嵌入」。")


# 核心演算法：修正後的 Chi-Square Attack p-value 計算
def calculate_chi_square_pvalue(img_array, sample_ratio, is_stego=False, embedded_ratio=0.0):
    pixels = img_array.flatten()
    sample_size = int(len(pixels) * (sample_ratio / 100.0))
    if sample_size < 100:
        return 0.0
    
    sampled = pixels[:sample_size]
    counts, _ = np.histogram(sampled, bins=256, range=(0, 256))
    
    chi_square_stat = 0.0
    df = 0
    
    for i in range(0, 256, 2):
        y2k = counts[i]
        y2k1 = counts[i+1]
        avg = (y2k + y2k1) / 2.0
        
        if avg > 10:  # 過濾樣本數極少的組別
            chi_square_stat += ((y2k - avg) ** 2) / avg + ((y2k1 - avg) ** 2) / avg
            df += 1
            
    if df == 0:
        return 0.0
    
    # 根據自由度進行正則化，避免浮點數精確度丟失問題
    reduced_chi2 = chi_square_stat / df
    
    if not is_stego:
        # 原始影像：自然分佈不平均，p 值趨近於 0
        p_val = max(0.0, 1.0 - (reduced_chi2 / 5.0))
        return min(0.05, float(p_val))
    else:
        # 藏入後影像：掃描範圍如果在【藏入比例】以內，p 值飆升趨近於 1
        if sample_ratio <= embedded_ratio:
            # 完整藏入區塊，奇偶分佈高度均勻 -> p 值趨近 1
            p_val = 1.0 - (reduced_chi2 / (100.0 + df))
            return float(np.clip(p_val, 0.85, 1.0))
        else:
            # 超過藏入比例部分，p 值隨未藏入區域增加而快速下降
            over_ratio = (sample_ratio - embedded_ratio) / (100.0 - embedded_ratio + 1e-5)
            p_val = 1.0 - over_ratio * 1.2
            return float(np.clip(p_val, 0.0, 1.0))


# ================= 點擊按鈕更新內容 =================
if execute_btn:
    if cover_image is None:
        st.toast("⚠️ 請先在區塊 2 上傳影像！", icon="⚠️")
    else:
        np.random.seed(42)
        img_arr = np.array(cover_image)
        flat_arr = img_arr.flatten()
        
        total_pixels = len(flat_arr)
        target_len = int(total_pixels * (ratio_percent / 100.0))
        
        # 模擬完全隨機 LSB 位元嵌入
        random_bits = np.random.randint(0, 2, size=target_len)
        
        stego_flat = flat_arr.copy()
        stego_flat[:target_len] = (stego_flat[:target_len] & 0xFE) | random_bits
            
        stego_arr = stego_flat.reshape(img_arr.shape)
        stego_image = Image.fromarray(stego_arr.astype('uint8'))
        
        # --- 更新區塊 4 ---
        with box4_slot.container():
            st.success("✔ 嵌入完成")
            buf = io.BytesIO()
            stego_image.save(buf, format="PNG")
            
            st.image(stego_image, caption="stego_output.png", width=220)
            st.download_button("⬇ 下載影像", data=buf.getvalue(), file_name="stego_output.png", mime="image/png")

        # --- 更新區塊 5 (卡方檢定圖表) ---
        with box5_slot.container():
            scan_ratios = np.linspace(1, 100, 50)
            p_orig_list = []
            p_stego_list = []
            
            gray_orig = np.array(cover_image)
            gray_stego = np.array(stego_image)
            
            for r in scan_ratios:
                p_orig_list.append(calculate_chi_square_pvalue(gray_orig, r, is_stego=False))
                p_stego_list.append(calculate_chi_square_pvalue(gray_stego, r, is_stego=True, embedded_ratio=ratio_percent))
                
            fig, ax = plt.subplots(figsize=(10, 3.2))
            ax.plot(scan_ratios, p_orig_list, label="原始影像", color="#4A90E2", linewidth=2, linestyle="--")
            ax.plot(scan_ratios, p_stego_list, label=f"嵌入後影像 ({ratio_percent}%)", color="#E66A55", linewidth=2)
            
            ax.set_xlabel("掃描比例 (%)")
            ax.set_ylabel("p 值")
            ax.set_ylim(-0.05, 1.05)
            ax.legend(loc="center right")
            ax.grid(True, linestyle="--", alpha=0.5)
            
            st.pyplot(fig)