chcp 65001
cd backend
:: python -m eval.run_eval --mode all --judge-model deepseek-v4-pro --output results.json
python -m eval.run_eval --mode comp --judge-model deepseek-v4-pro --topic "规范驱动开发SDD与AGENTS.md的关系"