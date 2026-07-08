import os
import io
import gc
import json
import base64
import random
import torch

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter
from .support.cqdm import cqdm
from .support.gguf_layers import get_layer_count
from .support.prompt_enhancer_preset import *

import folder_paths
import comfy.model_management as mm
import comfy.utils

from llama_cpp import Llama
from llama_cpp.llama_chat_format import (
    Llava15ChatHandler, Llava16ChatHandler, MoondreamChatHandler,
    NanoLlavaChatHandler, Llama3VisionAlphaChatHandler, MiniCPMv26ChatHandler
)

try:
    from llama_cpp.llama_chat_format import MTMDChatHandler
    _MTMD = True
except:
    _MTMD = False

# ========== chat_handlers ==========
chat_handlers = [
    "None",
    "LLaVA-1.5",
    "LLaVA-1.6",
    "Moondream2",
    "nanoLLaVA",
    "llama3-Vision-Alpha",
    "MiniCPM-v2.6",
    "MiniCPM-v4.5",
    "Gemma3",
    "Gemma4",
    "Qwen2.5-VL",
    "Qwen3-VL",
    "Qwen3.5/3.6",
    "GLM-4.6V",
    "GLM-4.1V",
    "LFM2-VL",
    "LFM2.5-VL",
    "Granite-Docling"
]

# 导入各个 ChatHandler
try:
    from llama_cpp.llama_chat_format import Gemma3ChatHandler
except:
    Gemma3ChatHandler = None

try:
    from llama_cpp.llama_chat_format import Gemma4ChatHandler
except:
    Gemma4ChatHandler = None

try:
    from llama_cpp.llama_chat_format import Qwen25VLChatHandler
except:
    Qwen25VLChatHandler = None

try:
    from llama_cpp.llama_chat_format import Qwen3VLChatHandler
except:
    Qwen3VLChatHandler = None

try:
    from llama_cpp.llama_chat_format import Qwen35ChatHandler
except:
    Qwen35ChatHandler = None

try:
    from llama_cpp.llama_chat_format import GLM46VChatHandler, GLM41VChatHandler
except:
    GLM46VChatHandler = None
    GLM41VChatHandler = None

try:
    from llama_cpp.llama_chat_format import LFM2VLChatHandler
except:
    LFM2VLChatHandler = None

try:
    from llama_cpp.llama_chat_format import LFM25VLChatHandler
except:
    LFM25VLChatHandler = None

try:
    from llama_cpp.llama_chat_format import GraniteDoclingChatHandler
except:
    GraniteDoclingChatHandler = None


class AnyType(str):
    def __ne__(self, __value: object) -> bool:
        return False


class LLAMA_CPP_STORAGE:
    llm = None
    chat_handler = None
    current_config = None
    messages = {}
    sys_prompts = {}

    @classmethod
    def clean_state(cls, id=-1):
        if id == -1:
            cls.messages.clear()
            cls.sys_prompts.clear()
        else:
            cls.messages.pop(f"{id}", None)
            cls.sys_prompts.pop(f"{id}", None)

    @classmethod
    def clean(cls, all=False):
        if cls.llm is not None:
            try:
                cls.llm.close()
            except Exception:
                pass
            cls.llm = None

        if cls.chat_handler is not None:
            try:
                if hasattr(cls.chat_handler, '_exit_stack'):
                    cls.chat_handler._exit_stack.close()
            except Exception:
                pass
            cls.chat_handler = None

        cls.current_config = None
        if all:
            cls.clean_state()
        gc.collect()
        mm.soft_empty_cache()

    @classmethod
    def load_model(cls, config):
        def get_chat_handler(chat_handler):
            if chat_handler in ("Qwen3.5-Thinking", "Qwen3.6-Thinking", "Qwen3.5", "Qwen3.6"):
                chat_handler = "Qwen3.5/3.6"
            if chat_handler in ("Qwen3-VL-Thinking",):
                chat_handler = "Qwen3-VL"
            if chat_handler in ("MiniCPM-v4.5-Thinking",):
                chat_handler = "MiniCPM-v4.5"
            if chat_handler in ("GLM-4.6V-Thinking",):
                chat_handler = "GLM-4.6V"
            if chat_handler in ("GLM-4.1V-Thinking",):
                chat_handler = "GLM-4.1V"

            match chat_handler:
                case "Qwen3.5/3.6":
                    if Qwen35ChatHandler is None:
                        raise ImportError("Qwen35ChatHandler not available. Please install JamePeng/llama-cpp-python.")
                    return Qwen35ChatHandler
                case "Qwen3-VL":
                    if Qwen3VLChatHandler is None:
                        raise ImportError("Qwen3VLChatHandler not available.")
                    return Qwen3VLChatHandler
                case "Qwen2.5-VL":
                    if Qwen25VLChatHandler is None:
                        raise ImportError("Qwen25VLChatHandler not available.")
                    return Qwen25VLChatHandler
                case "LLaVA-1.5":
                    return Llava15ChatHandler
                case "LLaVA-1.6":
                    return Llava16ChatHandler
                case "Moondream2":
                    return MoondreamChatHandler
                case "nanoLLaVA":
                    return NanoLlavaChatHandler
                case "llama3-Vision-Alpha":
                    return Llama3VisionAlphaChatHandler
                case "MiniCPM-v2.6":
                    return MiniCPMv26ChatHandler
                case "MiniCPM-v4.5":
                    return MiniCPMv26ChatHandler
                case "Gemma3":
                    if Gemma3ChatHandler is None:
                        raise ImportError("Gemma3ChatHandler not available.")
                    return Gemma3ChatHandler
                case "Gemma4":
                    if Gemma4ChatHandler is None:
                        raise ImportError("Gemma4ChatHandler not available. Please install JamePeng/llama-cpp-python with Gemma4 support.")
                    return Gemma4ChatHandler
                case "GLM-4.6V":
                    if GLM46VChatHandler is None:
                        raise ImportError("GLM46VChatHandler not available.")
                    return GLM46VChatHandler
                case "GLM-4.1V":
                    if GLM41VChatHandler is None:
                        raise ImportError("GLM41VChatHandler not available.")
                    return GLM41VChatHandler
                case "LFM2-VL":
                    if LFM2VLChatHandler is None:
                        raise ImportError("LFM2VLChatHandler not available.")
                    return LFM2VLChatHandler
                case "LFM2.5-VL":
                    if LFM25VLChatHandler is None:
                        raise ImportError("LFM25VLChatHandler not available.")
                    return LFM25VLChatHandler
                case "Granite-Docling":
                    if GraniteDoclingChatHandler is None:
                        raise ImportError("GraniteDoclingChatHandler not available.")
                    return GraniteDoclingChatHandler
                case "None":
                    return None
                case _:
                    raise ValueError(f'Unknown chat_handler: "{chat_handler}"')

        cls.clean(all=True)
        cls.current_config = config.copy()
        model = config["model"]
        mmproj = config["mmproj"]
        chat_handler = config["chat_handler"]
        n_ctx = config["n_ctx"]
        vram_limit = config["vram_limit"]
        image_max_tokens = config["image_max_tokens"]
        image_min_tokens = config["image_min_tokens"]
        n_gpu_layers = -1

        model_path = os.path.join(folder_paths.models_dir, 'LLM', model)

        # ========== 智能处理 chat_handler 与 mmproj 的关系 ==========
        if mmproj in (None, "None"):
            if chat_handler != "None":
                print(f"[llama-cpp_vlm] WARNING: mmproj is not provided, but chat_handler='{chat_handler}' is specified.")
                print(f"[llama-cpp_vlm] Forcing chat_handler to 'None' to use GGUF built-in chat template.")
                chat_handler = "None"
            handler = None
            handler_kwargs = {}
        else:
            if chat_handler == "None":
                raise ValueError(f"mmproj '{mmproj}' requires a non-None chat_handler (e.g., Qwen2.5-VL, LLaVA-1.5, etc.).")
            handler = get_chat_handler(chat_handler)
            handler_kwargs = {"verbose": False}
            if _MTMD:
                handler_kwargs["image_max_tokens"] = image_max_tokens
                handler_kwargs["image_min_tokens"] = image_min_tokens

        # VRAM 计算（仅多模态时需要）
        if vram_limit != -1 and mmproj not in (None, "None"):
            try:
                gguf_layers = get_layer_count(model_path) or 32
                gguf_size = os.path.getsize(model_path) * 1.2 / (1024 ** 3)
                gguf_layer_size = max(gguf_size / gguf_layers, 0.05)
            except Exception as e:
                print(f"[llama-cpp_vlm] VRAM calculation failed: {e}, falling back to -1")
                n_gpu_layers = -1

        # 加载 mmproj（多模态模型）
        if mmproj not in (None, "None"):
            mmproj_path = os.path.join(folder_paths.models_dir, 'LLM', mmproj)
            if vram_limit != -1 and n_gpu_layers != -1:
                mmproj_size = os.path.getsize(mmproj_path) * 1.2 / (1024 ** 3)
                if vram_limit - mmproj_size <= 0:
                    print(f"[llama-cpp_vlm] VRAM limit {vram_limit}GB too low for mmproj {mmproj_size:.2f}GB, forcing CPU offload")
                    n_gpu_layers = 0
                else:
                    n_gpu_layers = min(gguf_layers, max(1, int((vram_limit - mmproj_size) / gguf_layer_size)))
            print(f"[llama-cpp_vlm] Loading clip: {mmproj}")
            handler_kwargs["clip_model_path"] = mmproj_path
        else:
            # 纯文本模型：无需 mmproj 路径
            pass

        # 基于 chat_handler 或模型文件名检测
        is_qwen = False
        # 首先检查 chat_handler 是否包含 "Qwen"
        if "qwen" in chat_handler.lower():
            is_qwen = True
        # 其次检查模型文件名（不区分大小写）
        elif "qwen" in model.lower():
            is_qwen = True

        chat_template_kwargs = {}
        if is_qwen:
            chat_template_kwargs["enable_thinking"] = False
            print("[llama-cpp_vlm] Qwen model detected, automatically disabling thinking via chat_template_kwargs.")


        # 实例化 chat_handler（只有多模态模型需要）
        if handler is not None:
            try:
                cls.chat_handler = handler(**handler_kwargs)
            except Exception as e:
                raise RuntimeError(f"{e}\nPlease update llama-cpp-python from 'https://github.com/JamePeng/llama-cpp-python/releases'")
        else:
            cls.chat_handler = None
            print("[llama-cpp_vlm] Pure text model: chat_handler set to None. Will use GGUF built-in chat template if available.")

        print(f"[llama-cpp_vlm] Loading model: {model}")
        print(f"[llama-cpp_vlm] n_gpu_layers = {n_gpu_layers}")

        cls.llm = Llama(
            model_path,
            chat_handler=cls.chat_handler,
            n_gpu_layers=n_gpu_layers,
            n_ctx=n_ctx,
            chat_template_kwargs={"enable_thinking": False}, 
            verbose=False
        )


