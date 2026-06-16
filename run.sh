# 改成自己的内容
export APP_TOKEN="你的LLM API Key"
export LLM_BASE_URL="你的LLM服务URL"
export MCP_APP_ID="你的MCP工具ID"
export LANGSMITH_API_KEY="Langsmith api key"
cd backend
pip install .

# python test.py
cd ..
cd frontend
npm install
cd ..
make dev