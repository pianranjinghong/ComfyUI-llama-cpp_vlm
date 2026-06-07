import os
import struct

def get_layer_count(path):
    """
    从 GGUF 文件中读取模型层数（block_count）
    返回 int 或 None
    """
    try:
        # 方法1：快速解析文件末尾元数据
        with open(path, 'rb') as f:
            f.seek(-512, 2)  # 从文件末尾倒数512字节开始
            tail = f.read()
            # 查找 "block_count" 字符串
            idx = tail.find(b'block_count')
            if idx >= 0:
                # 尝试提取后面的整数（4或8字节）
                data = tail[idx+11:idx+19]
                # 先尝试无符号32位
                try:
                    val = struct.unpack('<I', data[:4])[0]
                    if 0 < val < 1000:
                        return val
                except:
                    pass
                # 再尝试无符号64位
                try:
                    val = struct.unpack('<Q', data[:8])[0]
                    if 0 < val < 1000:
                        return val
                except:
                    pass
        # 方法2：使用 gguf 库完整解析
        print("Fast parse failed, trying gguf library...")
        try:
            from gguf import GGUFReader
            reader = GGUFReader(path)
            for k, v in reader.fields.items():
                if k.lower().endswith("block_count"):
                    return v.value
        except ImportError:
            print("gguf library not installed, cannot read layer count")
        except Exception as e:
            print(f"GGUF library error: {e}")
        return None
    except Exception as e:
        print(f"Error reading gguf layer count: {e}")
        return None