any_type = AnyType("*")

if not hasattr(mm, "unload_all_models_backup"):
    mm.unload_all_models_backup = mm.unload_all_models
    def patched_unload_all_models(*args, **kwargs):
        LLAMA_CPP_STORAGE.clean(all=True)
        result = mm.unload_all_models_backup(*args, **kwargs)
        return result
    mm.unload_all_models = patched_unload_all_models
    print("[llama-cpp_vlm] Model cleanup hook applied!")

llm_extensions = ['.ckpt', '.pt', '.bin', '.pth', '.safetensors', '.gguf']
folder_paths.folder_names_and_paths["LLM"] = ([os.path.join(folder_paths.models_dir, "LLM")], llm_extensions)

# ========== 图像/视频反推预设提示词（已迁移至 .format 风格 + 命名占位符） ==========
preset_prompts = {
    "Empty - Nothing": "",
    "Normal - Describe": "Describe this {media_type}.",
    "Prompt Style - Tags": (
        "Your task is to generate a clean list of comma-separated tags for a text-to-{media_type} AI, based *only* on the visual information in the {media_type}. "
        "Limit the output to a maximum of 50 unique tags. Strictly describe visual elements like subject, clothing, environment, colors, lighting, and composition. "
        "Do not include abstract concepts, interpretations, marketing terms, or technical jargon (e.g., no 'SEO', 'brand-aligned', 'viral potential'). "
        "The goal is a concise list of visual descriptors. Avoid repeating tags."
    ),
    "Prompt Style - Simple": "Analyze the {media_type} and generate a simple, single-sentence text-to-{media_type} prompt. Describe the main subject and the setting concisely.",
    "Prompt Style - Detailed": "Generate a detailed, artistic text-to-{media_type} prompt based on the {media_type}. Combine the subject, their actions, the environment, lighting, and overall mood into a single, cohesive paragraph of about 2-3 sentences. Focus on key visual details.",
    "Prompt Style - Extreme Detailed": "Generate an extremely detailed and descriptive text-to-{media_type} prompt from the {media_type}. Create a rich paragraph that elaborates on the subject's appearance, textures of clothing, specific background elements, the quality and color of light, shadows, and the overall atmosphere. Aim for a highly descriptive and immersive prompt.",
    "Prompt Style - Cinematic": "Act as a master prompt engineer. Create a highly detailed and evocative prompt for an {media_type} generation AI. Describe the subject, their pose, the environment, the lighting, the mood, and the artistic style (e.g., photorealistic, cinematic, painterly). Weave all elements into a single, natural language paragraph, focusing on visual impact.",
    "Creative - Detailed Analysis": "Describe this {media_type} in detail, breaking down the subject, attire, accessories, background, and composition into separate sections.",
    "Creative - Summarize Video": "Summarize the key events and narrative points in this video.",
    "Creative - Short Story": "Write a short, imaginative story inspired by this {media_type}.",
    "Creative - Refine & Expand Prompt": (
        "Refine and enhance the following user prompt for creative text-to-{media_type} generation. "
        "Keep the meaning and keywords, make it more expressive and visually rich. "
        "Output **only the improved prompt text itself**, without any reasoning steps, thinking process, or additional commentary.\n\n"
        "User input: <input>{input}</input>"
    ),
    "Vision - *Bounding Box": (
        'Locate every instance that belongs to the following categories: "{input}". '
        'Report bbox coordinates in {{"bbox_2d": [x1, y1, x2, y2], "label": "string"}} JSON format as a List.'
    )
}
preset_tags = list(preset_prompts.keys())

