// API配置
export const API_BASE_URL = import.meta.env.DEV
  ? "http://localhost:2024"
  : "http://localhost:8123";

// 模型配置接口
export interface ModelConfig {
  model_id: string;
  display_name: string;
  icon: string;
  icon_color: string;
}

// 获取可用模型列表
export async function fetchAvailableModels(): Promise<ModelConfig[]> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/models`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = await response.json();
    return data.models || [];
  } catch (error) {
    console.error("获取模型列表失败:", error);
    // 返回默认模型列表作为降级方案
    return [
      { model_id: "qwen3.6-flash", display_name: "Qwen-Flash", icon: "Zap", icon_color: "yellow-400" },
      { model_id: "qwen3.6-plus", display_name: "Qwen-Plus", icon: "Zap", icon_color: "orange-400" },
      { model_id: "qwen3.7-max", display_name: "Qwen-Max", icon: "Cpu", icon_color: "purple-400" },
    ];
  }
}
