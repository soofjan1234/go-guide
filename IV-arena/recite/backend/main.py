import json
import os
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from urllib import error, request


app = FastAPI(title="Loom Memory API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_load_storage() -> None:
    load_storage()

Grade = Literal["A", "B", "C"]
ReviewMode = Literal["home", "company"]
Category = Literal["Go", "MySQL", "Redis", "网络", "项目", "其它"]
CardStatus = Literal["active", "deleted"]
CardAction = Literal["snooze_15d", "delete"]
CandidateStatus = Literal["pending", "approved", "rejected"]

FIXED_RULES: dict[tuple[Grade, Grade], int] = {
    ("A", "A"): 7,
    ("A", "B"): 4,
    ("B", "A"): 4,
    ("B", "B"): 3,
    ("C", "B"): 2,
    ("C", "C"): 1,
}

COMPANY_REVIEW_NOTE = "公司模式：未记录书面作答；复习间隔仅按自评（记住/模糊/忘了）与调度矩阵计算，无 AI 评分。"


class ReviewRequest(BaseModel):
    card_id: str
    answer_text: str = ""
    user_grade: Grade
    mode: ReviewMode = "home"


class ReviewResponse(BaseModel):
    card_id: str
    ai_grade: Grade
    suggested_interval_days: int
    next_review_at: str
    reason: str
    ai_analysis: str


class BatchReviewItem(BaseModel):
    card_id: str
    answer_text: str = ""
    user_grade: Grade = "B"
    # After AI review: none=keep schedule from matrix, snooze_15d, delete (handled before scoring).
    post_action: Literal["none", "snooze_15d", "delete"] = "none"


class BatchReviewRequest(BaseModel):
    mode: ReviewMode = "home"
    items: list[BatchReviewItem]


class BatchReviewResultRow(BaseModel):
    card_id: str
    question: str
    ai_grade: str
    next_review_at: str
    final_status: str
    user_answer: str
    reference_answer: str
    ai_analysis: str = ""


class BatchReviewResponse(BaseModel):
    results: list[BatchReviewResultRow]


class StatsEvaluateRequest(BaseModel):
    # "all" means across all categories.
    category: Category | Literal["all"] = "all"
    # Optional: evaluate a specific subset by card_id.
    card_ids: list[str] | None = None
    # How many latest usable review records to include.
    limit: int = 10


class StatsItem(BaseModel):
    card_id: str
    category: Category
    question: str
    user_answer: str
    reference_answer: str
    final_status: str
    ai_analysis: str


class StatsEvaluateResponse(BaseModel):
    items: list[StatsItem]
    ai_summary: str


class Card(BaseModel):
    id: str
    question: str
    answer: str
    category: Category = "其它"
    # Historical/seeded data may omit these fields; keep sensible defaults so /api/cards is never empty.
    source_path: str = ""
    source_type: str = ""
    status: CardStatus = "active"
    next_review_at: str = Field(default_factory=lambda: str(date.today()))
    review_count: int = 0
    last_ai_grade: Grade | None = None
    last_user_grade: Grade | None = None


class CardActionRequest(BaseModel):
    action: CardAction


class CardActionResponse(BaseModel):
    card_id: str
    status: CardStatus
    next_review_at: str
    action: CardAction


class CardUpdateRequest(BaseModel):
    question: str | None = None
    answer: str | None = None
    category: Category | None = None
    next_review_at: str | None = None


class CandidateCard(BaseModel):
    candidate_id: str
    question: str
    answer: str
    category: Category
    source_text_ref: str
    review_status: CandidateStatus


class GenerateCandidatesRequest(BaseModel):
    source_text: str


class GenerateCandidatesResponse(BaseModel):
    candidates: list[CandidateCard]
    # Full source after mvp4.2 markdown cleanup (for import page middle panel).
    processed_source: str = ""


class CreateCandidateRequest(BaseModel):
    """Manual add on import page; category defaults to 其它 if omitted."""

    category: Category | None = None
    question: str = ""
    answer: str = ""


class CandidateDecisionRequest(BaseModel):
    action: Literal["approve", "reject"]
    question: str | None = None
    answer: str | None = None
    category: Category | None = None


class ReviewLog(BaseModel):
    card_id: str
    category: Category = "其它"
    question: str
    answer_text: str
    reference_answer: str = ""
    ai_grade: Grade
    user_grade: Grade
    suggested_interval_days: int
    next_review_at: str
    final_status: str
    reviewed_at: str
    ai_analysis: str = ""
    review_mode: ReviewMode = "home"


CARDS: dict[str, Card] = {
    "card-1": Card(
        id="card-1",
        question="TCP 三次握手分别做了什么，为什么不能只两次？",
        answer="建立可靠连接并同步初始序列号，避免历史连接干扰。",
        category="网络",
        source_path="Article/网络/4.1-网络层IP、ARP、ICMP.md",
        source_type="file",
        status="active",
        next_review_at=str(date.today()),
        review_count=0,
    ),
    "card-2": Card(
        id="card-2",
        question="HTTP 和 HTTPS 的主要区别是什么？",
        answer="HTTPS 在 HTTP 上增加 TLS 加密、身份校验与完整性保护。",
        category="网络",
        source_path="Article/网络/1-分层对照与协议一览.md",
        source_type="file",
        status="active",
        next_review_at=str(date.today()),
        review_count=0,
    ),
}

CANDIDATES: dict[str, CandidateCard] = {}
REVIEW_LOGS: list[ReviewLog] = []
DATA_BASE_DIR = Path(__file__).resolve().parent / "data"
QUESTION_DIR = DATA_BASE_DIR / "question"
REVIEW_DIR = DATA_BASE_DIR / "review"
REVIEW_LOGS_FILE = REVIEW_DIR / "review_logs.json"

# Legacy: older versions persisted network cards here.
LEGACY_DATA_DIR = DATA_BASE_DIR / "网络"
LEGACY_CARDS_FILE = LEGACY_DATA_DIR / "cards.json"

ALL_CATEGORIES: list[Category] = ["Go", "MySQL", "Redis", "网络", "项目", "其它"]


def next_numeric_suffix_id(prefix: str, keys: dict[str, object]) -> str:
    """Next ``{prefix}{n}`` where n is max existing numeric suffix + 1.

    Using ``len(keys) + 1`` is unsafe when keys are not a contiguous 1..N range
    (e.g. after rejects or reload), which led to duplicate ids and 404 on decision.
    """
    max_n = 0
    lp = len(prefix)
    for k in keys:
        if not k.startswith(prefix):
            continue
        tail = k[lp:]
        if tail.isdigit():
            max_n = max(max_n, int(tail))
    return f"{prefix}{max_n + 1}"


def cards_path_for_category(category: Category) -> Path:
    return QUESTION_DIR / f"cards-{category}.json"


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_storage() -> None:
    QUESTION_DIR.mkdir(parents=True, exist_ok=True)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)

    # Write cards into category-separated files.
    for category in ALL_CATEGORIES:
        cards_for_category = [card.model_dump() for card in CARDS.values() if card.category == category]
        cards_for_category.sort(key=lambda item: str(item.get("id", "")))
        write_json(cards_path_for_category(category), {"cards": cards_for_category})

    # Write review logs to a single file (stats reads from here).
    write_json(REVIEW_LOGS_FILE, {"review_logs": [log.model_dump() for log in REVIEW_LOGS]})