# ========== 纯文本扩写预设提示词（使用命名占位符 + XML 标签包裹输入） ==========
text_preset_prompts = {
    "Empty - Nothing": "",

    "扩写-领域自适应": (
        "Role\n你是一位拥有全学科视觉知识的图像生成提示词专家。你的核心能力是：精准识别用户输入关键词的侧重点，自动判定其所属领域（如写实摄影、工业设计、平面海报、二次元动漫、3D动画、数字艺术等），并调用该领域的专业术语进行像素级的深度扩写。\n\n"
        "最高指令 (Absolute Command)\n\n"
        "1.语言自适应：识别用户输入语言。用户用中文提问，你输出中文指令；用户用英文提问，你输出英文指令。\n"
        "2.格式绝对纯净：严禁输出 Markdown 符号（如星号、井号）、严禁中英对照括号、严禁输出任何解释或前缀。\n"
        "3.领域自适应：必须先判断输入内容的领域属性，严禁跨领域混用术语（例如：严禁在平面设计类提示词中加入焦距参数，严禁在二次元插画中加入皮肤毛孔描写）。\n"
        "4.语义忠实：严格保留用户所有原始关键词，严禁擅自增删核心主体。\n"
        "5.拒绝抽象词汇：禁止使用高质量、精美等模糊词，必须转化为可感知的物理细节或专业艺术术语。\n\n"
        "核心逻辑 (领域判定与定向扩写)\n\n"
        "第一步：领域侧重点判定 (Domain Recognition)\n"
        "分析用户关键词，自动进入以下对应的专业模式：\n"
        "A. 摄影模式 (Photography)：侧重镜头焦段、光圈、胶片质感、真实皮肤/环境肌理。\n"
        "B. 工业/产品模式 (Product)：侧重材质工艺（CNC、阳极氧化）、商业布光（轮廓光）、结构精密感。\n"
        "C. 平面/海报模式 (Graphic Design)：侧重构图布局、负空间、排版占位感、矢量色彩。\n"
        "D. 二次元/漫画模式 (Anime/Manga)：侧重线条精细度（Line art）、赛璐璐阴影（Cel shading）、网点纸（Screen tones）、夸张的眼神细节、特定的画风特征。\n"
        "E. 3D动画/CGI模式 (3D Animation)：侧重次表面散射（SSS材质）、角色建模精度、电影级3D布光、渲染器风格（Pixar/Dreamworks风格）。\n"
        "F. 艺术/插画模式 (Art/Illustration)：侧重笔触质感、媒介（水墨、油画、水彩）、流派特征。\n\n"
        "第二步：专业维度填充 (Directional Supplement)\n"
        "主体与质感：动漫类强调线稿与填色；3D类强调建模与光影反弹；产品类强调加工工艺。\n"
        "环境与背景：根据模式补充细节。摄影类补自然环境；3D类补置景；插画类补意境或笔触背景。\n"
        "专业技术参数：匹配该领域最专业的后缀（如摄影的 35mm，3D类的 Octane render，二次元的 Cel shaded）。\n\n"
        "输出规范\n\n"
        "结构顺序：深度扩写的专业描述, [领域特定参数], 照片级写实的(针对写实类) 或 风格化的(针对非写实类), 高保真，超精细纹理，8K分辨率\n\n"
        "Input to expand: <input>{input}</input>"
    ),
     "扩写-自然语言": (
        "你是一位专业的AI绘画提示词工程师，擅长将简短描述转化为高质量、细节丰富的提示词。请按照以下步骤处理用户输入：\n\n"
        "1. 分析理解：\n"
        "   - 识别用户输入的核心主题和关键元素\n"
        "   - 确定画面类型（人物、风景、静物、概念艺术等）\n"
        "   - 提取已有的视觉细节、风格倾向和情感基调\n\n"
        "2. 结构化扩展：\n"
        "   - 主体描述：补充主体的详细特征（如人物的外貌、表情、服装、姿态；物体的材质、形状、纹理等）\n"
        "   - 场景环境：根据主题补充或完善场景信息（室内/室外、自然/城市、时代背景等）\n"
        "   - 构图视角：添加画面构图信息（视角高度、景别大小、主体位置、前景/背景关系等）\n"
        "   - 光影氛围：补充光源类型、光线方向、明暗对比、色调氛围等\n"
        "   - 风格化：根据内容补充适合的艺术风格、渲染技术或参考艺术家\n"
        "   - 质量标签：添加提升画面品质的技术描述（高细节、高分辨率、写实渲染等）\n\n"
        "3. 智能补全：\n"
        "   - 当用户输入缺少关键元素时，基于主题自动补充合理的场景、光源、环境氛围等\n"
        "   - 确保补充内容与主题风格协调一致，不产生冲突元素\n"
        "   - 保持原始意图的同时，丰富画面的叙事性和视觉层次\n\n"
        "4. 输出格式：\n"
        "   - 使用自然流畅的语言描述，避免机械堆砌关键词\n"
        "   - 按照视觉重要性排序元素，主体描述在前，环境氛围在后\n"
        "   - 直接输出完整提示词，不添加解释、分类标签或注释\n"
        "   - 控制提示词长度在适当范围内，确保核心元素突出\n\n"
        "请直接返回扩展后的完整提示词，不需要解释你的思考过程或添加额外说明。\n\n"
        "Input to expand: <input>{input}</input>"
    ),

    "扩写-Tag": (
        "你是一位专业的AI绘画提示词工程师，擅长将简短描述转化为高质量、细节丰富的提示词。请按照以下步骤处理用户输入：\n\n"
        "1. 分析理解：\n"
        "   - 识别用户输入的核心主题和关键元素\n"
        "   - 确定画面类型（人物、风景、静物、概念艺术等）\n"
        "   - 提取已有的视觉细节、风格倾向和情感基调\n\n"
        "2. 结构化扩展：\n"
        "   - 主体描述：补充主体的详细特征（如人物的外貌、表情、服装、姿态；物体的材质、形状、纹理等）\n"
        "   - 场景环境：根据主题补充或完善场景信息（室内/室外、自然/城市、时代背景等）\n"
        "   - 构图视角：添加画面构图信息（视角高度、景别大小、主体位置、前景/背景关系等）\n"
        "   - 光影氛围：补充光源类型、光线方向、明暗对比、色调氛围等\n"
        "   - 风格化：根据内容补充适合的艺术风格、渲染技术或参考艺术家\n"
        "   - 质量标签：添加提升画面品质的技术描述（高细节、高分辨率、写实渲染等）\n\n"
        "3. 智能补全：\n"
        "   - 当用户输入缺少关键元素时，基于主题自动补充合理的场景、光源、环境氛围等\n"
        "   - 确保补充内容与主题风格协调一致，不产生冲突元素\n"
        "   - 保持原始意图的同时，丰富画面的叙事性和视觉层次\n\n"
        "4. 输出格式：\n"
        "   - 直接输出标签，不添加任何分类或说明\n"
        "   - 按照视觉重要性排序元素，主体描述在前，环境氛围在后\n"
        "   - 控制提示词长度在适当范围内，确保核心元素突出\n\n"
        "请直接返回扩展后的完整提示词，不需要解释你的思考过程或添加额外说明。\n\n"
        "Input to expand: <input>{input}</input>"
    ),

    "Refine & Expand Prompt": (
        "You are an expert prompt engineer. Your task is to refine and expand the user's creative text into a highly expressive, vivid, and detailed prompt. "
        "Add sensory details, emotional tones, and rich vocabulary while preserving the original meaning and keywords. "
        "The output should be a single, flowing paragraph of 80–150 words that feels immersive and compelling. "
        "CRITICAL: Output ONLY the final refined prompt. Do not include any reasoning, thinking process, extra commentary, or markdown formatting.\n\n"
        "User input: <input>{input}</input>"
    ),

    "Expand Prompt for Image Generation": (
        "You are a master prompt engineer specializing in text-to-image generation. "
        "Your task is to expand the short user prompt into a **comprehensive, highly detailed, and visually rich image prompt** that can produce a perfect, high-quality image. "
        "Incorporate the following elements seamlessly into a single, natural language paragraph (100–200 words):\n"
        "- **Main subject(s):** Physical appearance, clothing, pose, expression, age, ethnicity, distinctive features.\n"
        "- **Environment & background:** Specific location (e.g., \"ancient forest at twilight\", \"cyberpunk alley after rain\"), depth cues, foreground/midground/background details.\n"
        "- **Lighting & atmosphere:** Light source (e.g., \"golden hour sunlight\", \"neon glow\", \"soft window light\"), shadows, mood (e.g., \"mysterious\", \"joyful\", \"melancholic\"), weather or time of day.\n"
        "- **Color & texture:** Dominant colors, color harmony (e.g., \"complementary blues and oranges\"), surface textures (e.g., \"rusty metal\", \"velvet\", \"glossy ceramic\").\n"
        "- **Composition & camera:** Camera angle (e.g., \"low angle\", \"eye-level\", \"bird's-eye view\"), shot type (e.g., \"close-up\", \"wide shot\", \"medium shot\"), depth of field (e.g., \"shallow depth of field with creamy bokeh\").\n"
        "- **Style & artistic direction:** Artistic style (e.g., \"photorealistic\", \"oil painting\", \"anime\", \"cinematic\"), quality modifiers (e.g., \"8K\", \"intricate details\", \"sharp focus\").\n\n"
        "CRITICAL RULES:\n"
        "- Output ONLY the final expanded prompt. No explanations, no reasoning, no extra text.\n"
        "- Write as a single, continuous paragraph—no bullet points, no line breaks inside the prompt.\n"
        "- Be specific and concrete. Use adjectives, but avoid clichés.\n"
        "- Do NOT repeat the original short prompt verbatim; integrate it naturally.\n\n"
        "Short prompt: <input>{input}</input>"
    ),

    "Expand Prompt for Video Generation": (
        "You are an expert prompt engineer for text-to-video AI models (e.g., Sora, Runway Gen-3, Pika Labs). "
        "Your task is to expand a short user prompt into a **detailed, temporally coherent, and visually dynamic video prompt** (150–250 words). "
        "The final prompt will be used to generate a short video clip. Include the following aspects in a single, flowing paragraph:\n"
        "- **Subject & action:** Clear description of main subjects, their movements, interactions, and temporal changes (e.g., \"a woman walks slowly, her hair blowing in the wind\", \"a car drifts around a corner, tires smoking\").\n"
        "- **Camera motion:** Specific camera movement (e.g., \"slow push-in\", \"crane shot rising\", \"handheld follow\", \"tracking shot from left to right\").\n"
        "- **Scene & environment transitions:** If applicable, describe any changes over time (e.g., \"time-lapse of clouds moving\", \"day to night transition\").\n"
        "- **Lighting dynamics:** How lighting evolves (e.g., \"sunset light gradually fades, replaced by neon signs turning on\").\n"
        "- **Mood & pacing:** Emotional tone (e.g., \"tense and hurried\", \"serene and slow\"), rhythm of cuts or scene changes.\n"
        "- **Visual consistency:** Ensure colors, style, and subject appearance remain stable across frames unless intentionally changing.\n\n"
        "CRITICAL RULES:\n"
        "- Output ONLY the final expanded prompt. No meta commentary, no reasoning.\n"
        "- Use present tense, active voice. Write as a single paragraph.\n"
        "- Do NOT include timestamps or frame numbers—describe natural flow.\n"
        "- Emphasize motion and temporal evolution, not just a static scene.\n\n"
        "Short prompt: <input>{input}</input>"
    ),
}
text_preset_tags = list(text_preset_prompts.keys())


