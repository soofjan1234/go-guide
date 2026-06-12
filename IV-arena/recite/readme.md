# Loom Memory MVP（Light UI）

## 1. 项目结构
- `backend/`：Python FastAPI 接口
- `frontend/`：React + Vite 浅色风格页面

## 2. 启动后端
在 `IV-arena/recite/backend` 目录执行：

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

默认地址：`http://127.0.0.1:8000`

## 3. 启动前端（React）
在 `IV-arena/recite/frontend` 目录执行：

```bash
npm install
npm run dev
```

默认地址：`http://127.0.0.1:5173`

## 4. 当前能力
- 今日待复习列表（多题）
- 用户 A/B/C 自评
- 调用后端评分接口，返回 AI 评分和下一次复习日期
- 题目管理动作：延后 +15 天 / 删除
- 粘贴文本后优先通过 Ollama 提示词智能分题（失败回退规则生成）
- 候选题支持先修改问题/答案，再执行同意入库/拒绝
- 评分优先调用本地 Ollama `llama3.2:3b`，失败时回退为本地规则评分

## 5. 下一步建议
- 接入 Ollama：`llama3.2:3b`
- 题库持久化（SQLite）
- 今日待复习列表与调度队列