def load_storage() -> None:
    loaded_any_cards = False
    loaded_cards: dict[str, Card] = {}

    # Load from: data/question/cards-*.json
    if QUESTION_DIR.exists():
        for path in QUESTION_DIR.glob("cards-*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                cards = payload.get("cards", []) if isinstance(payload, dict) else []
                if not isinstance(cards, list):
                    continue
                for item in cards:
                    try:
                        card = Card(**item)
                    except Exception:
                        continue
                    loaded_cards[card.id] = card
                loaded_any_cards = loaded_any_cards or bool(loaded_cards)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

    # Legacy migration: data/网络/cards.json -> data/question/cards-网络.json
    if not loaded_any_cards and LEGACY_CARDS_FILE.exists():
        try:
            payload = json.loads(LEGACY_CARDS_FILE.read_text(encoding="utf-8"))
            legacy_cards = payload.get("cards", []) if isinstance(payload, dict) else []
            if isinstance(legacy_cards, list):
                for item in legacy_cards:
                    try:
                        card = Card(**item)
                    except Exception:
                        continue
                    if not getattr(card, "category", None):
                        card.category = "网络"  # type: ignore[assignment]
                    loaded_cards[card.id] = card

                loaded_any_cards = bool(loaded_cards)
        except (json.JSONDecodeError, TypeError, ValueError):
            loaded_any_cards = False

        if loaded_any_cards:
            # Persist migration result for consistency.
            QUESTION_DIR.mkdir(parents=True, exist_ok=True)
            for category in ALL_CATEGORIES:
                cards_for_category = [card.model_dump() for card in loaded_cards.values() if card.category == category]
                cards_for_category.sort(key=lambda item: str(item.get("id", "")))
                write_json(cards_path_for_category(category), {"cards": cards_for_category})

    if loaded_any_cards:
        CARDS.clear()
        CARDS.update(loaded_cards)

    # Load review logs from: data/review/review_logs.json
    if not REVIEW_LOGS_FILE.exists():
        return

    try:
        payload = json.loads(REVIEW_LOGS_FILE.read_text(encoding="utf-8"))
        review_logs = payload.get("review_logs", []) if isinstance(payload, dict) else []
        if not isinstance(review_logs, list):
            return

        parsed: list[ReviewLog] = []
        for item in review_logs:
            try:
                parsed.append(ReviewLog(**item))
            except Exception:
                continue
        if parsed:
            REVIEW_LOGS.clear()
            REVIEW_LOGS.extend(parsed)
    except (json.JSONDecodeError, TypeError, ValueError):
        return


def simple_ai_grade(answer_text: str) -> Grade:
    text = answer_text.strip()
    if len(text) >= 80:
        return "A"
    if len(text) >= 30:
        return "B"
    return "C"


def try_ollama_grade(question: str, answer_text: str) -> Grade | None:
    """Try local Ollama first; return None if unavailable."""
    ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
    payload = {
        "model": "llama3.2:3b",
        "stream": False,
        "prompt": (
            "你是面试卡片题的严格阅卷人。\n"
            "根据题目与用户答案，只输出一个大写字母：A、B、C 三者之一。\n"
            "A=大体正确且较完整，B=核心方向对但缺关键细节，C=错误或过于含糊。\n\n"
            f"题目：{question}\n"
            f"用户答案：{answer_text}\n\n"
            "只输出一个字母，不要输出其他任何文字。"
        ),
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        ollama_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8")
            body = json.loads(raw)
            letter = str(body.get("response", "")).strip().upper()[:1]
            if letter in {"A", "B", "C"}:
                return letter  # type: ignore[return-value]
    except (error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    return None


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


def try_ollama_batch_review(
    entries: list[tuple[str, str, str, str, Grade]],
) -> dict[str, tuple[Grade, str]] | None:
    """One Ollama call for many cards. Each tuple: card_id, question, reference_answer, user_answer, user_grade.

    Returns None on transport/parse failure; caller should fall back per card.
    """
    if not entries:
        return {}

    ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
    blocks: list[str] = []
    for cid, q, ref, ua, ug in entries:
        blocks.append(
            json.dumps(
                {
                    "card_id": cid,
                    "question": q,
                    "reference_answer": ref,
                    "user_answer": ua,
                    "user_self_grade": ug,
                },
                ensure_ascii=False,
            )
        )

    joined = "\n".join(blocks)
    payload = {
        "model": "llama3.2:3b",
        "stream": False,
        "prompt": (
            "你是面试卡片题的严格阅卷人。下面每行是一个 JSON 对象，描述一道题与用户的作答。\n"
            "请对每一道题给出：\n"
            "1）ai_grade：只取 A、B、C 之一（A=大体正确且较完整，B=核心方向对但缺关键细节，C=错误或过于含糊）。\n"
            "2）ai_analysis：中文 2～3 句简练话（答对部分、缺失或错误、一条可执行改进建议），不要用 Markdown。\n\n"
            "你必须只输出一个 JSON 数组，元素形状为 "
            '[{"card_id":"...","ai_grade":"A","ai_analysis":"..."},...]，'
            "数组顺序与输入题目顺序一致，card_id 必须与输入一致，不要输出数组以外的任何文字。\n\n"
            f"题目列表（每行一个 JSON）：\n{joined}\n"
        ),
    }
    data = json.dumps(payload).encode("utf-8")
    timeout = min(180, max(25, 20 + 14 * len(entries)))
    req = request.Request(
        ollama_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            body = json.loads(raw)
            content = str(body.get("response", "")).strip()
            if not content:
                return None
            parsed = json.loads(_strip_json_fence(content))
            if not isinstance(parsed, list):
                return None
            out: dict[str, tuple[Grade, str]] = {}
            for row in parsed:
                if not isinstance(row, dict):
                    continue
                cid = str(row.get("card_id", "")).strip()
                g = str(row.get("ai_grade", "")).strip().upper()[:1]
                analysis = str(row.get("ai_analysis", "")).strip()
                if cid and g in {"A", "B", "C"} and analysis:
                    out[cid] = (g, analysis)  # type: ignore[assignment]
            return out if out else None
    except (error.URLError, TimeoutError, json.JSONDecodeError, TypeError, ValueError):
        return None


def try_ollama_analysis(question: str, reference_answer: str, user_answer: str) -> str | None:
    ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
    payload = {
        "model": "llama3.2:3b",
        "stream": False,
        "prompt": (
            "你是严格的学习教练。将用户答案与参考答案对照。\n"
            "用中文写 2～3 句简练话：1）答对或到位的部分 2）缺失或错误 3）一条可执行的改进建议。\n"
            "不要使用 Markdown。\n\n"
            f"题目：{question}\n"
            f"参考答案：{reference_answer}\n"
            f"用户答案：{user_answer}\n"
        ),
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        ollama_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8")
            body = json.loads(raw)
            text = str(body.get("response", "")).strip()
            return text or None
    except (error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def fallback_analysis(reference_answer: str, user_answer: str) -> str:
    if len(user_answer.strip()) < 20:
        return "你的回答过短，核心信息不完整。建议先覆盖参考答案中的关键结论，再补充原因或细节。"
    return (
        "你的回答覆盖了部分核心点，但与参考答案相比仍有细节缺失。"
        "建议按“结论 -> 关键机制 -> 影响”三步组织答案。"
    )


def try_ollama_stats_summary(items: list[ReviewLog]) -> str | None:
    """Generate a simplified weakness + improvement summary for a batch of records."""
    if not items:
        return None

    ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")

    # Keep prompt size bounded.
    sample = items[:8]
    lines: list[str] = []
    for idx, item in enumerate(sample, start=1):
        lines.append(
            f"[{idx}] 题目：{item.question}\n"
            f"用户答案：{item.answer_text}\n"
            f"参考答案：{item.reference_answer}\n"
            f"AI 解析：{item.ai_analysis}\n"
            f"最终状态：{item.final_status}\n"
        )

    payload = {
        "model": "llama3.2:3b",
        "stream": False,
        "prompt": (
            "你是面试卡片场景的严格学习教练。\n"
            "下面是同一学习者的多条复习记录。请完成：\n"
            "1）归纳其共性弱项（2～4 条）。\n"
            "2）对每条弱项说明复习时要关注什么。\n"
            "3）给出下一轮复习可执行的具体改进计划。\n\n"
            "请用中文、纯文本输出，不要使用 Markdown。\n"
            "若信息不足，请明确说明。\n\n"
            + "\n".join(lines)
        ),
    }

    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        ollama_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=18) as resp:
            raw = resp.read().decode("utf-8")
            body = json.loads(raw)
            text = str(body.get("response", "")).strip()
            return text or None
    except (error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def fallback_stats_summary(items: list[ReviewLog]) -> str:
    if not items:
        return "暂无可用的统计评估记录。"

    # Very simple heuristic fallback: pull the "建议..." part if present.
    suggestions: list[str] = []
    for item in items:
        text = item.ai_analysis or ""
        if "建议" in text:
            # Try to extract up to the first sentence containing "建议".
            parts = text.split("建议", 1)
            if len(parts) == 2:
                suggestions.append("建议" + parts[1].strip())

    if suggestions:
        # Deduplicate while keeping order.
        seen: set[str] = set()
        uniq: list[str] = []
        for s in suggestions:
            if s not in seen:
                seen.add(s)
                uniq.append(s)
        return f"共性弱项/改进建议（简化版）：{'; '.join(uniq[:4])}"

    return "当前记录中缺少足够的 AI 解析文本，建议先完成多次 review 以获得更可靠的弱项定位。"


def _coerce_card_due(value: str) -> date:
    """Parse ``next_review_at`` for scheduling: full ISO date, or first 10 chars ``YYYY-MM-DD``; else due today."""
    s = (value or "").strip()
    if not s:
        return date.today()
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass
    if len(s) >= 10:
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            pass
    return date.today()


def strip_markdown_import(text: str) -> str:
    """mvp4.2: strip ###/##/**/`*`/```/line-leading `-` ; keep digits and `1.` style lists."""
    if not text or not text.strip():
        return ""
    out_lines: list[str] = []
    in_fence = False
    for raw in text.splitlines():
        s = raw.rstrip()
        t = s.strip()
        if t.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            out_lines.append(s)
            continue
        s = re.sub(r"^\s*#{1,6}\s+", "", s)
        if re.match(r"^\s*-\s+", s):
            s = re.sub(r"^\s*-\s+", "", s)
        out_lines.append(s)
    body = "\n".join(out_lines)
    body = re.sub(r"\*\*([^*]+)\*\*", r"\1", body)
    body = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", body)
    body = re.sub(r"`([^`]+)`", r"\1", body)
    body = body.replace("```", "")
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def parse_source_into_qa_items(source_text: str, max_cards: int = 8) -> list[dict[str, str]]:
    """Split on ##/### headings; question = heading text, answer = following body (mvp4.2, no LLM)."""
    text = source_text.strip()
    if not text:
        return []
    parts = [p.strip() for p in re.split(r"\n(?=#{1,6}\s+)", text) if p.strip()]
    pairs: list[tuple[str, str]] = []
    for part in parts:
        lines = part.split("\n", 1)
        head = lines[0].strip()
        tail = lines[1].strip() if len(lines) > 1 else ""
        if re.match(r"^#{1,6}\s", head):
            q_raw = re.sub(r"^#{1,6}\s+", "", head)
            pairs.append((q_raw, tail))
        else:
            if not pairs:
                q_raw = head
                ans = tail if tail else part
                pairs.append((q_raw, ans.strip()))
            else:
                pq, pa = pairs[-1]
                merged = f"{pa}\n{part}".strip() if pa else part
                pairs[-1] = (pq, merged)
    items: list[dict[str, str]] = []
    for q_raw, a_raw in pairs[:max_cards]:
        q = strip_markdown_import(q_raw).strip()
        a = strip_markdown_import(a_raw).strip()
        if not q:
            continue
        if not a:
            a = q
        if len(q) < 2:
            continue
        items.append({"question": q, "answer": a})
    return items


def clear_pending_candidates() -> None:
    for cid, c in list(CANDIDATES.items()):
        if c.review_status == "pending":
            del CANDIDATES[cid]


@app.get("/api/cards/today", response_model=list[Card])
def get_today_cards() -> list[Card]:
    # Ensure we always reflect latest on-disk storage.
    load_storage()
    today = date.today()
    cards = []
    for card in CARDS.values():
        due = _coerce_card_due(card.next_review_at)
        if card.status == "active" and due <= today:
            cards.append(card)
    return sorted(cards, key=lambda item: item.id)


@app.get("/api/cards", response_model=list[Card])
def list_cards() -> list[Card]:
    # Ensure we always reflect latest on-disk storage.
    load_storage()
    return sorted(CARDS.values(), key=lambda item: item.id)


@app.patch("/api/cards/{card_id}", response_model=Card)
def update_card(card_id: str, payload: CardUpdateRequest) -> Card:
    card = CARDS.get(card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found.")
    if payload.question is not None:
        card.question = payload.question
    if payload.answer is not None:
        card.answer = payload.answer
    if payload.category is not None:
        card.category = payload.category
    if payload.next_review_at is not None:
        s = payload.next_review_at.strip()
        if not s:
            raise HTTPException(status_code=400, detail="next_review_at cannot be empty.")
        card.next_review_at = s
    save_storage()
    return card


@app.post("/api/candidates/generate", response_model=GenerateCandidatesResponse)
def generate_candidates(payload: GenerateCandidatesRequest) -> GenerateCandidatesResponse:
    source = payload.source_text.strip()
    if not source:
        raise HTTPException(status_code=400, detail="source_text is required.")

    processed_source = strip_markdown_import(source)
    clear_pending_candidates()
    qa_items = parse_source_into_qa_items(source, max_cards=8)
    if not qa_items:
        raise HTTPException(status_code=400, detail="No usable text blocks found.")
    print(f"[candidates] card_count={len(qa_items)} (category fixed to 其它)")
    created: list[CandidateCard] = []
    for index, item in enumerate(qa_items, start=1):
        candidate_id = next_numeric_suffix_id("cand-", CANDIDATES)
        candidate = CandidateCard(
            candidate_id=candidate_id,
            question=item["question"],
            answer=item["answer"],
            source_text_ref=f"parse-{index}",
            category="其它",
            review_status="pending",
        )
        CANDIDATES[candidate_id] = candidate
        created.append(candidate)
    save_storage()
    return GenerateCandidatesResponse(candidates=created, processed_source=processed_source)


def _candidate_sort_key(item: CandidateCard) -> tuple[int, str]:
    cid = item.candidate_id
    if cid.startswith("cand-") and cid.removeprefix("cand-").isdigit():
        return (int(cid.removeprefix("cand-")), cid)
    return (10**12, cid)


@app.get("/api/candidates", response_model=list[CandidateCard])
def list_candidates() -> list[CandidateCard]:
    pending = [item for item in CANDIDATES.values() if item.review_status == "pending"]
    return sorted(pending, key=_candidate_sort_key)


@app.post("/api/candidates", response_model=CandidateCard)
def create_candidate(payload: CreateCandidateRequest) -> CandidateCard:
    category = payload.category or "其它"
    candidate_id = next_numeric_suffix_id("cand-", CANDIDATES)
    candidate = CandidateCard(
        candidate_id=candidate_id,
        question=(payload.question or "").strip(),
        answer=(payload.answer or "").strip(),
        source_text_ref="manual-add",
        category=category,
        review_status="pending",
    )
    CANDIDATES[candidate_id] = candidate
    save_storage()
    return candidate


@app.delete("/api/candidates/{candidate_id}")
def delete_candidate(candidate_id: str) -> dict[str, str]:
    candidate = CANDIDATES.get(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    if candidate.review_status != "pending":
        raise HTTPException(status_code=400, detail="Only pending candidates can be removed.")
    del CANDIDATES[candidate_id]
    save_storage()
    return {"ok": "true", "candidate_id": candidate_id}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/review", response_model=ReviewResponse)
def review(payload: ReviewRequest) -> ReviewResponse:
    card = CARDS.get(payload.card_id)
    if not card or card.status != "active":
        raise HTTPException(status_code=404, detail="Card not found or not active.")

    company = payload.mode == "company"
    if company:
        ai_grade = payload.user_grade
        interval = FIXED_RULES.get((ai_grade, payload.user_grade), 2)
        reason = f"公司模式：自评={payload.user_grade}，间隔 {interval} 天（无 AI）。"
        ai_analysis = COMPANY_REVIEW_NOTE
    else:
        if not (payload.answer_text or "").strip():
            raise HTTPException(status_code=400, detail="answer_text is required in home mode.")
        ai_grade = try_ollama_grade(card.question, payload.answer_text) or simple_ai_grade(
            payload.answer_text
        )
        interval = FIXED_RULES.get((ai_grade, payload.user_grade), 2)
        reason = (
            f"AI={ai_grade}, User={payload.user_grade}, "
            f"scheduled {interval} day(s)."
        )
        ai_analysis = try_ollama_analysis(card.question, card.answer, payload.answer_text) or fallback_analysis(
            card.answer, payload.answer_text
        )
    next_review_at = str(date.today() + timedelta(days=interval))
    card.next_review_at = next_review_at
    card.review_count += 1
    card.last_ai_grade = ai_grade
    card.last_user_grade = payload.user_grade
    REVIEW_LOGS.append(
        ReviewLog(
            card_id=card.id,
            category=card.category,
            question=card.question,
            answer_text=payload.answer_text,
            reference_answer=card.answer,
            ai_grade=ai_grade,
            user_grade=payload.user_grade,
            suggested_interval_days=interval,
            next_review_at=next_review_at,
            final_status="normal",
            reviewed_at=f"{date.today()}",
            ai_analysis=ai_analysis,
            review_mode=payload.mode,
        )
    )
    save_storage()
    return ReviewResponse(
        card_id=card.id,
        ai_grade=ai_grade,
        suggested_interval_days=interval,
        next_review_at=next_review_at,
        reason=reason,
        ai_analysis=ai_analysis,
    )


@app.post("/api/review/batch", response_model=BatchReviewResponse)
def review_batch(payload: BatchReviewRequest) -> BatchReviewResponse:
    """Submit many reviews in one request. Home mode: one Ollama batch when available. Company mode: no AI."""
    load_storage()
    if not payload.items:
        return BatchReviewResponse(results=[])

    company = payload.mode == "company"
    results: list[BatchReviewResultRow] = []
    ollama_inputs: list[tuple[str, str, str, str, Grade]] = []

    if not company:
        for item in payload.items:
            if item.post_action == "delete":
                continue
            card = CARDS.get(item.card_id)
            if not card or card.status != "active":
                raise HTTPException(status_code=404, detail=f"Card not found or not active: {item.card_id}")
            ollama_inputs.append(
                (card.id, card.question, card.answer, item.answer_text.strip(), item.user_grade)
            )

    batch_ai: dict[str, tuple[Grade, str]] | None = None
    if ollama_inputs:
        batch_ai = try_ollama_batch_review(ollama_inputs)

    today = str(date.today())

    for item in payload.items:
        if item.post_action == "delete":
            card = CARDS.get(item.card_id)
            if not card:
                raise HTTPException(status_code=404, detail=f"Card not found: {item.card_id}")
            deleted = CARDS.pop(item.card_id)
            REVIEW_LOGS.append(
                ReviewLog(
                    card_id=deleted.id,
                    category=deleted.category,
                    question=deleted.question,
                    answer_text="",
                    reference_answer=deleted.answer,
                    ai_grade="C",
                    user_grade="C",
                    suggested_interval_days=0,
                    next_review_at=deleted.next_review_at,
                    final_status="deleted",
                    reviewed_at=today,
                )
            )
            results.append(
                BatchReviewResultRow(
                    card_id=deleted.id,
                    question=deleted.question,
                    ai_grade="-",
                    next_review_at="-",
                    final_status="已删除",
                    user_answer=item.answer_text.strip() or "-",
                    reference_answer=deleted.answer or "-",
                    ai_analysis="",
                )
            )
            continue

        card = CARDS.get(item.card_id)
        if not card or card.status != "active":
            raise HTTPException(status_code=404, detail=f"Card not found or not active: {item.card_id}")

        if company:
            ai_grade = item.user_grade
            ai_analysis = COMPANY_REVIEW_NOTE
        else:
            if not (item.answer_text or "").strip():
                raise HTTPException(
                    status_code=400,
                    detail=f"answer_text is required in home mode (card_id={item.card_id}).",
                )
            pair = batch_ai.get(card.id) if batch_ai is not None else None
            if pair:
                ai_grade, ai_analysis = pair
            else:
                # Whole-batch Ollama failed, JSON parse failed, or this card_id missing from model output.
                ai_grade = simple_ai_grade(item.answer_text)
                ai_analysis = fallback_analysis(card.answer, item.answer_text)

        interval = FIXED_RULES.get((ai_grade, item.user_grade), 2)
        next_review_at = str(date.today() + timedelta(days=interval))
        card.next_review_at = next_review_at
        card.review_count += 1
        card.last_ai_grade = ai_grade
        card.last_user_grade = item.user_grade

        REVIEW_LOGS.append(
            ReviewLog(
                card_id=card.id,
                category=card.category,
                question=card.question,
                answer_text=item.answer_text,
                reference_answer=card.answer,
                ai_grade=ai_grade,
                user_grade=item.user_grade,
                suggested_interval_days=interval,
                next_review_at=next_review_at,
                final_status="normal",
                reviewed_at=today,
                ai_analysis=ai_analysis,
                review_mode=payload.mode,
            )
        )

        final_status = "正常"
        if item.post_action == "snooze_15d":
            card.next_review_at = str(date.today() + timedelta(days=15))
            next_review_at = card.next_review_at
            final_status = "延后15天"
            updated = False
            for log in reversed(REVIEW_LOGS):
                if log.card_id == card.id and log.reviewed_at == today and log.final_status == "normal":
                    log.final_status = "snooze_15d"
                    log.next_review_at = card.next_review_at
                    updated = True
                    break
            if not updated:
                REVIEW_LOGS.append(
                    ReviewLog(
                        card_id=card.id,
                        category=card.category,
                        question=card.question,
                        answer_text="",
                        reference_answer=card.answer,
                        ai_grade="C",
                        user_grade="C",
                        suggested_interval_days=0,
                        next_review_at=card.next_review_at,
                        final_status="snooze_15d",
                        reviewed_at=today,
                    )
                )

        results.append(
            BatchReviewResultRow(
                card_id=card.id,
                question=card.question,
                ai_grade=ai_grade,
                next_review_at=next_review_at,
                final_status=final_status,
                user_answer=item.answer_text,
                reference_answer=card.answer or "-",
                ai_analysis=ai_analysis,
            )
        )

    save_storage()
    return BatchReviewResponse(results=results)


@app.post("/api/stats/evaluate", response_model=StatsEvaluateResponse)
def evaluate_stats(payload: StatsEvaluateRequest) -> StatsEvaluateResponse:
    load_storage()

    usable_logs: list[ReviewLog] = []
    for log in REVIEW_LOGS:
        if not (log.reference_answer or "").strip():
            continue
        if not (log.ai_analysis or "").strip():
            continue
        if log.review_mode == "company":
            usable_logs.append(log)
            continue
        if not (log.answer_text or "").strip():
            continue
        usable_logs.append(log)

    if payload.card_ids:
        wanted = set(payload.card_ids)
        usable_logs = [log for log in usable_logs if log.card_id in wanted]

    if payload.category != "all":
        usable_logs = [log for log in usable_logs if log.category == payload.category]

    def reviewed_sort_key(log: ReviewLog) -> date:
        try:
            return date.fromisoformat(log.reviewed_at)
        except Exception:
            return date.min

    usable_logs.sort(key=reviewed_sort_key, reverse=True)
    limit = max(1, min(int(payload.limit), 30))
    selected = usable_logs[:limit]

    items = [
        StatsItem(
            card_id=log.card_id,
            category=log.category,
            question=log.question,
            user_answer=log.answer_text,
            reference_answer=log.reference_answer,
            final_status=log.final_status,
            ai_analysis=log.ai_analysis,
        )
        for log in selected
    ]

    ai_summary = try_ollama_stats_summary(selected) or fallback_stats_summary(selected)
    return StatsEvaluateResponse(items=items, ai_summary=ai_summary)


@app.post("/api/candidates/{candidate_id}/decision", response_model=CandidateCard)
def decide_candidate(candidate_id: str, payload: CandidateDecisionRequest) -> CandidateCard:
    candidate = CANDIDATES.get(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    if candidate.review_status != "pending":
        raise HTTPException(status_code=400, detail="Candidate already reviewed.")

    if payload.action == "reject":
        candidate.review_status = "rejected"
        save_storage()
        return candidate

    question = (payload.question or candidate.question).strip()
    answer = (payload.answer or candidate.answer).strip()
    if not question or not answer:
        raise HTTPException(status_code=400, detail="question and answer cannot be empty.")

    if payload.category is not None:
        candidate.category = payload.category

    candidate.review_status = "approved"
    new_id = next_numeric_suffix_id("card-", CARDS)
    CARDS[new_id] = Card(
        id=new_id,
        question=question,
        answer=answer,
        category=candidate.category,
        source_path="manual-import",
        source_type="pasted_text",
        status="active",
        next_review_at=str(date.today()),
        review_count=0,
    )
    save_storage()
    return candidate


@app.post("/api/cards/{card_id}/action", response_model=CardActionResponse)
def act_on_card(card_id: str, payload: CardActionRequest) -> CardActionResponse:
    card = CARDS.get(card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found.")

    if payload.action == "delete":
        deleted = CARDS.pop(card_id)
        final_status: CardStatus = "deleted"
        # Record deletion in review logs (answer/analysis may be empty).
        REVIEW_LOGS.append(
            ReviewLog(
                card_id=deleted.id,
                category=deleted.category,
                question=deleted.question,
                answer_text="",
                reference_answer=deleted.answer,
                ai_grade="C",
                user_grade="C",
                suggested_interval_days=0,
                next_review_at=deleted.next_review_at,
                final_status="deleted",
                reviewed_at=f"{date.today()}",
            )
        )
        save_storage()
        return CardActionResponse(
            card_id=deleted.id,
            status=final_status,
            next_review_at=deleted.next_review_at,
            action=payload.action,
        )

    if payload.action == "snooze_15d":
        card.next_review_at = str(date.today() + timedelta(days=15))
        today = str(date.today())

        # Update the latest "normal" review record for this card (same day),
        # so we keep user's answer + ai_analysis and only adjust final_status/next_review_at.
        updated = False
        for log in reversed(REVIEW_LOGS):
            if log.card_id == card.id and log.reviewed_at == today and log.final_status == "normal":
                log.final_status = "snooze_15d"
                log.next_review_at = card.next_review_at
                updated = True
                break

        if not updated:
            REVIEW_LOGS.append(
                ReviewLog(
                    card_id=card.id,
                    category=card.category,
                    question=card.question,
                    answer_text="",
                    reference_answer=card.answer,
                    ai_grade="C",
                    user_grade="C",
                    suggested_interval_days=0,
                    next_review_at=card.next_review_at,
                    final_status="snooze_15d",
                    reviewed_at=today,
                )
            )

        save_storage()
        return CardActionResponse(
            card_id=card.id,
            status=card.status,
            next_review_at=card.next_review_at,
            action=payload.action,
        )

    raise HTTPException(status_code=400, detail="Unsupported action.")