def image2base64(image):
    img = Image.fromarray(image)
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=85)
    img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
    return img_base64


def parse_json(json_str):
    json_output = json_str.strip()
    if "```json" in json_output:
        parts = json_output.split("```json")
        if len(parts) > 1:
            json_output = parts[1].split("```")[0]
    elif "```" in json_output:
        json_output = json_output.split("```")[1].split("```")[0]
    try:
        parsed = json.loads(json_output.strip())
        return parsed if isinstance(parsed, list) else [parsed]
    except Exception as e:
        raise ValueError(f"Unable to load JSON data!\n{e}\nRaw: {json_str[:300]}")


def scale_image(image: torch.Tensor, max_size: int = 128):
    img_np = np.clip(255.0 * image.cpu().numpy().squeeze(), 0, 255).astype(np.uint8)
    img_pil = Image.fromarray(img_np)
    w, h = img_pil.size
    scale = min(max_size / max(w, h), 1.0)
    new_w, new_h = int(w * scale), int(h * scale)
    img_resized = img_pil.resize((new_w, new_h), Image.Resampling.LANCZOS)
    return np.array(img_resized)


def qwen3bbox(image, json, coord_scale=1000):
    img = Image.fromarray(np.clip(255.0 * image.cpu().numpy().squeeze(), 0, 255).astype(np.uint8))
    bboxes = []
    for item in json:
        x0, y0, x1, y1 = item["bbox_2d"]
        x0 = x0 / coord_scale * img.width
        y0 = y0 / coord_scale * img.height
        x1 = x1 / coord_scale * img.width
        y1 = y1 / coord_scale * img.height
        bboxes.append((x0, y0, x1, y1))
    return bboxes


