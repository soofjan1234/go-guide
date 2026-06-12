import React, { useState } from "react";

const API_BASE = "http://127.0.0.1:8000";

/** 周一至周五：公司模式；周六、周日：家庭模式（按本机日历）。 */
function getAutoReviewMode() {
  const day = new Date().getDay();
  if (day === 0 || day === 6) {
    return "home";
  }
  return "company";
}

function AssistantStatus({ message, busy }) {
  return (
    <div
      className={`assistant-status${busy ? " assistant-status--busy" : ""}`}
      role="status"
      aria-live="polite"
      aria-busy={busy}
    >
      <span className="assistant-status-mark" aria-hidden />
      <div className="assistant-status-body">
        <div className="assistant-status-label">Loom · 会话</div>
        <div className="assistant-status-row">
          <p className="assistant-status-msg">{message}</p>
          {busy && (
            <span className="typing-dots" role="img" aria-label="处理中">
              <span className="typing-dot" />
              <span className="typing-dot" />
              <span className="typing-dot" />
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

const defaultResult = {
  ai_grade: "-",
  suggested_interval_days: "-",
  next_review_at: "-",
  reason: "等待提交...",
};

/** 题库搜索：不区分大小写；空格拆成多段且需同时命中；覆盖题目/答案/分类/id/来源路径。 */
function cardMatchesBankFilter(card, query, categoryFilter) {
  if (categoryFilter !== "全部") {
    if (String(card.category || "").toLowerCase() !== String(categoryFilter).toLowerCase()) {
      return false;
    }
  }
  const raw = String(query || "").trim();
  if (!raw) {
    return true;
  }
  const hay = [
    card.question,
    card.answer,
    card.category,
    card.id,
    card.source_path || "",
    card.next_review_at || "",
  ]
    .join("\n")
    .toLowerCase();
  const parts = raw
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean);
  return parts.every((p) => hay.includes(p));
}

export default function App() {
  const [activeTab, setActiveTab] = useState("review");
  const [cards, setCards] = useState([]);
  const [cardIndex, setCardIndex] = useState(0);
  const [reviewDrafts, setReviewDrafts] = useState({});
  const [pendingActions, setPendingActions] = useState({});
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(defaultResult);
  const [batchResults, setBatchResults] = useState([]);
  const [showResultDialog, setShowResultDialog] = useState(false);
  const [metaMessage, setMetaMessage] = useState("正在加载今日待复习...");
  const [sourceText, setSourceText] = useState("");
  const [processedPreview, setProcessedPreview] = useState("");
  const [candidates, setCandidates] = useState([]);
  const [candidateEdits, setCandidateEdits] = useState({});

  // 统计评估页状态（mvp4：基于落盘 Review 数据的简化弱项分析）
  const [statsCategory, setStatsCategory] = useState("全部");
  const [statsLimit, setStatsLimit] = useState(10);
  const [statsLoading, setStatsLoading] = useState(false);
  const [statsError, setStatsError] = useState("");
  const [statsResult, setStatsResult] = useState(null);

  /** 今日复习模式由星期自动决定，见 getAutoReviewMode */
  const [lastReviewMode, setLastReviewMode] = useState("home");

  // 题库页状态（与“今日复习”的 cards 变量分离，避免互相覆盖）
  const [allCards, setAllCards] = useState([]);
  const [cardQuery, setCardQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("全部");
  const [expandedAnswers, setExpandedAnswers] = useState({});
  const [editCardId, setEditCardId] = useState(null);
  const [editQuestion, setEditQuestion] = useState("");
  const [editAnswer, setEditAnswer] = useState("");
  const [editCategory, setEditCategory] = useState("其它");
  const [editNextReviewAt, setEditNextReviewAt] = useState("");

  const reviewMode = getAutoReviewMode();

  const currentCard = cards[cardIndex] ?? null;
  const currentDraft = currentCard
    ? reviewDrafts[currentCard.id] || { answer_text: "", user_grade: "B" }
    : { answer_text: "", user_grade: "B" };
  const isLastCard = cards.length > 0 && cardIndex === cards.length - 1;

  const loadTodayCards = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/cards/today`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      setCards(data);
      setCardIndex(0);
      setReviewDrafts((prev) => {
        const next = {};
        data.forEach((card) => {
          next[card.id] = prev[card.id] || { answer_text: "", user_grade: "B" };
        });
        return next;
      });
      setPendingActions((prev) => {
        const next = {};
        data.forEach((card) => {
          next[card.id] = prev[card.id] || "none";
        });
        return next;
      });
      setResult(defaultResult);
      setMetaMessage(data.length ? `今日待复习：${data.length} 题` : "今日没有待复习题目");
    } catch (error) {
      setMetaMessage(`加载失败：${error.message}`);
    }
  };

  const loadCandidates = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/candidates`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      setCandidates(data);
      setCandidateEdits((prev) => {
        const next = { ...prev };
        data.forEach((candidate) => {
          if (!next[candidate.candidate_id]) {
            next[candidate.candidate_id] = {
              question: candidate.question,
              answer: candidate.answer,
              category: candidate.category,
            };
          }
        });
        Object.keys(next).forEach((key) => {
          if (!data.find((item) => item.candidate_id === key)) {
            delete next[key];
          }
        });
        return next;
      });
    } catch {
      setCandidates([]);
      setCandidateEdits({});
    }
  };

  const loadAllCards = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/cards`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      setAllCards(data);
    } catch {
      setAllCards([]);
    }
  };

  React.useEffect(() => {
    loadTodayCards();
    loadCandidates();
    loadAllCards();
  }, []);

  const updateCurrentDraft = (field, value) => {
    if (!currentCard) {
      return;
    }
    setReviewDrafts((prev) => ({
      ...prev,
      [currentCard.id]: {
        ...(prev[currentCard.id] || { answer_text: "", user_grade: "B" }),
        [field]: value,
      },
    }));
  };

  const submitAllReviews = async () => {
    if (!cards.length) {
      setMetaMessage("当前没有可复习的题目。");
      return;
    }

    const missingCard =
      reviewMode === "home"
        ? cards.find((card) => {
            const action = pendingActions[card.id] || "none";
            const draft = reviewDrafts[card.id] || { answer_text: "" };
            if (action === "delete") {
              return false;
            }
            return !draft.answer_text?.trim();
          })
        : null;
    if (missingCard) {
      setMetaMessage("请先完成所有未删除题目的答案后再统一提交。");
      return;
    }

    setLoading(true);
    try {
      const items = cards.map((card) => {
        const action = pendingActions[card.id] || "none";
        const draft = reviewDrafts[card.id] || { answer_text: "", user_grade: "B" };
        let post_action = "none";
        if (action === "delete") {
          post_action = "delete";
        } else if (action === "snooze_15d") {
          post_action = "snooze_15d";
        }
        return {
          card_id: card.id,
          answer_text: draft.answer_text,
          user_grade: draft.user_grade,
          post_action,
        };
      });

      const batchResp = await fetch(`${API_BASE}/api/review/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: reviewMode, items }),
      });
      if (!batchResp.ok) {
        const errText = await batchResp.text().catch(() => "");
        throw new Error(errText || `HTTP ${batchResp.status}`);
      }
      const batchData = await batchResp.json();
      setLastReviewMode(reviewMode);
      const finalRows = (batchData.results || []).map((row) => ({
        card_id: row.card_id,
        question: row.question,
        ai_grade: row.ai_grade,
        next_review_at: row.next_review_at,
        final_status: row.final_status,
        user_answer: row.user_answer,
        reference_answer: row.reference_answer,
        ai_analysis: row.ai_analysis || "",
      }));
      setBatchResults(finalRows);
      setShowResultDialog(true);
      setResult({
        ai_grade: "-",
        suggested_interval_days: "-",
        next_review_at: "-",
        reason: "本轮题目已统一提交并处理完成。",
      });
      setMetaMessage("已完成统一评估并应用状态。");
      await loadTodayCards();
    } catch (error) {
      setMetaMessage(`统一提交失败：${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const prevCard = () => {
    if (!cards.length) {
      return;
    }
    setCardIndex((prev) => Math.max(prev - 1, 0));
  };

  const nextCard = () => {
    if (!cards.length) {
      return;
    }
    setCardIndex((prev) => Math.min(prev + 1, cards.length - 1));
  };

  const togglePendingAction = (action) => {
    if (!currentCard) {
      return;
    }
    setPendingActions((prev) => {
      const current = prev[currentCard.id] || "none";
      return {
        ...prev,
        [currentCard.id]: current === action ? "none" : action,
      };
    });
  };

  const CATEGORY_OPTIONS = [
    { value: "Go", label: "go" },
    { value: "MySQL", label: "mysql" },
    { value: "Redis", label: "redis" },
    { value: "网络", label: "网络" },
    { value: "项目", label: "项目" },
    { value: "其它", label: "其它" },
  ];

  const toggleExpandedAnswer = (cardId) => {
    setExpandedAnswers((prev) => ({
      ...prev,
      [cardId]: !prev[cardId],
    }));
  };

  const generateCandidates = async () => {
    if (!sourceText.trim()) {
      setMetaMessage("请先粘贴文本再解析。");
      return;
    }
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/candidates/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_text: sourceText }),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      setProcessedPreview(typeof data.processed_source === "string" ? data.processed_source : "");
      await loadCandidates();
      setMetaMessage("已按标题切分并清洗 Markdown，请在下方审查候选题。");
    } catch (error) {
      setMetaMessage(`解析失败：${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const removeCandidate = async (candidateId) => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/candidates/${candidateId}`, { method: "DELETE" });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      await loadCandidates();
      setMetaMessage("已从队列移除该候选。");
    } catch (error) {
      setMetaMessage(`删除失败：${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const addEmptyCandidate = async () => {
    setLoading(true);
    try {
      const category = candidates[0]?.category || "其它";
      const response = await fetch(`${API_BASE}/api/candidates`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category, question: "", answer: "" }),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      await loadCandidates();
      setMetaMessage("已增加一条空候选，可编辑后入库。");
    } catch (error) {
      setMetaMessage(`增加失败：${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const finishImportParse = () => {
    setSourceText("");
    setProcessedPreview("");
    setMetaMessage("已清空原文与处理结果（候选队列未变）。");
  };

  const reviewCandidate = async (candidate, action) => {
    setLoading(true);
    try {
      const edited = candidateEdits[candidate.candidate_id] || {
        question: candidate.question,
        answer: candidate.answer,
        category: candidate.category,
      };
      const response = await fetch(`${API_BASE}/api/candidates/${candidate.candidate_id}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action,
          question: edited.question,
          answer: edited.answer,
          category: edited.category ?? candidate.category,
        }),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      await loadCandidates();
      await loadTodayCards();
    } catch (error) {
      setMetaMessage(`审查失败：${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const updateCandidateField = (candidateId, field, value) => {
    setCandidateEdits((prev) => ({
      ...prev,
      [candidateId]: {
        ...(prev[candidateId] || {}),
        [field]: value,
      },
    }));
  };

  const deleteCard = async (cardId) => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/cards/${cardId}/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "delete" }),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      await loadAllCards();
      await loadTodayCards();
      if (editCardId === cardId) {
        setEditCardId(null);
      }
      setMetaMessage("已删除题目。");
    } catch (error) {
      setMetaMessage(`删除失败：${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const saveEditCard = async () => {
    if (!editCardId) {
      return;
    }
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/cards/${editCardId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: editQuestion,
          answer: editAnswer,
          category: editCategory,
          next_review_at: editNextReviewAt,
        }),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      await loadAllCards();
      await loadTodayCards();
      setEditCardId(null);
      setMetaMessage("已保存修改。");
    } catch (error) {
      setMetaMessage(`保存失败：${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const runStatsEvaluate = async () => {
    setStatsLoading(true);
    setStatsError("");
    try {
      const resp = await fetch(`${API_BASE}/api/stats/evaluate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category: statsCategory === "全部" ? "all" : statsCategory,
          limit: Number(statsLimit),
        }),
      });
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
      const data = await resp.json();
      setStatsResult(data);
    } catch (error) {
      setStatsError(`生成失败：${error.message}`);
      setStatsResult(null);
    } finally {
      setStatsLoading(false);
    }
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <h1>Loom Memory</h1>
        
        <nav>
          <button
            type="button"
            className={`nav-link ${activeTab === "review" ? "active" : ""}`}
            onClick={() => setActiveTab("review")}
          >
            今日复习
          </button>
          <button
            type="button"
            className={`nav-link ${activeTab === "cards" ? "active" : ""}`}
            onClick={() => setActiveTab("cards")}
          >
            题库
          </button>
          <button
            type="button"
            className={`nav-link ${activeTab === "import" ? "active" : ""}`}
            onClick={() => setActiveTab("import")}
          >
            导入
          </button>
          <button
            type="button"
            className={`nav-link ${activeTab === "stats" ? "active" : ""}`}
            onClick={() => setActiveTab("stats")}
          >
            统计
          </button>
        </nav>
      </aside>

      <main
        className={`content ${activeTab === "review" ? "review-content" : ""} ${activeTab === "import" ? "import-flow" : ""} ${activeTab === "cards" ? "cards-content" : ""}`}
      >
        {activeTab === "review" && (
          <>
            {!cards.length && (
              <section className="card empty-card">
                <h2>今日无复习题目</h2>
                <p className="meta">当前没有待复习内容，去导入页生成题目即可。</p>
                <AssistantStatus message={metaMessage} busy={loading} />
                {batchResults.length > 0 && (
                  <div className="actions">
                    <button type="button" onClick={() => setShowResultDialog(true)}>
                      查看上次评估结果
                    </button>
                  </div>
                )}
              </section>
            )}
            {cards.length > 0 && (
              <section className="card">
          <div className="review-mode-pill" role="status" aria-live="polite">
            <span className={`review-mode-badge review-mode-badge--${reviewMode}`}>
              {reviewMode === "company" ? "今日：公司模式（工作日）" : "今日：家庭模式（周末）"}
            </span>
          </div>
          <p className="meta review-mode-hint">
            {reviewMode === "company"
              ? "工作日默认：不写答案，心里想过后选择「记住 / 模糊 / 忘了」再提交；无 AI 评分，仅按自评排下次复习。"
              : "周末默认：写下答案，提交后由本地 AI 辅助评分与解析（若可用）。"}
          </p>
          <div className="card-header">
            <span className="tag">卡片 {cardIndex + 1} / {cards.length}</span>
            <div className="card-top-actions">
              <button
                type="button"
                className={(pendingActions[currentCard?.id] || "none") === "snooze_15d" ? "selected" : ""}
                onClick={() => togglePendingAction("snooze_15d")}
                disabled={!currentCard || loading}
              >
                延后 +15 天
              </button>
              <button
                type="button"
                className={(pendingActions[currentCard?.id] || "none") === "delete" ? "selected" : ""}
                onClick={() => togglePendingAction("delete")}
                disabled={!currentCard || loading}
              >
                删除
              </button>
            </div>
          </div>
          <p className="source">来源：{currentCard ? currentCard.source_path : "-"}</p>
          <h2>{currentCard ? currentCard.question : "暂无待复习题目"}</h2>
          <AssistantStatus message={metaMessage} busy={loading} />

          {reviewMode === "home" && (
            <textarea
              rows={8}
              placeholder="输入你的答案..."
              value={currentDraft.answer_text}
              onChange={(event) => updateCurrentDraft("answer_text", event.target.value)}
              disabled={!currentCard}
            />
          )}

          <div className="grade-row">
            <span>{reviewMode === "company" ? "自评（心里回忆后选择）：" : "你的自评："}</span>
            {["A", "B", "C"].map((grade) => (
              <button
                key={grade}
                className={`grade-btn ${currentDraft.user_grade === grade ? "selected" : ""}`}
                data-grade={grade}
                onClick={() => updateCurrentDraft("user_grade", grade)}
                type="button"
              >
                {grade === "A" && "A 记住"}
                {grade === "B" && "B 模糊"}
                {grade === "C" && "C 忘了"}
              </button>
            ))}
          </div>

          <div className="actions">
            {cardIndex > 0 && (
              <button type="button" onClick={prevCard} disabled={!currentCard || loading}>
                上一题
              </button>
            )}
            {!isLastCard && (
              <button type="button" onClick={nextCard} disabled={!currentCard || loading}>
                下一题
              </button>
            )}
            {isLastCard && (
              <button id="submitBtn" type="button" onClick={submitAllReviews} disabled={loading}>
                {loading ? (reviewMode === "company" ? "提交中…" : "评估中…") : reviewMode === "company" ? "提交" : "提交评估"}
              </button>
            )}
          </div>

          <p className="meta">
            当前状态：{
              (pendingActions[currentCard?.id] || "none") === "delete"
                ? "已标记删除（提交时生效）"
                : (pendingActions[currentCard?.id] || "none") === "snooze_15d"
                  ? "已标记延后15天（提交时生效）"
                  : "正常"
            }
          </p>
          {batchResults.length > 0 && (
            <div className="actions">
              <button type="button" onClick={() => setShowResultDialog(true)}>
                查看上次评估结果
              </button>
            </div>
          )}
        </section>
            )}
          </>
        )}

        {activeTab === "import" && (
          <div className="import-stack">
            <section className="card import-block">
              <p className="import-section-label">上 · 粘贴原文</p>
              <h2>导入</h2>
              <p className="meta">按 ## / ### 标题切分为「问题 + 答案」；程序去除 Markdown 符号（保留数字与 1. 列表形式）。分类仍由本地模型辅助判断（可失败则为「其它」）。</p>
              <div className="import-box">
                <textarea
                  rows={10}
                  placeholder="粘贴 Markdown / 纯文本，然后点击下方按钮解析"
                  value={sourceText}
                  onChange={(event) => setSourceText(event.target.value)}
                />
                <div className="actions">
                  <button type="button" className="btn-cta" onClick={generateCandidates} disabled={loading}>
                    {loading ? "解析中…" : "解析并生成候选"}
                  </button>
                </div>
              </div>
            </section>

            <section className="card import-block">
              <p className="import-section-label">中 · 程序化清洗结果（全篇）</p>
              <h2>处理结果</h2>
              <p className="meta">与入库题干一致的全文清洗预览；未解析前为空。</p>
              <textarea
                className="processed-preview"
                rows={10}
                readOnly
                placeholder="解析成功后在此展示已去除 ###、##、**、行首 - 等后的全文…"
                value={processedPreview}
              />
            </section>

            <section className="card import-block">
              <p className="import-section-label">下 · 候选题审查</p>
              <h2>候选题</h2>
              <p className="meta">可修改问题、答案与分类，删除队列或同意入库；列表末尾可手动增加空候选。</p>
              {candidates.length === 0 && <p className="reason">暂无待审查候选题</p>}
              {candidates.map((candidate) => (
                <div key={candidate.candidate_id} className="candidate-item">
                  <p className="meta">候选 ID：{candidate.candidate_id}</p>
                  <label className="field-label" htmlFor={`${candidate.candidate_id}-cat`}>
                    分类
                  </label>
                  <select
                    id={`${candidate.candidate_id}-cat`}
                    className="select-input candidate-category-select"
                    value={(candidateEdits[candidate.candidate_id] || {}).category ?? candidate.category}
                    onChange={(event) =>
                      updateCandidateField(candidate.candidate_id, "category", event.target.value)
                    }
                  >
                    {CATEGORY_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.value}
                      </option>
                    ))}
                  </select>
                  <label className="field-label" htmlFor={`${candidate.candidate_id}-q`}>
                    问题
                  </label>
                  <textarea
                    id={`${candidate.candidate_id}-q`}
                    rows={3}
                    value={(candidateEdits[candidate.candidate_id] || {}).question ?? candidate.question}
                    onChange={(event) =>
                      updateCandidateField(candidate.candidate_id, "question", event.target.value)
                    }
                  />
                  <label className="field-label" htmlFor={`${candidate.candidate_id}-a`}>
                    答案
                  </label>
                  <textarea
                    id={`${candidate.candidate_id}-a`}
                    rows={4}
                    value={(candidateEdits[candidate.candidate_id] || {}).answer ?? candidate.answer}
                    onChange={(event) =>
                      updateCandidateField(candidate.candidate_id, "answer", event.target.value)
                    }
                  />
                  <div className="actions">
                    <button
                      type="button"
                      className="btn-cta"
                      onClick={() => reviewCandidate(candidate, "approve")}
                      disabled={loading}
                    >
                      同意入库
                    </button>
                    <button
                      type="button"
                      className="danger-outline-btn"
                      onClick={() => removeCandidate(candidate.candidate_id)}
                      disabled={loading}
                    >
                      删除
                    </button>
                  </div>
                </div>
              ))}
              <div className="actions import-add-tail">
                <button type="button" onClick={addEmptyCandidate} disabled={loading}>
                  增加空候选
                </button>
                <button type="button" onClick={finishImportParse} disabled={loading}>
                  完成解析
                </button>
              </div>
            </section>
          </div>
        )}

        {activeTab === "cards" && (
          <section className="card cards-page">
            <h2>题库</h2>

            <div className="cards-toolbar">
                <input
                  type="text"
                  className="text-input"
                  placeholder="搜索：题目、答案、分类、下次复习日期…"
                  value={cardQuery}
                  onChange={(e) => setCardQuery(e.target.value)}
                />
                <select
                  className="select-input"
                  value={categoryFilter}
                  onChange={(e) => setCategoryFilter(e.target.value)}
                >
                  <option value="全部">全部</option>
                  {CATEGORY_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="cards-list">
                {allCards.length === 0 && <p className="reason">题库为空：先到“导入”生成题目。</p>}
                {allCards.length > 0 &&
                  allCards
                    .filter((card) => cardMatchesBankFilter(card, cardQuery, categoryFilter))
                    .sort((a, b) => (a.next_review_at || "").localeCompare(b.next_review_at || ""))
                    .map((card) => (
                      <div key={card.id} className="cards-item">
                        <div className="cards-item-main">
                          <div className="cards-item-title">{card.question}</div>
                          {(() => {
                            const answerText = card.answer || "";
                            const expanded = !!expandedAnswers[card.id];
                            const preview = answerText.length > 120 ? `${answerText.slice(0, 120)}...` : answerText;
                            return (
                              <div className={`cards-item-answer ${expanded ? "expanded" : "collapsed"}`}>
                                {expanded ? answerText : preview}
                              </div>
                            );
                          })()}
                          <div className="cards-item-meta">
                            分类：{card.category} / 下次复习：{card.next_review_at}
                          </div>
                        </div>
                        <div className="cards-item-actions">
                          <button
                            type="button"
                            onClick={() => toggleExpandedAnswer(card.id)}
                            className="answer-toggle-btn"
                          >
                            {expandedAnswers[card.id] ? "收起答案" : "展开答案"}
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setEditCardId(card.id);
                              setEditQuestion(card.question);
                              setEditAnswer(card.answer);
                              setEditCategory(card.category || "其它");
                              setEditNextReviewAt(card.next_review_at || "");
                            }}
                          >
                            编辑
                          </button>
                          <button type="button" onClick={() => deleteCard(card.id)} className="danger-btn">
                            删除
                          </button>
                        </div>
                      </div>
                    ))}
            </div>
          </section>
        )}

        {activeTab === "stats" && (
          <>
            <section className="card">
              <h2>统计评估</h2>
              <p className="meta">基于落盘 Review 数据生成简化弱项改进建议（不提供历史回看）。</p>
            </section>
            <section className="panel">
              <h3>生成</h3>
              <p className="reason">会选择最近 N 条“带 AI 解析”的评估记录，并输出本次统计结果。</p>
              <div className="cards-toolbar">
                <select className="select-input" value={statsCategory} onChange={(e) => setStatsCategory(e.target.value)}>
                  <option value="全部">全部</option>
                  {CATEGORY_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.value}
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  className="text-input"
                  value={statsLimit}
                  min={1}
                  max={30}
                  onChange={(e) => setStatsLimit(e.target.value)}
                />
              </div>
              <div className="actions">
                <button type="button" className="btn-cta" onClick={runStatsEvaluate} disabled={statsLoading}>
                  {statsLoading ? "生成中…" : "生成统计评估"}
                </button>
              </div>
              {statsError && <p className="reason">{statsError}</p>}
            </section>

            {statsResult && (
              <>
                <section className="panel">
                  <h3>AI 总结</h3>
                  <p className="reason">{statsResult.ai_summary || "暂无总结。"}</p>
                </section>

                <section className="panel">
                  <h3>评估明细（本次生成所选）</h3>
                  {statsResult.items?.length ? (
                    statsResult.items.map((item) => (
                      <div key={item.card_id} className="candidate-item">
                        <p>
                          <strong>题目：</strong>
                          {item.question}
                        </p>
                        <p>
                          <strong>最终状态：</strong>
                          {item.final_status}
                        </p>
                        <p>
                          <strong>你的答案：</strong>
                          {item.user_answer || "-"}
                        </p>
                        <p>
                          <strong>AI解析：</strong>
                          {item.ai_analysis || "暂无解析"}
                        </p>
                      </div>
                    ))
                  ) : (
                    <p className="reason">暂无可用记录。</p>
                  )}
                </section>
              </>
            )}
          </>
        )}
      </main>
      {activeTab === "cards" && editCardId && (
        <div
          className="dialog-mask"
          role="presentation"
          onClick={() => {
            if (!loading) {
              setEditCardId(null);
            }
          }}
        >
          <div
            className="dialog-card dialog-card--edit"
            role="dialog"
            aria-modal="true"
            aria-labelledby="card-edit-dialog-title"
            onClick={(event) => event.stopPropagation()}
          >
            <h3 id="card-edit-dialog-title">编辑题目</h3>
            <p className="meta dialog-edit-meta">ID：{editCardId}</p>
            <label className="field-label">问题</label>
            <textarea rows={4} value={editQuestion} onChange={(e) => setEditQuestion(e.target.value)} />
            <label className="field-label">答案</label>
            <textarea rows={6} value={editAnswer} onChange={(e) => setEditAnswer(e.target.value)} />
            <label className="field-label">分类</label>
            <select className="select-input" value={editCategory} onChange={(e) => setEditCategory(e.target.value)}>
              {CATEGORY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <label className="field-label">下次复习日期</label>
            <input
              type="text"
              className="text-input"
              placeholder="任意字符串；排期用 YYYY-MM-DD（可带后缀说明）"
              value={editNextReviewAt}
              onChange={(e) => setEditNextReviewAt(e.target.value)}
            />
            <div className="actions dialog-edit-actions">
              <button type="button" className="btn-cta" onClick={() => saveEditCard()} disabled={loading}>
                {loading ? "保存中…" : "保存"}
              </button>
              <button type="button" onClick={() => !loading && setEditCardId(null)} disabled={loading}>
                取消
              </button>
            </div>
          </div>
        </div>
      )}
      {showResultDialog && (
        <div className="dialog-mask" onClick={() => setShowResultDialog(false)}>
          <div className="dialog-card" onClick={(event) => event.stopPropagation()}>
            <h3>本轮评估结果</h3>
            <p className="reason">
              {lastReviewMode === "company"
                ? `共 ${batchResults.length} 题。公司模式：无 AI 评分与作答记录，复习间隔仅按自评（记住/模糊/忘了）与既有矩阵计算。状态说明同下。`
                : `共 ${batchResults.length} 题。状态说明：「正常」表示按评估间隔复习，「延后15天」表示提交时已延后，「已删除」表示提交时已移出复习列表。`}
            </p>
            {batchResults.length === 0 && <p className="reason">暂无可展示的评估记录。</p>}
            {batchResults.map((row) => (
              <div key={row.card_id} className="candidate-item">
                <p>
                  <strong>题目：</strong>
                  {row.question}
                </p>
                <p>
                  <strong>{lastReviewMode === "company" ? "自评（调度等价）" : "AI评分"}：</strong>
                  {lastReviewMode === "company" ? `${row.ai_grade}（与自评一致，无 AI）` : row.ai_grade}
                </p>
                <p>
                  <strong>下次复习：</strong>
                  {row.next_review_at}
                </p>
                <p>
                  <strong>最终状态：</strong>
                  {row.final_status}
                </p>
                <p>
                  <strong>你的答案：</strong>
                  {lastReviewMode === "company" && !(row.user_answer && String(row.user_answer).trim() && row.user_answer !== "-")
                    ? "（公司模式未记录打字）"
                    : row.user_answer}
                </p>
                <p>
                  <strong>参考答案：</strong>
                  {row.reference_answer}
                </p>
                <p>
                  <strong>{lastReviewMode === "company" ? "说明" : "AI解析"}：</strong>
                  {row.ai_analysis || "暂无解析"}
                </p>
              </div>
            ))}
            <div className="actions">
              <button type="button" onClick={() => setShowResultDialog(false)}>
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
