import os
from sentence_transformers import SentenceTransformer

def download_model(model_name, save_path):
    print(f"开始下载模型: {model_name} ...")
    model = SentenceTransformer(model_name)
    os.makedirs(save_path, exist_ok=True)
    model.save(save_path)
    print(f"✅ 模型已下载并保存至: {save_path}")

if __name__ == "__main__":
    MODEL_NAME = "BAAI/bge-small-zh-v1.5"
    # utils 上一级是根目录
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # 保存路径不再包含作者前缀，只保留模型名
    SAVE_DIR = os.path.join(root_dir, "models", "bge-small-zh-v1.5")
    
    download_model(MODEL_NAME, SAVE_DIR)