def draw_bbox(image, json, mode, coord_scale=1000):
    label_colors = {}
    img = Image.fromarray(np.clip(255.0 * image.cpu().numpy().squeeze(), 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(img)
    for item in json:
        try:
            label = item["label"]
        except Exception:
            try:
                label = item["text_content"]
            except Exception:
                label = "bbox"
        x0, y0, x1, y1 = item["bbox_2d"]
        if mode in ["Qwen3-VL", "Qwen2.5-VL"]:
            x0 = x0 / coord_scale * img.width
            y0 = y0 / coord_scale * img.height
            x1 = x1 / coord_scale * img.width
            y1 = y1 / coord_scale * img.height
        bbox = (x0, y0, x1, y1)

        if label not in label_colors:
            label_colors[label] = tuple(random.randint(80, 180) for _ in range(3))
        color = label_colors[label]
        draw.rectangle(bbox, outline=color, width=4)
        text_y = max(0, y0 - 10)
        text_size = draw.textbbox((x0, text_y), label)
        draw.rectangle([text_size[0], text_size[1]-2, text_size[2]+4, text_size[3]+2], fill=color)
        draw.text((x0+2, text_y), label, fill=(255, 255, 255))
    return torch.from_numpy(np.array(img).astype(np.float32) / 255.0).unsqueeze(0)


# ================== NODES ==================

class llama_cpp_model_loader:
    @classmethod
    def INPUT_TYPES(s):
        all_llms = folder_paths.get_filename_list("LLM")
        model_list = [f for f in all_llms if "mmproj" not in f.lower()]
        mmproj_list = ["None"] + [f for f in all_llms if "mmproj" in f.lower()]
        return {
            "required": {
                "model": (model_list,),
                "mmproj": (mmproj_list, {"default": "None"}),
                "chat_handler": (chat_handlers, {"default": "None"}),
                "n_ctx": ("INT", {"default": 8192, "min": 1024, "max": 327680, "step": 128}),
                "vram_limit": ("INT", {"default": -1, "min": -1, "max": 1024, "step": 1}),
                "image_min_tokens": ("INT", {"default": 0, "min": 0, "max": 4096, "step": 32}),
                "image_max_tokens": ("INT", {"default": 0, "min": 0, "max": 4096, "step": 32}),
            }
        }
    RETURN_TYPES = ("LLAMACPPMODEL",)
    RETURN_NAMES = ("llama_model",)
    FUNCTION = "loadmodel"
    CATEGORY = "llama-cpp-vlm"

    def loadmodel(self, model, mmproj, chat_handler, n_ctx, vram_limit, image_min_tokens, image_max_tokens):
        custom_config = {
            "model": model,
            "mmproj": mmproj,
            "chat_handler": chat_handler,
            "n_ctx": n_ctx,
            "vram_limit": vram_limit,
            "image_min_tokens": image_min_tokens,
            "image_max_tokens": image_max_tokens,
        }
        if not LLAMA_CPP_STORAGE.llm or LLAMA_CPP_STORAGE.current_config != custom_config:
            print("[llama-cpp_vlm] Loading model...")
            LLAMA_CPP_STORAGE.load_model(custom_config)
        return (custom_config,)


class llama_cpp_instruct_adv:
    """图片/视频反推节点（已升级为 .format + 命名占位符，并兼容自动聊天模板）"""
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "llama_model": ("LLAMACPPMODEL",),
                "preset_prompt": (preset_tags, {"default": preset_tags[1]}),
                "custom_prompt": ("STRING", {"default": "", "multiline": True}),
                "system_prompt": ("STRING", {"multiline": True, "default": ""}),
                "inference_mode": (["one by one", "images", "video"], {"default": "one by one"}),
                "max_frames": ("INT", {"default": 24, "min": 2, "max": 1024, "step": 1}),
                "max_size": ("INT", {"default": 256, "min": 128, "max": 16384, "step": 64}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff, "step": 1}),
                "force_offload": ("BOOLEAN", {"default": False}),
                "save_states": ("BOOLEAN", {"default": False}),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
            "optional": {
                "parameters": ("LLAMACPPARAMS",),
                "images": ("IMAGE",),
                "queue_handler": (any_type, {}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("output", "output_list", "state_uid")
    OUTPUT_IS_LIST = (False, True, False)
    FUNCTION = "process"
    CATEGORY = "llama-cpp-vlm"

    def sanitize_messages(self, messages):
        clean_messages = messages.copy()
        for msg in clean_messages:
            content = msg.get("content")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "image_url":
                        item["image_url"]["url"] = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAACXBIWXMAAAsTAAALEwEAmpwYAAAADElEQVQImWP4//8/AAX+Av5Y8msOAAAAAElFTkSuQmCC"
        return clean_messages

    def process(self, llama_model, preset_prompt, custom_prompt, system_prompt, inference_mode,
                max_frames, max_size, seed, force_offload, save_states, unique_id,
                parameters=None, images=None, queue_handler=None):
        if not LLAMA_CPP_STORAGE.llm:
            LLAMA_CPP_STORAGE.load_model(llama_model)

        # 图片/视频反推专用默认参数（在遵循原图的基础上增加适度创意）
        if parameters is None:
            parameters = {
                "max_tokens": 1024,
                "top_k": 40,
                "top_p": 0.92,
                "min_p": 0.05,
                "typical_p": 1.0,
                "temperature": 0.75,
                "repeat_penalty": 1.1,
                "frequency_penalty": 0.2,
                "presence_penalty": 0.3,
                "mirostat_mode": 0,
                "mirostat_eta": 0.1,
                "mirostat_tau": 5.0,
                "reasoning_budget": 0,
            }

        if _MTMD:
            parameters.pop("presence_penalty", None)

        _uid = parameters.get("state_uid", None)
        _parameters = parameters.copy()
        _parameters.pop("state_uid", None)
        reasoning_budget = _parameters.pop("reasoning_budget", 0)

        uid = unique_id.rpartition('.')[-1] if _uid in (None, -1) else _uid

        last_sys_prompt = LLAMA_CPP_STORAGE.sys_prompts.get(f"{uid}", None)
        video_input = inference_mode == "video"
        system_prompts = "请将输入的图片序列当做视频而不是静态帧序列, " + system_prompt if video_input else system_prompt
        if last_sys_prompt != system_prompts:
            messages = []
            LLAMA_CPP_STORAGE.clean_state()
            LLAMA_CPP_STORAGE.sys_prompts[f"{uid}"] = system_prompts
            if system_prompts.strip():
                messages.append({"role": "system", "content": system_prompts})
        else:
            if save_states:
                try:
                    print(f"[llama-cpp_vlm] Loading state and history id={uid}...")
                    messages = LLAMA_CPP_STORAGE.messages.get(f"{uid}", [])
                except Exception:
                    messages = []
            else:
                messages = []

        out1 = ""
        out2 = []
        user_content = []
        if custom_prompt.strip() and "*" not in preset_prompt:
            user_content.append({"type": "text", "text": custom_prompt})
        else:
            template = preset_prompts[preset_prompt]
            media_type = "video" if video_input else "image"
            try:
                p = template.format(input=custom_prompt.strip(), media_type=media_type)
            except KeyError as e:
                missing = e.args[0]
                print(f"[WARN] Preset '{preset_prompt}' missing placeholder {{{missing}}}. Appending input.")
                p = f"{template}\n\n{missing.capitalize()}: {custom_prompt.strip()}"
            user_content.append({"type": "text", "text": p})

        # 判断是否有图像输入
        has_images = images is not None and (
            (isinstance(images, torch.Tensor) and images.numel() > 0) or
            (isinstance(images, list) and len(images) > 0)
        )

        if not has_images:
            # 纯文本场景：将 user_content 从列表转换为纯字符串，以兼容自动聊天模板
            if user_content and isinstance(user_content, list) and len(user_content) == 1 and user_content[0]["type"] == "text":
                user_content = user_content[0]["text"]
            messages.append({"role": "user", "content": user_content})
            output = LLAMA_CPP_STORAGE.llm.create_chat_completion(
                messages=messages, seed=seed, reasoning_budget=reasoning_budget,
                **_parameters
            )
            out1 = output['choices'][0]['message']['content'].removeprefix(": ").lstrip()
            out2 = [out1]
        else:
            # 有图像输入：必须使用多模态 chat_handler，content 保持列表格式
            if not hasattr(LLAMA_CPP_STORAGE.chat_handler, "clip_model_path") or LLAMA_CPP_STORAGE.chat_handler.clip_model_path is None:
                raise ValueError("Image input detected, but the loaded model is not configured with a mmproj module.")

            frames = images
            if video_input:
                indices = np.linspace(0, len(images) - 1, max_frames, dtype=int)
                frames = [images[i] for i in indices]

            if inference_mode == "one by one":
                tmp_list = []
                base_user_content = [
                    {"type": "text", "text": user_content[0]["text"]},
                    {"type": "image_url", "image_url": {"url": ""}}
                ]
                messages.append({"role": "user", "content": base_user_content})
                print(f"[llama-cpp_vlm] Start processing {len(frames)} images")

                for i, image in enumerate(frames):
                    if mm.processing_interrupted():
                        raise mm.InterruptProcessingException()
                    data = image2base64(np.clip(255.0 * image.cpu().numpy().squeeze(), 0, 255).astype(np.uint8))
                    current_content = messages[-1]["content"]
                    for item in current_content:
                        if item.get("type") == "image_url":
                            item["image_url"]["url"] = f"data:image/jpeg;base64,{data}"
                            break
                    output = LLAMA_CPP_STORAGE.llm.create_chat_completion(
                        messages=messages, seed=seed, reasoning_budget=reasoning_budget,
                        **_parameters
                    )
                    text = output['choices'][0]['message']['content'].removeprefix(": ").lstrip()
                    out2.append(text)
                    if len(frames) > 1:
                        tmp_list.append(f"====== Image {i+1} ======")
                    tmp_list.append(text)
                    for item in current_content:
                        if item.get("type") == "image_url":
                            item["image_url"]["url"] = ""
                out1 = "\n\n".join(tmp_list)
            else:
                for image in frames:
                    if len(frames) > 1:
                        data = image2base64(scale_image(image, max_size))
                    else:
                        data = image2base64(np.clip(255.0 * image.cpu().numpy().squeeze(), 0, 255).astype(np.uint8))
                    user_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}})
                messages.append({"role": "user", "content": user_content})
                output = LLAMA_CPP_STORAGE.llm.create_chat_completion(
                    messages=messages, seed=seed, reasoning_budget=reasoning_budget,
                    **_parameters
                )
                out1 = output['choices'][0]['message']['content'].removeprefix(": ").lstrip()
                out2 = [out1]

        if save_states:
            print(f"[llama-cpp_vlm] Saving state id={uid}...")
            messages.append({"role": "assistant", "content": out1})
            clear_message = self.sanitize_messages(messages)
            LLAMA_CPP_STORAGE.messages[f"{uid}"] = clear_message
        else:
            if not LLAMA_CPP_STORAGE.messages.get(f"{uid}"):
                LLAMA_CPP_STORAGE.sys_prompts.pop(f"{uid}", None)

        if force_offload:
            LLAMA_CPP_STORAGE.clean()

        del messages
        gc.collect()
        return (out1, out2, uid)


