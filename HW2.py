import gradio as gr

# 預設同義詞庫 (代表0的詞, 代表1的詞)
DEFAULT_DICTIONARY = """陽光開朗,開朗樂觀
戶外活動,戶外運動
旅行,旅遊
慢跑,跑步
豐富,充實
令人嚮往,令人羨慕"""

def parse_dictionary(dict_str):
    """解析同義詞庫"""
    rules = []
    lines = dict_str.strip().split('\n')
    for line in lines:
        if ',' in line:
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 2:
                rules.append((parts[0], parts[1]))
    return rules

def generate_preview(text, dict_str, bit_input):
    """根據輸入文字、詞彙庫與自訂的欲嵌入位元序列產生對照表"""
    rules = parse_dictionary(dict_str)
    table_data = []
    
    # 清理位元輸入，只留 0 和 1
    clean_bits = [b for b in bit_input if b in ['0', '1']]
    
    bit_idx = 0
    for w0, w1 in rules:
        # 檢查文本中是否有該同義詞組中的任何一個詞
        matched_word = None
        if w0 in text:
            matched_word = w0
        elif w1 in text:
            matched_word = w1
            
        if matched_word:
            # 若還有可嵌入的位元，則根據位元選擇要替換的詞，否則維持原詞
            if bit_idx < len(clean_bits):
                target_bit = clean_bits[bit_idx]
                selected_word = w0 if target_bit == '0' else w1
                table_data.append([matched_word, target_bit, selected_word])
                bit_idx += 1
            else:
                table_data.append([matched_word, "無位元", matched_word])
                
    return table_data

def embed_watermark(text, dict_str, bit_input):
    """執行浮水印嵌入：根據使用者輸入的位元序列進行同義詞替換"""
    rules = parse_dictionary(dict_str)
    clean_bits = [b for b in bit_input if b in ['0', '1']]
    
    output_text = text
    bit_idx = 0
    
    for w0, w1 in rules:
        if bit_idx >= len(clean_bits):
            break
            
        target_bit = clean_bits[bit_idx]
        target_word = w0 if target_bit == '0' else w1
        
        # 如果文本包含 w0 或 w1，替換為目標位元對應的詞彙
        if w0 in output_text:
            output_text = output_text.replace(w0, target_word, 1)
            bit_idx += 1
        elif w1 in output_text:
            output_text = output_text.replace(w1, target_word, 1)
            bit_idx += 1
            
    return output_text

def extract_watermark(watermarked_text, dict_str):
    """從含浮水印的文字中擷取浮水印位元"""
    rules = parse_dictionary(dict_str)
    found_matches = []
    
    for w0, w1 in rules:
        pos0 = watermarked_text.find(w0)
        if pos0 != -1:
            found_matches.append((pos0, "0"))
        pos1 = watermarked_text.find(w1)
        if pos1 != -1:
            found_matches.append((pos1, "1"))
            
    # 按照在文本中出現的位置順序排序
    found_matches.sort(key=lambda x: x[0])
    extracted_bits = [b for pos, b in found_matches]
    
    result_str = "".join(extracted_bits) if extracted_bits else "未偵測到浮水印位元"
    return result_str

# --- 建立 Gradio UI 介面 ---
with gr.Blocks(title="文字浮水印嵌入 / 擷取系統") as demo:
    gr.Markdown("# 文字浮水印嵌入 / 擷取系統")
    gr.Markdown("**同義詞替換法 (Synonym Substitution Linguistic Steganography)**")
    
    # 1. 輸入原始文字
    gr.Markdown("### 1️⃣ 輸入原始文字")
    input_text = gr.Textbox(
        label="使用者欲嵌入浮水印的文句", 
        lines=3, 
        value="他是一個陽光開朗的好青年，喜歡戶外活動、旅行、游泳與慢跑，過著豐富跟充滿鬥志的生活，這實在是令人嚮往的一件事。"
    )
    
    with gr.Row():
        with gr.Column():
            # 2. 同義詞對照表
            gr.Markdown("### 2️⃣ 同義詞對照表（詞彙庫）")
            gr.Markdown("格式：每行一組 `代表0的詞,代表1的詞`，可自行新增/編輯同義詞")
            dict_input = gr.Textbox(
                label="詞彙庫", 
                lines=8, 
                value=DEFAULT_DICTIONARY
            )
            
        with gr.Column():
            # 3. 欲嵌入位元序列
            gr.Markdown("### 3️⃣ 欲嵌入位元序列")
            bit_input = gr.Textbox(
                label="欲嵌入位元序列 (可自由修改 0/1 組合)", 
                value="010111", 
                interactive=True
            )
            
            mapping_table = gr.Dataframe(
                headers=["載體詞 (依序)", "位元", "選用詞彙"],
                value=[
                    ["陽光開朗", "0", "陽光開朗"],
                    ["戶外活動", "1", "戶外運動"],
                    ["旅行", "0", "旅行"],
                    ["慢跑", "1", "跑步"],
                    ["豐富", "1", "充實"],
                    ["令人嚮往", "1", "令人羨慕"]
                ],
                interactive=False
            )
            
            # 【核心按鈕】嵌入數位浮水印按鈕
            embed_btn = gr.Button("🔒 藏入數位浮水印", variant="primary")
            
    # 4. 嵌入浮水印之後的輸出文字
    gr.Markdown("### 4️⃣ 嵌入浮水印之後之輸出文字")
    output_text = gr.Textbox(
        label="含浮水印文本", 
        lines=3, 
        interactive=False,
        value="他是一個陽光開朗的好青年，喜歡戶外運動、旅行、游泳與跑步，過著充實跟充滿鬥志的生活，這實在是令人羨慕的一件事。"
    )
    
    # 5. 擷取文字浮水印
    gr.Markdown("### 5️⃣ 擷取文字浮水印")
    with gr.Row():
        with gr.Column(scale=2):
            extract_input = gr.Textbox(
                label="貼入含浮水印之文句，比對詞彙庫還原位元", 
                lines=3,
                value="他是一個陽光開朗的好青年，喜歡戶外運動、旅行、游泳與跑步，過著充實跟充滿鬥志的生活，這實在是令人羨慕的一件事。"
            )
            extract_btn = gr.Button("🔍 擷取浮水印")
        with gr.Column(scale=1):
            extracted_bits_output = gr.Textbox(label="還原出來的位元序列", lines=3, interactive=False)

    # --- 事件綁定 ---
    # 當原始文字、詞庫或欲嵌入位元改變時，動態更新預覽表格
    input_text.change(fn=generate_preview, inputs=[input_text, dict_input, bit_input], outputs=[mapping_table])
    dict_input.change(fn=generate_preview, inputs=[input_text, dict_input, bit_input], outputs=[mapping_table])
    bit_input.change(fn=generate_preview, inputs=[input_text, dict_input, bit_input], outputs=[mapping_table])
    
    # 點擊「藏入數位浮水印」按鈕執行嵌入
    embed_btn.click(fn=embed_watermark, inputs=[input_text, dict_input, bit_input], outputs=[output_text])
    
    # 點擊「擷取浮水印」按鈕執行擷取
    extract_btn.click(fn=extract_watermark, inputs=[extract_input, dict_input], outputs=[extracted_bits_output])

if __name__ == "__main__":
    demo.launch()