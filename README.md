# DeepResearch Quick Start

当前项目展示了如何使用Langgraph搭建一个DeepResearch的应用
<img src="./app.png" title="Use Langgraph to build an DeepResearch" alt="如何使用Langgraph搭建一个DeepResearch的应用" width="90%">

## 项目结构
当前项目目录分为以下两个结构
-   `frontend/`: 项目前端
-   `backend/`: 包含了核心的后端逻辑，所有的Agent体系的后端逻辑都在当前目录下

## 项目目录结构
```bash
deep research/
├── backend/                          # 后端服务目录
│   ├── src/
│   │   ├── agent/                    # 核心代理模块
│   │   │   ├── __init__.py
│   │   │   ├── app.py               # FastAPI 应用入口
│   │   │   ├── base_agent.py        # 基础代理类定义
│   │   │   ├── configuration.py     # 系统配置管理
│   │   │   ├── graph.py             # LangGraph 工作流定义
│   │   │   ├── state.py             # 状态数据结构定义
│   │   │   ├── tools_and_schemas.py # 工具和模式定义
│   │   │   ├── prompts.py           # 提示词模板
│   │   │   ├── post.py              # 后处理工具
│   │   │   ├── utils.py             # 工具函数
│   │   │   └── llm/                 # LLM 集成模块
│   │   │       ├── __init__.py
│   │   │       └── llm.py           # 大语言模型接口
│   │   └── main.py                  # 主程序入口
│   ├── langgraph.json               # LangGraph 配置文件
│   ├── pyproject.toml               # Python 项目配置
├── frontend/                        # 前端应用目录
│   ├── src/
│   │   ├── components/              # React 组件
│   │   │   ├── ActivityTimeline.tsx # 活动时间线组件
│   │   │   ├── ChatMessagesView.tsx # 聊天消息视图
│   │   │   ├── InputForm.tsx        # 输入表单组件
│   │   │   ├── WelcomeScreen.tsx    # 欢迎界面组件
│   │   │   └── ui/                  # UI 组件库
│   │   ├── App.tsx                  # 主应用组件
│   │   ├── main.tsx                 # 应用入口
│   │   └── global.css               # 全局样式
│   ├── package.json                 # Node.js 依赖配置
│   └── vite.config.ts               # Vite 构建配置
├── README.md                        # 项目说明文档，即本文档
└── run.sh                           # 启动脚本
```
## Quick Start
**1. 前期准备:**
- Node.js and npm (or yarn/pnpm)
- Python 3.11+
- miniconda或anaconda
- API Key，可以从[百炼](https://bailian.console.aliyun.com/)官网注册登录获取

**2. Install Dependencies:**

**Backend:**

```bash
cd backend
pip install .

# 以下可以不用，如果运行时发现缺失包，可以执行补充
pip install langgraph>=0.2.6
pip install langchain>=0.3.19
pip install openai
pip install python-dotenv>=1.0.1
pip install langgraph-sdk>=0.1.57
pip install langgraph-cli
pip install langgraph-api
pip install fastapi
```

**Frontend:**

```bash
cd frontend
npm install
```

**3. Run Development Servers:**
配置好相关的APIKey后，运行以下命令启动后端服务
```bash
run_backend.bat
```

运行以下命令启动前端服务
```bash
run_fontend.bat
```
MAC（linux）下可以参考run.sh，run.sh属于整体的运行和部署脚本
```bash
sh run.sh
```

**4. 启动后的接口**

后端服务在启动时会提供三个访问链接：  
1. API: http://127.0.0.1:2024  
用途：LangGraph 后端服务的根地址  
功能：提供所有 LangGraph 自动生成的标准端点（如 /runs/stream、/threads 等）、处理前端的流式通信请求、执行 Agent 工作流（graph.py 定义的研究流程）、包含自定义的 /api/models 接口（获取模型列表），前端应用通过 LangGraph SDK 调用

2. Studio UI: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024  
用途：LangSmith Studio 可视化调试界面  
功能：  
📊 可视化监控：实时查看 Agent 的执行流程和状态  
🔍 调试工具：追踪每个节点（generate_search、web_search、critique、final_answer）的执行情况  
📝 日志查看：查看每次运行的详细日志和中间结果  
🎯 性能分析：分析各阶段的耗时和 token 使用情况  
💾 历史记录：保存和回放历史运行记录  
开发者用于调试和优化 Agent

3. API Docs: http://127.0.0.1:2024/docs  
用途：FastAPI 自动生成的 Swagger UI 文档  
功能：  
📖 API 文档：展示所有可用的 API 端点及其参数  
🧪 在线测试：可以直接在浏览器中测试 API 接口  
📋 Schema 查看：查看请求/响应的数据结构定义  

**4. 基础版参考查询请求**
```bash
DeepSeek资深研究员陈德里近日在社交媒体发布信息证实：DeepSeek正在组织一个新的Harness团队做Harness方向的产品和研究，并直言：简单来说就是对标Claude Code，做DeepSeek Code Harness。如何评价DeepSeek成立Harness团队？
```

```bash
规范驱动开发SDD和AGENTS.md的关系是什么？
```

```bash
目前AICoding的工具有Claude Code（以及Claude Code插件）、Codex、Curosr、Trae、CodeBuddy、Qoder、通义灵码插件等等。现在请仔细分析这些工具，给出一份详细的报告
```
**5. 电商版参考查询请求:**
```bash
制作一份荔枝产品电商行业市场洞察报告
```