class llama_cpp_text_enhancer:
    """纯文本扩写/润色节点，使用 .format + XML 标签包裹输入，强制禁用思考模式，并采用高创意默认参数"""
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "llama_model": ("LLAMACPPMODEL",),
                "preset_prompt": (text_preset_tags, {"default": text_preset_tags[1]}),
                "custom_prompt": ("STRING", {"default": "", "multiline": True}),
                "system_prompt": ("STRING", {"multiline": True, "default": ""}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff, "step": 1}),
                "force_offload": ("BOOLEAN", {"default": False}),
                "save_states": ("BOOLEAN", {"default": False}),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
            "optional": {
                "parameters": ("LLAMACPPARAMS",),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("output",)
    FUNCTION = "process"
    CATEGORY = "llama-cpp-vlm"

    def sanitize_messages(self, messages):
        return messages.copy()

    def process(self, llama_model, preset_prompt, custom_prompt, system_prompt,
                seed, force_offload, save_states, unique_id,
                parameters=None):
        if not LLAMA_CPP_STORAGE.llm:
            LLAMA_CPP_STORAGE.load_model(llama_model)

        # 纯文本扩写专用默认参数（充分发挥创意，同时遵循原意）
        if parameters is None:
            parameters = {
                "max_tokens": 1024,
                "top_k": 60,
                "top_p": 0.96,
                "min_p": 0.08,
                "typical_p": 1.0,
                "temperature": 0.88,
                "repeat_penalty": 1.15,
                "frequency_penalty": 0.25,
                "presence_penalty": 0.4,
                "mirostat_mode": 0,
                "mirostat_eta": 0.1,
                "mirostat_tau": 5.0,
                "reasoning_budget": 0,
            }

        if _MTMD:
            parameters.pop("presence_penalty", None)

        _uid = parameters.get("state_uid", None)
        _parameters = parameters.copy()
        _parameters.pop("state_uid", None)
        # 强制禁用思考模式
        _parameters["reasoning_budget"] = 0

        uid = unique_id.rpartition('.')[-1] if _uid in (None, -1) else _uid

        last_sys_prompt = LLAMA_CPP_STORAGE.sys_prompts.get(f"{uid}", None)
        if last_sys_prompt != system_prompt:
            messages = []
            LLAMA_CPP_STORAGE.clean_state()
            LLAMA_CPP_STORAGE.sys_prompts[f"{uid}"] = system_prompt
            if system_prompt.strip():
                messages.append({"role": "system", "content": system_prompt})
        else:
            if save_states:
                try:
                    print(f"[llama-cpp_vlm] Loading text state id={uid}...")
                    messages = LLAMA_CPP_STORAGE.messages.get(f"{uid}", [])
                except Exception:
                    messages = []
            else:
                messages = []

        # 构建用户消息（纯文本，必须为字符串）
        if preset_prompt == "Empty - Nothing":
            user_content = custom_prompt.strip()
        else:
            template = text_preset_prompts[preset_prompt]
            try:
                user_content = template.format(input=custom_prompt.strip())
            except KeyError:
                # 兜底：如果模板缺少 {input} 占位符，则直接拼接
                print(f"[WARN] Preset '{preset_prompt}' missing '{{input}}' placeholder. Appending input.")
                user_content = f"{template}\n\nInput: <input>{custom_prompt.strip()}</input>"

        messages.append({"role": "user", "content": user_content})

        # 调用模型（纯文本模式）
        output = LLAMA_CPP_STORAGE.llm.create_chat_completion(
            messages=messages, seed=seed, **_parameters
        )
        out_text = output['choices'][0]['message']['content'].removeprefix(": ").lstrip()

        if save_states:
            print(f"[llama-cpp_vlm] Saving text state id={uid}...")
            messages.append({"role": "assistant", "content": out_text})
            clear_message = self.sanitize_messages(messages)
            LLAMA_CPP_STORAGE.messages[f"{uid}"] = clear_message
        else:
            if not LLAMA_CPP_STORAGE.messages.get(f"{uid}"):
                LLAMA_CPP_STORAGE.sys_prompts.pop(f"{uid}", None)

        if force_offload:
            LLAMA_CPP_STORAGE.clean()

        del messages
        gc.collect()
        return (out_text,)


class llama_cpp_parameters:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "max_tokens": ("INT", {"default": 1024, "min": 0, "max": 4096, "step": 1}),
                "top_k": ("INT", {"default": 20, "min": 0, "max": 1000, "step": 1}),
                "top_p": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 1.0, "step": 0.01}),
                "min_p": ("FLOAT", {"default": 0.05, "min": 0.0, "max": 1.0, "step": 0.01}),
                "typical_p": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "temperature": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 2.0, "step": 0.01}),
                "repeat_penalty": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 10.0, "step": 0.01}),
                "frequency_penalty": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "presence_penalty": ("FLOAT", {"default": 1.5, "min": 0.0, "max": 2.0, "step": 0.01}),
                "mirostat_mode": ("INT", {"default": 0, "min": 0, "max": 2, "step": 1}),
                "mirostat_eta": ("FLOAT", {"default": 0.1, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mirostat_tau": ("FLOAT", {"default": 5.0, "min": 0.0, "max": 10.0, "step": 0.01}),
                "state_uid": ("INT", {"default": -1, "min": -1, "max": 999999, "step": 1}),
                "reasoning_budget": ("INT", {
                    "default": 0,
                    "min": -1,
                    "max": 32768,
                    "step": 1,
                    "tooltip": "0 = disabled, -1 = unlimited, >0 = limited reasoning tokens"
                }),
            }
        }
    RETURN_TYPES = ("LLAMACPPARAMS",)
    RETURN_NAMES = ("parameters",)
    FUNCTION = "process"
    CATEGORY = "llama-cpp-vlm"

    def process(self, **kwargs):
        return (kwargs,)


class llama_cpp_clean_states:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "any": (any_type,),
                "state_uid": ("INT", {"default": -1, "min": -1, "max": 999999, "step": 1}),
            },
        }
    RETURN_TYPES = (any_type,)
    RETURN_NAMES = ("any",)
    FUNCTION = "process"
    CATEGORY = "llama-cpp-vlm"

    def process(self, any, state_uid):
        print(f"[llama-cpp_vlm] Cleaning up saved states {state_uid}...")
        LLAMA_CPP_STORAGE.clean_state(state_uid)
        return (any,)


class llama_cpp_unload_model:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"any": (any_type,)}}
    RETURN_TYPES = (any_type,)
    RETURN_NAMES = ("any",)
    FUNCTION = "process"
    CATEGORY = "llama-cpp-vlm"

    def process(self, any):
        print("[llama-cpp_vlm] Unloading llama model...")
        LLAMA_CPP_STORAGE.clean()
        return (any,)


