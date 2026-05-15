import json
from config_runtime import SMALL_TALK_KEYWORDS
from utils.ollama_client import ask_ollama

SMALL_TALK = SMALL_TALK_KEYWORDS

def extract_user_preferences(dialog_text: str) -> dict:
    """
    提取用户偏好、习惯或特定的长期约束
    """
    prompt = f"""
    请分析以下对话，提取用户的【长期偏好】或【个性化习惯】。

    关注点：
    1. 技术栈偏好（如：喜欢 Python 还是 R，喜欢深度学习还是统计学）
    2. 输出格式偏好（如：喜欢表格、Markdown、还是纯文本）
    3. 关注领域（如：滑坡、地震、降雨、InSAR 等）
    4. 语言习惯（如：喜欢简洁、喜欢详细解释、专业术语等）

    如果未发现明显偏好，返回空 JSON {{}}。
    如果有发现，请返回 JSON 格式，例如：
    {{
        "tech_stack": "Python, PyTorch",
        "format": "Markdown tables",
        "focus_area": "Landslide susceptibility",
        "style": "Concise"
    }}

    【对话内容】
    {dialog_text}

    【JSON 结果】
    """
    try:
        res = ask_ollama(prompt).strip()
        start = res.find("{")
        end = res.rfind("}") + 1
        if start != -1 and end != -1:
            json_str = res[start:end]
            return json.loads(json_str)
    except Exception:
        pass
    return {}

def summarize_dialog(dialog_text: str) -> tuple[str, dict]:
    """
    地质专用摘要器：
    1. 剔除闲聊行
    2. ≤30 字中文压缩
    3. 提取用户偏好
    """
    lines = [line for line in dialog_text.splitlines() if not any(k in line.lower() for k in SMALL_TALK)]

    if not lines:
        return "", {}

    text = "\n".join(lines)
    preferences = extract_user_preferences(text)

    prompt = f"""
    你是地质滑坡防治专家。
    用≤30 字、中文、段落式、第三人称总结下列「地质专业内容」：

    保留：地质现象 / 诱因 / 防治方法 / 监测技术
    忽略：问候、自我介绍、与地质无关内容
    **必须把英文术语（slide、debris、monitoring 等）翻译成中文**，禁止出现英文。

    【对话】
    {text}

    【≤30 字中文摘要】
    """
    summary = ask_ollama(prompt).strip()

    return summary, preferences