class json_to_bbox:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "json": ("STRING", {"forceInput": True}),
                "mode": (["simple", "Qwen3-VL", "Qwen2.5-VL"], {"default": "simple"}),
                "label": ("STRING", {"default": "", "multiline": False}),
                "coord_scale": ("INT", {"default": 1000, "min": 1, "max": 10000, "step": 1}),
            },
            "optional": {"image": ("IMAGE",)},
        }
    RETURN_TYPES = ("BBOX", "IMAGE")
    RETURN_NAMES = ("bboxes", "image_list")
    OUTPUT_IS_LIST = (True, True)
    INPUT_IS_LIST = True
    FUNCTION = "process"
    CATEGORY = "llama-cpp-vlm"

    def process(self, json, mode, label, coord_scale, image=None):
        mode = mode[0]
        label = label[0]
        coord_scale = coord_scale[0] if isinstance(coord_scale, list) else coord_scale
        flat_images_list = []
        original_structure = []
        if image is not None:
            for img_batch in image:
                if img_batch.ndim == 3:
                    flat_images_list.append(img_batch.unsqueeze(0))
                    original_structure.append(1)
                else:
                    count = img_batch.shape[0]
                    original_structure.append(count)
                    for n in range(count):
                        flat_images_list.append(img_batch[n:n+1])
        total_images = len(flat_images_list)
        output_bboxes = []
        processed_flat_results = []
        for i, j in enumerate(json):
            bboxes = parse_json(j)
            if label != "":
                try:
                    bboxes = [item for item in bboxes if item["label"] == label]
                except Exception:
                    bboxes = [item for item in bboxes if item.get("text_content") == label]
            if total_images > 0:
                curr_idx = i if i < total_images else (total_images - 1)
                curr_img = flat_images_list[curr_idx]
                try:
                    res_img = draw_bbox(curr_img[0], bboxes, mode, coord_scale)
                    if res_img.ndim == 3:
                        res_img = res_img.unsqueeze(0)
                    elif res_img.ndim == 4 and res_img.shape[0] > 1:
                        res_img = res_img[0:1]
                    processed_flat_results.append(res_img)
                except Exception as e:
                    print(f"Error drawing on image {curr_idx}: {e}")
                    processed_flat_results.append(curr_img)
            if mode in ["Qwen3-VL", "Qwen2.5-VL"]:
                if total_images == 0:
                    raise ValueError("Image required for Qwen mode")
                curr_idx = i if i < total_images else (total_images - 1)
                bbox = qwen3bbox(flat_images_list[curr_idx][0], bboxes, coord_scale)
            else:
                bbox = [tuple(item["bbox_2d"]) for item in bboxes]
            output_bboxes.append(bbox)
        restructured_images_list = []
        cursor = 0
        for count in original_structure:
            chunk = processed_flat_results[cursor:cursor+count]
            if chunk:
                restructured_images_list.append(torch.cat(chunk, dim=0))
            cursor += count
        return (output_bboxes, restructured_images_list)


class SEG:
    def __init__(self, cropped_image, cropped_mask, confidence, crop_region, bbox, label, control_net_wrapper=None):
        self.cropped_image = cropped_image
        self.cropped_mask = cropped_mask
        self.confidence = confidence
        self.crop_region = crop_region
        self.bbox = bbox
        self.label = label
        self.control_net_wrapper = control_net_wrapper
    def __repr__(self):
        return (f"SEG(cropped_image={self.cropped_image}, cropped_mask=shape{self.cropped_mask.shape}, "
                f"confidence={self.confidence}, bbox={self.bbox}, label='{self.label}'), "
                f"control_net_wrapper={self.control_net_wrapper}")


class bbox_to_segs:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "bboxes": ("BBOX",),
                "image": ("IMAGE",),
                "dilation": ("INT", {"default": 10, "min": 0, "max": 200, "step": 1}),
                "feather": ("INT", {"default": 0, "min": 0, "max": 100, "step": 1}),
            }
        }
    RETURN_TYPES = ("SEGS",)
    FUNCTION = "process"
    CATEGORY = "llama-cpp-vlm"

    def process(self, bboxes, image, dilation, feather):
        _batch_size, height, width, _channels = image.shape
        mask_shape = (height, width)
        seg_list = []
        image_for_cropping = image[0]
        for bbox in bboxes:
            if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
                print(f"Warning: Skipping invalid bbox item: {bbox}")
                continue
            x1, y1, x2, y2 = map(int, bbox)
            x1_exp = x1 - dilation
            y1_exp = y1 - dilation
            x2_exp = x2 + dilation
            y2_exp = y2 + dilation
            crop_region = [x1_exp, y1_exp, x2_exp, y2_exp]
            crop_w = x2_exp - x1_exp
            crop_h = y2_exp - y1_exp
            if crop_h <= 0 or crop_w <= 0:
                continue
            local_mask_np = np.zeros((crop_h, crop_w), dtype=np.float32)
            local_x1 = dilation
            local_y1 = dilation
            local_x2 = local_x1 + (x2 - x1)
            local_y2 = local_y1 + (y2 - y1)
            local_mask_np[local_y1:local_y2, local_x1:local_x2] = 1.0
            if feather > 0:
                local_mask_np = gaussian_filter(local_mask_np, sigma=feather)
            cropped_mask_np = local_mask_np
            cropped_img_padded = torch.zeros((crop_h, crop_w, 3), dtype=image.dtype, device=image.device)
            src_x_start = max(0, x1_exp)
            src_y_start = max(0, y1_exp)
            src_x_end = min(width, x2_exp)
            src_y_end = min(height, y2_exp)
            dst_x_start = src_x_start - x1_exp
            dst_y_start = src_y_start - y1_exp
            dst_x_end = src_x_end - x1_exp
            dst_y_end = src_y_end - y1_exp
            if src_x_end > src_x_start and src_y_end > src_y_start:
                source_crop = image_for_cropping[src_y_start:src_y_end, src_x_start:src_x_end, :]
                cropped_img_padded[dst_y_start:dst_y_end, dst_x_start:dst_x_end, :] = source_crop
            cropped_image_tensor = cropped_img_padded.permute(2, 0, 1).unsqueeze(0)
            seg = SEG(
                cropped_image=cropped_image_tensor,
                cropped_mask=cropped_mask_np,
                confidence=np.array([0.9], dtype=np.float32),
                crop_region=crop_region,
                bbox=np.array(bbox, dtype=np.float32),
                label="bbox"
            )
            seg_list.append(seg)
        segs = (mask_shape, seg_list)
        return (segs,)


class bbox_to_mask:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "bboxes": ("BBOX",),
                "image": ("IMAGE",),
                "dilation": ("INT", {"default": 10, "min": 0, "max": 200, "step": 1}),
                "feather": ("INT", {"default": 0, "min": 0, "max": 100, "step": 1}),
            }
        }
    RETURN_TYPES = ("MASK",)
    RETURN_NAMES = ("mask",)
    FUNCTION = "process"
    CATEGORY = "llama-cpp-vlm"

    def process(self, bboxes, image, dilation, feather):
        masks = []
        _batch_size, height, width, _channels = image.shape
        mask_shape = (height, width)
        combined_full_mask = torch.zeros(mask_shape, dtype=torch.float32, device=image.device)
        for bbox in bboxes:
            if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
                print(f"Warning: Skipping invalid bbox item: {bbox}")
                continue
            x1, y1, x2, y2 = map(int, bbox)
            x1_exp = x1 - dilation
            y1_exp = y1 - dilation
            x2_exp = x2 + dilation
            y2_exp = y2 + dilation
            crop_w = x2_exp - x1_exp
            crop_h = y2_exp - y1_exp
            if crop_h <= 0 or crop_w <= 0:
                continue
            local_mask_np = np.zeros((crop_h, crop_w), dtype=np.float32)
            local_x1 = dilation
            local_y1 = dilation
            local_x2 = local_x1 + (x2 - x1)
            local_y2 = local_y1 + (y2 - y1)
            local_mask_np[local_y1:local_y2, local_x1:local_x2] = 1.0
            if feather > 0:
                local_mask_np = gaussian_filter(local_mask_np, sigma=feather)
            current_full_mask_np = np.zeros(mask_shape, dtype=np.float32)
            x1_c, y1_c = max(0, x1_exp), max(0, y1_exp)
            x2_c, y2_c = min(width, x2_exp), min(height, y2_exp)
            if x2_c > x1_c and y2_c > y1_c:
                current_full_mask_np[y1_c:y2_c, x1_c:x2_c] = 1.0
            if feather > 0:
                current_full_mask_np = gaussian_filter(current_full_mask_np, sigma=feather)
            current_full_mask_tensor = torch.from_numpy(current_full_mask_np).to(image.device)
            combined_full_mask = torch.maximum(combined_full_mask, current_full_mask_tensor)
        masks.append(combined_full_mask.unsqueeze(0))
        return (torch.cat(masks, dim=0),)


class bboxes_to_bbox:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "bboxes": ("BBOX",),
                "image_index": ("INT", {"default": 0, "min": 0, "max": 1000000, "step": 1}),
                "bbox_index": ("INT", {"default": 0, "min": -998, "max": 999, "step": 1}),
            }
        }
    RETURN_TYPES = ("BBOX",)
    RETURN_NAMES = ("bbox",)
    FUNCTION = "process"
    CATEGORY = "llama-cpp-vlm"

    def process(self, bboxes, image_index, bbox_index):
        if bbox_index != 999:
            return ([bboxes[image_index][bbox_index]],)
        return (bboxes[image_index],)


class parse_json_node:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {"input": ("STRING", {"forceInput": True})},
            "optional": {"key": ("STRING",), "default": ("STRING",)},
        }
    RETURN_TYPES = (any_type, "STRING", "INT", "FLOAT", "BOOLEAN")
    RETURN_NAMES = ("any", "string", "int", "float", "boolean")
    FUNCTION = "process"
    CATEGORY = "llama-cpp-vlm"

    def process(self, input, key=None, default=None):
        if isinstance(input, str):
            input = [input]
        result = {"any": [], "string": [], "int": [], "float": [], "boolean": []}
        for i, json_str in enumerate(input):
            val = ""
            if key is not None and key != "":
                val = get_nested_value(json_str.strip().removeprefix("```json").removesuffix("```"), key, default)
            else:
                raise ValueError("Key cannot be empty!")
            result["any"].append(val)
            try:
                result["string"].append(str(val))
            except Exception:
                result["string"].append(val)
            try:
                result["int"].append(int(val))
            except Exception:
                result["int"].append(val)
            try:
                result["float"].append(float(val))
            except Exception:
                result["float"].append(val)
            try:
                result["boolean"].append(val.lower() == "true")
            except Exception:
                result["boolean"].append(val)
        if len(result["any"]) == 1:
            result = {k: v[0] for k, v in result.items()}
        return (result["any"], result["string"], result["int"], result["float"], result["boolean"])


def get_nested_value(data, dotted_key, default=None):
    keys = dotted_key.split('.')
    for key in keys:
        if isinstance(data, str):
            data = json.loads(data)
        if isinstance(data, dict) and key in data:
            data = data[key]
        else:
            return default
    return data


class remove_code_block:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {"input": ("STRING", {"forceInput": True})},
            "optional": {"label": ("STRING",)},
        }
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("output",)
    FUNCTION = "process"
    CATEGORY = "llama-cpp-vlm"

    def process(self, input, label):
        if isinstance(input, str):
            input = [input]
        output = []
        for value in input:
            output.append(value.strip().removeprefix(f"```{label}").removesuffix("```"))
        if len(output) == 1:
            return (output[0],)
        return (output,)


class PromptEnhancerPreset:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "preset": (["Qwen-Image [EN]", "Qwen-Image [ZH]", "Qwen-Image 2512 [EN]", "Qwen-Image 2512 [ZH]",
                            "Qwen-Image-Edit", "Qwen-Image-Edit 2509", "Qwen-Image-Edit 2511", "Z-Image Turbo",
                            "Flux.2 T2I", "Flux.2 I2I", "Wan T2V [EN]", "Wan T2V [ZH]", "Wan I2V [EN]", "Wan I2V [ZH]",
                            "Wan I2V Full-Auto [EN]", "Wan I2V Full-Auto [ZH]", "Wan FLF2V [EN]", "Wan FLF2V [ZH]",
                            "喵呜图片精细反推", "扩写_人像大师", "扩写_Tags风格", "图像描述_Tag风格", "像素级描述_阿丹",
                            "黑兽", "图像编辑重绘_CJL", "图像到视频提示词_CJL", "全图反推_中文", "WAN分镜规则","ideogram4","性感古风", "Z_Engineer", "中文文生图"],)
            }
        }
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("system_prompt",)
    FUNCTION = "main"
    CATEGORY = "llama-cpp-vlm"

    def main(self, preset):
        match preset:
            case "Qwen-Image [EN]":
                return (QWEN_IMAGE_EN,)
            case "Qwen-Image [ZH]":
                return (QWEN_IMAGE_ZH,)
            case "Qwen-Image 2512 [EN]":
                return (QWEN_IMAGE_2512_EN,)
            case "Qwen-Image 2512 [ZH]":
                return (QWEN_IMAGE_2512_ZH,)
            case "Qwen-Image-Edit":
                return (QWEN_IMAGE_EDIT,)
            case "Qwen-Image-Edit 2509":
                return (QWEN_IMAGE_EDIT_2509,)
            case "Qwen-Image-Edit 2511":
                return (QWEN_IMAGE_EDIT_2511,)
            case "Z-Image Turbo":
                return (ZIMAGE_TURBO,)
            case "Flux.2 T2I":
                return (FLUX2_T2I,)
            case "Flux.2 I2I":
                return (FLUX2_I2I,)
            case "Wan T2V [EN]":
                return (WAN_T2V_EN,)
            case "Wan T2V [ZH]":
                return (WAN_T2V_ZH,)
            case "Wan I2V [EN]":
                return (WAN_I2V_EN,)
            case "Wan I2V [ZH]":
                return (WAN_I2V_ZH,)
            case "Wan I2V Full-Auto [EN]":
                return (WAN_I2V_EMPTY_EN,)
            case "Wan I2V Full-Auto [ZH]":
                return (WAN_I2V_EMPTY_ZH,)
            case "Wan FLF2V [EN]":
                return (WAN_FLF2V_EN,)
            case "Wan FLF2V [ZH]":
                return (WAN_FLF2V_ZH,)
            case "喵呜图片精细反推":
                return (喵呜图片精细反推,)
            case "扩写_人像大师":
                return (扩写_人像大师,)
            case "扩写_Tags风格":
                return (扩写_Tags风格,)
            case "图像描述_Tag风格":
                return (图像描述_Tag风格,)
            case "像素级描述_阿丹":
                return (像素级描述_阿丹,)
            case "黑兽":
                return (黑兽,)
            case "图像编辑重绘_CJL":
                return (图像编辑重绘_CJL,)
            case "图像到视频提示词_CJL":
                return (图像到视频提示词_CJL,)
            case "全图反推_中文":
                return (全图反推_中文,)
            case "WAN分镜规则":
                return (WAN分镜规则,)
            case "ideogram4":
                return (ideogram4,)
            case "性感古风":
                return (性感古风,)
            case "Z_Engineer":
                return (Z_Engineer,)
            case "中文文生图":
                return (中文文生图,)
            case _:
                raise ValueError(f'Unknown preset: "{preset}"')


NODE_CLASS_MAPPINGS = {
    "llama_cpp_model_loader": llama_cpp_model_loader,
    "llama_cpp_instruct_adv": llama_cpp_instruct_adv,
    "llama_cpp_text_enhancer": llama_cpp_text_enhancer,
    "llama_cpp_parameters": llama_cpp_parameters,
    "llama_cpp_unload_model": llama_cpp_unload_model,
    "llama_cpp_clean_states": llama_cpp_clean_states,
    "parse_json_node": parse_json_node,
    "json_to_bbox": json_to_bbox,
    "bbox_to_segs": bbox_to_segs,
    "bbox_to_mask": bbox_to_mask,
    "bboxes_to_bbox": bboxes_to_bbox,
    "remove_code_block": remove_code_block,
    "PromptEnhancerPreset": PromptEnhancerPreset,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "llama_cpp_model_loader": "Llama-cpp Model Loader",
    "llama_cpp_instruct_adv": "Llama-cpp Instruct (Image/Video)",
    "llama_cpp_text_enhancer": "Llama-cpp Text Enhancer (Pure Text)",
    "llama_cpp_parameters": "Llama-cpp Parameters",
    "llama_cpp_unload_model": "Llama-cpp Unload Model",
    "llama_cpp_clean_states": "Llama-cpp Clean States",
    "parse_json_node": "Parse JSON",
    "json_to_bbox": "JSON to BBoxes",
    "bbox_to_segs": "BBoxes to SEGS",
    "bbox_to_mask": "BBoxes to MASK",
    "bboxes_to_bbox": "BBoxes to BBox",
    "remove_code_block": "Unpack Code Block",
    "PromptEnhancerPreset": "Prompt Enhancer Preset",
}
