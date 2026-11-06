"""手机 BOSS：搜索筛选、读取 JD、匹配去重、立即沟通并核对状态。"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

# 只操作用户指定设备上的 BOSS 界面，不调用招聘平台私有接口。
PACKAGE = "com.hpbr.bosszhipin"
TZ = timezone(timedelta(hours=8))
# 用户明确要求扩至 30 个；仍按有限批次计数，续跑不重复增加目标。
MAX_BATCH = 30
# 识别独立 Agent、AIAgent 连写及中文智能体，不使用公司名称作过滤依据。
AGENT_ROLE = re.compile(r"agent|智能体|智能代理", re.I)
# 仅复用刚取得的页面进行返回或滚动；沟通按钮仍强制重读。
SNAPSHOT_MAX_AGE = 2.0
# 常驻采集使用独立服务端口；页面动作只读等待五秒，不重放输入。
U2_PORT = 19018
PAGE_WAIT_SECONDS = 5.0
# 拒绝项只短期复用；筛选规则改变时递增版本，避免沿用旧判断。
NEGATIVE_CACHE_TTL = 6 * 60 * 60
NEGATIVE_CACHE_POLICY = 1
NEGATIVE_CACHE_LIMIT = 1000
# 列表标签没有资源名，只认完整且唯一的经验、学历文本。
EXPERIENCE_TAG = re.compile(r"(?:经验不限|应届生|在校/应届|\d+年以内|\d+年以上|\d+\s*[-~～–]\s*\d+年)")
DEGREE_TAGS = {"学历不限", "初中及以下", "中专/中技", "高中", "大专", "本科", "硕士", "博士"}
# 稳定判断保留业务内容和可操作控件几何，排除活跃状态、头像等装饰刷新。
STABILITY_IDS = {
    "job": set("tv_job_name tv_boss_name tv_boss_title tv_job_salary tv_required_location "
               "tv_required_work_exp tv_required_degree tv_description btn_chat btn_continue_chat "
               "iv_back tv_job_competitive_title".split()),
    "search_results": set("tv_search_hint tv_tab_label tv_label tv_position_name tv_salary_statue "
                          "tv_company_name tv_employer tv_distance tv_digest".split()),
    "chat": set("tv_title tv_position_name tv_company_name editText_with_scrollbar tv_contact_time "
                "tv_content_text iv_avatar mMsgTvStatus".split()),
    "search_input": {"et_search", "tv_search"},
}
DEFAULT_OUTPUT = Path(__file__).parent / "boss_apply_data"
DEFAULT_OCR = Path("D:/PersonalGrowth/生活领域/求职/feedback-reader/ocr_text.ps1")


class StopRun(RuntimeError):
    """页面或发送结果无法确定时，停止整批并保留记录。"""


class TransientPage(StopRun):
    """页面切换期间暂未取得 BOSS 窗口，只允许等待，不再次输入。"""


class ViewportError(StopRun):
    """无法确认可用显示区域，常驻采集须退回原方式。"""


class JobIdentityMismatch(StopRun):
    """只读岗位详情身份不符，记录待核后可安全返回列表，不进行沟通。"""

    def __init__(self, detail, snapshot):
        """保留实际详情及当前快照，不把匿名客户和招聘机构合并成同一公司。"""
        super().__init__("列表与详情身份不一致，未沟通，已记待核")
        self.detail, self.snapshot = detail, snapshot


def display_viewport(text):
    """取主屏的应用可用尺寸，排除物理尺寸、基础配置和虚拟屏幕。"""
    values = set()
    for line in text.splitlines():
        if "mOverrideDisplayInfo=DisplayInfo{" not in line or not re.search(r'displayId\s+0[",\s]', line):
            continue
        size = re.search(r", app (\d+) x (\d+)", line)
        rotation = re.search(r"\brotation (\d+)", line)
        if size and rotation:
            values.add((*map(int, size.groups()), int(rotation[1])))
    if len(values) != 1 or min(next(iter(values))[:2]) <= 0:
        raise ViewportError("主屏可用显示区域无法唯一确认")
    return next(iter(values))


@dataclass
class Criteria:
    """薪资以月薪 K 为单位；岗位区间与目标区间有交集即可纳入。"""

    keyword: str = "go"
    city: str = "深圳"
    salary_min: int = 15
    salary_max: int = 25
    exclude_agent: bool = True


def now():
    """返回上海时区时间，便于核对批次与聊天记录。"""
    return datetime.now(TZ).isoformat(timespec="seconds")


def normalized(value):
    """只消除空白和已观察到的岗位装饰，不做模糊公司名合并。"""
    text = re.sub(r"\s+", "", str(value).replace("&@", "")).strip().casefold()
    # 列表与详情可能用不同数量的点显示同一省略号；保留前缀，不做模糊补全。
    return re.sub(r"(?:\.{3,}|…+)$", "…", text)


def identity(job):
    """以公司、岗位、招聘人标识候选，不使用会变化的薪资作为主键。"""
    return tuple(normalized(job.get(k, "")) for k in ("company", "title", "hr"))


def job_key(job):
    """生成本地可复核主键，不声称它是平台唯一 ID。"""
    return hashlib.sha256("|".join(identity(job)).encode()).hexdigest()[:20]


def salary_range(text):
    """解析月薪区间，忽略额外月数，不将年薪或日薪换算成月薪。"""
    match = re.search(r"(\d+(?:\.\d+)?)\s*[-~～]\s*(\d+(?:\.\d+)?)\s*[kK]", text)
    return tuple(map(float, match.groups())) if match else None


def is_agent_role(job):
    """硬过滤标题和 JD 的 Agent／智能体字样，不再推断职责、章节或加分项。"""
    text = " ".join(str(job.get(field) or "") for field in ("title", "jd"))
    return bool(AGENT_ROLE.search(text))


def qualification_review(job):
    """共用列表和详情的资格门槛，不因提前读取而改变待核口径。"""
    reasons = []
    if re.search(r"5\s*[-~～–]\s*10年|10年以上", job.get("experience", "")):
        reasons.append("经验年限超过当前简历")
    if job.get("degree") in {"硕士", "博士"}:
        reasons.append("学历要求超过当前简历")
    return reasons


def prefilter_job(job, criteria):
    """列表只淘汰已知不符项，字段缺失或标题未写 Go 仍进入详情。"""
    reasons = []
    if criteria.exclude_agent and is_agent_role({"title": job.get("title", "")}):
        reasons.append("Agent/智能体岗位")
    title = re.sub(r"非外包|不外包|非驻场|不驻场", "", job.get("title", ""))
    if re.search(r"外包|驻场", title):
        reasons.append("标题明确外包或驻场")
    if job.get("location") and criteria.city not in job["location"]:
        reasons.append("地点不符")
    salary = salary_range(job.get("salary", ""))
    if salary and (salary[0] > salary[1] or salary[1] < criteria.salary_min or salary[0] > criteria.salary_max):
        reasons.append("薪资不符")
    review = qualification_review(job)
    return dict(status="skipped" if reasons else ("review" if review else "candidate"), reasons=reasons + review)


def evaluate_job(job, criteria):
    """按明确事实筛选；字段缺失及硬性经验疑点进入待核。"""
    reasons, review = [], []
    title, jd = job.get("title", ""), job.get("jd", "")
    if criteria.exclude_agent and is_agent_role(job):
        reasons.append("Agent/智能体岗位")
    # 1. 排除措辞中的否定和历史经历要求，不能把“非外包”误当外包。
    employment = re.sub(r"非外包|不(?:是|属于)?外包|无外包经历|不接受外包经历|不(?:需要|用|要求)?驻场|无需驻场|非驻场", "", jd)
    title_employment = re.sub(r"非外包|不外包|非驻场|不驻场", "", title)
    if (re.search(r"外包|驻场", title_employment)
            or re.search(r"(?:本岗位|该岗位|用工性质|岗位性质)[：:为是\s]{0,4}外包|(?:需要|需|长期|派遣|客户现场)驻场|外包(?:岗位|性质)|劳务派遣|外派岗位", employment)):
        reasons.append("明确外包或驻场")
    elif re.search(r"合作伙伴|第三方用工|外包", employment):
        review.append("用工性质存在含糊表述，需核实")
    if job.get("contacted"):
        reasons.append("界面显示已沟通")
    if job.get("closed"):
        reasons.append("岗位已关闭")
    if not re.search(r"(?<![a-z])go(?:lang)?(?![a-z])", title + " " + jd, re.I):
        reasons.append("未见 Go 岗位依据")
    if job.get("location") and criteria.city not in job["location"]:
        reasons.append("地点不符")
    elif not job.get("location"):
        review.append("地点缺失")
    # 2. 按用户确认的交集口径筛选，额外月薪不改变月薪区间判断。
    salary = salary_range(job.get("salary", ""))
    if salary:
        low, high = salary
        if low > high or high < criteria.salary_min or low > criteria.salary_max:
            reasons.append("薪资不符")
    else:
        review.append("月薪区间无法确认")
    if not job.get("jd_complete"):
        review.append("JD 未完整展开")
    if not all(job.get(k) for k in ("title", "company", "hr")):
        review.append("岗位身份字段缺失")
    review.extend(qualification_review(job))
    if re.search(r"(?:必须|硬性|要求具备|至少).{0,25}(?:生产\s*K8s|K8s.{0,8}(?:集群|运维)|PB级|内核驱动)", jd, re.I):
        review.append("硬性经验要求需人工核实")
    return dict(status="skipped" if reasons else ("review" if review else "ready"),
                reasons=reasons + review)


class History:
    """兼容已有 feedback-reader 记录，按公司和岗位阻止重复投递。"""

    def __init__(self, paths=()):
        """只读用户指定的历史 JSON，不扫描其他私人目录。"""
        self.keys = set()
        self.roles = set()
        self.paths = []
        for path in paths:
            path = Path(path)
            if path.is_dir():
                path = path / "results.json"
            self.paths.append(str(path.resolve()))
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(data, (dict, list)) or (isinstance(data, dict) and not {"records", "results"}.intersection(data)):
                raise StopRun(f"历史记录缺少 records/results：{path}")
            records = data if isinstance(data, list) else data.get("records", data.get("results", []))
            if not isinstance(records, list):
                raise StopRun(f"历史记录结构无法识别：{path}")
            for record in records:
                # 新版运行报告包含未沟通过的待核/跳过项，这些不算已沟通历史。
                if record.get("status") in {"ready", "review", "skipped"}:
                    continue
                adapted = dict(company=record.get("company", ""),
                               title=record.get("card_job_title") or record.get("list_job_title") or record.get("title", ""),
                               hr=record.get("hr_name") or record.get("hr", ""))
                key = identity(adapted)
                if key[0] and key[1]:
                    self.keys.add(key)
                    self.roles.add(key[:2])

    def contains(self, job):
        """按公司和岗位去重，招聘人变化不再绕过历史。"""
        return identity(job)[:2] in self.roles


class Journal:
    """点击沟通前写入持久记录；即使进程被杀，也不重复触发。"""

    def __init__(self, directory):
        """运行状态与原始证据分开管理，保留到用户主动处理。"""
        self.path = Path(directory) / "journal.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events = []
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    self.events.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise StopRun("沟通记录损坏，需人工核对，禁止忽略后重试") from exc

    def contains(self, job):
        """同公司同岗位的已尝试和未知结果均阻止再投，保留旧键兼容。"""
        role, key = identity(job)[:2], job_key(job)
        return any(event["key"] == key or all(role) and identity(event)[:2] == role for event in self.events)

    def latest(self, job):
        """恢复时以最后一次实际沟通证据为准，不用报告中的临时状态猜结果。"""
        return next((e for e in reversed(self.events) if e["key"] == job_key(job)), None)

    def record(self, job, status, reason, source=""):
        """追加后 fsync，确保立即沟通按钮触发前的意图已落盘。"""
        event = dict(at=now(), key=job_key(job), status=status, reason=reason,
                     company=job.get("company"), title=job.get("title"), hr=job.get("hr"), source=source)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.events.append(event)


def write_json(path, data):
    """使用同目录原子替换保存批次，防止中断留下半份清单。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


class NegativeCache:
    """跨批次缓存完整 JD 的明确拒绝项；命中只能跳过，不能授权沟通。"""

    def __init__(self, path, criteria, account):
        """缓存与账号、规则和筛选条件绑定；损坏或旧版本缓存直接失效。"""
        self.path, self.criteria, self.account = Path(path), asdict(criteria), account
        self.entries = {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if (isinstance(data, dict) and data.get("policy_version") == NEGATIVE_CACHE_POLICY
                    and data.get("criteria") == self.criteria and data.get("account") == account):
                self.entries = {key: value for key, value in data.get("entries", {}).items()
                                if isinstance(value, dict) and isinstance(value.get("expires_at"), (int, float))
                                and isinstance(value.get("cached_at"), (int, float))
                                and value["cached_at"] <= time.time()
                                and value["cached_at"] < value["expires_at"] <= value["cached_at"] + NEGATIVE_CACHE_TTL
                                and value["expires_at"] > time.time()
                                and value.get("status") in {"skipped", "review"}
                                and isinstance(value.get("source"), str)
                                and isinstance(value.get("reasons"), list) and value["reasons"]
                                and all(isinstance(reason, str) for reason in value["reasons"])}
        except (OSError, ValueError, TypeError, AttributeError):
            self.entries = {}

    @staticmethod
    def signature(row):
        """字段齐全才复用；招聘人或列表条件、正文摘要改变均重新读取。"""
        fields = ("company", "title", "hr", "salary", "location", "experience", "degree")
        if not all(isinstance(row.get(field), str) and row[field].strip() for field in fields):
            return None
        values = [row[field] for field in fields] + [row.get("digest", "")]
        return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()

    def lookup(self, row):
        """仅返回仍有效的拒绝依据，不延长有效期，不替代沟通历史。"""
        signature = self.signature(row)
        entry = self.entries.get(signature) if signature else None
        return dict(entry) if entry and entry["expires_at"] > time.time() else None

    def remember(self, value, row, decision):
        """只保存完整且身份匹配的 Agent 或资格拒绝；不保存不完整、含糊项。"""
        signature = self.signature(row)
        if (not signature or not value.get("jd_complete") or identity(value) != identity(row)
                or decision["status"] not in {"skipped", "review"}
                or not ({"Agent/智能体岗位", *qualification_review(value)} & set(decision["reasons"]))):
            return
        # 保留原证据和期限；不缓存可投递结果，过期后必须重新打开详情。
        stamp = time.time()
        self.entries[signature] = dict(status=decision["status"], reasons=list(decision["reasons"]),
            cached_at=stamp, expires_at=stamp + NEGATIVE_CACHE_TTL,
            source=value.get("jd_source", value.get("source", "")))
        valid = [(key, entry) for key, entry in self.entries.items() if entry["expires_at"] > stamp]
        self.entries = dict(sorted(valid, key=lambda pair: pair[1]["cached_at"])[-NEGATIVE_CACHE_LIMIT:])
        write_json(self.path, dict(policy_version=NEGATIVE_CACHE_POLICY, criteria=self.criteria,
                                  account=self.account, entries=self.entries))


def reconcile_batch(report, journal):
    """补回已落日志的成功结果；存在未确认的点击时阻止继续操作。"""
    pending = []
    for value in report["records"]:
        if not value.get("attempted"):
            continue
        event = journal.latest(value)
        if event is None:
            # 意图尚未落盘，contact_job 不可能已点击；可以复用已读 JD。
            value.update(status="cached", attempted=False)
        elif event["status"] in {"contacted", "already_contacted"}:
            value.update(status=event["status"], contact_source=event.get("source", ""))
        else:
            value.update(status="unknown")
            pending.append(job_key(value))
    report["contacted"] = sum(j.get("status") == "contacted" for j in report["records"])
    report["complete"] = report["contacted"] >= report["target"]
    if report["complete"]:
        report["state"] = "complete"
    if pending:
        raise StopRun("批次有未确认的沟通结果，须先核对聊天并补齐日志，未自动重试")


def open_batch(path, criteria, serial, account, target, journal, new_batch=False):
    """默认续接同一批次；完成后重复执行不新增沟通，新批次显式创建。"""
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if previous and previous.get("version") == 3:
        try:
            reconcile_batch(previous, journal)
        finally:
            write_json(path, previous)
        if not new_batch:
            expected = (asdict(criteria), serial, account, target)
            actual = (previous["criteria"], previous["serial"], previous["account"], previous["target"])
            if expected != actual:
                raise StopRun("续跑条件与原批次不同；沿用原条件，或用 --new-batch 开始新批次")
            previous.pop("stop_reason", None)
            return previous, True
    if previous:
        if previous.get("version") not in {2, 3}:
            raise StopRun("不支持的批次版本，未覆盖原记录")
        # 旧版或显式新建前保留原始报告，沟通日志始终跨批次去重。
        archive = path.with_name(f"results-{previous.get('batch_id', time.time_ns())}.json")
        write_json(archive, previous)
    report = dict(version=3, batch_id=str(time.time_ns()), started_at=now(), serial=serial,
                  account=account, criteria=asdict(criteria), target=target, contacted=0,
                  records=[], complete=False, state="running", timings={},
                  history_paths=previous.get("history_paths", []) if previous else [])
    write_json(path, report)
    return report, False


@contextmanager
def timed(report, phase):
    """累计各阶段耗时，方便按实际瓶颈继续优化。"""
    start = time.perf_counter()
    try:
        yield
    finally:
        timings = report.setdefault("timings", {})
        timings[phase] = round(timings.get(phase, 0) + time.perf_counter() - start, 3)


class Snapshot:
    """只接收 BOSS 当前 UI 树，以当前节点定位，拒绝使用过期坐标。"""

    def __init__(self, xml, source="", viewport=None):
        """确认应用包名和常见阻断提示，未知页面不执行导航。"""
        self.root = ET.fromstring(xml)
        self.nodes = list(self.root.iter("node"))
        self.parents = {c: p for p in self.nodes for c in p}
        self.source = source
        self.captured_at = time.monotonic()
        if not any(n.get("package") == PACKAGE for n in self.nodes):
            raise TransientPage("手机未停在 BOSS，或已锁屏；请手动打开 BOSS")
        if any(re.search(r"安全验证|拖动滑块|请完成验证|操作过于频繁|人机验证", n.get("text", "")) for n in self.nodes):
            raise StopRun("遇到验证码或频率提示，请本人处理后重新运行")
        if viewport is not None:
            self.width, self.height = viewport
            if min(viewport) <= 0:
                raise ViewportError("可用显示区域无效")
            # 裁剪负坐标及底部系统栏外的节点；完全不可见的矩形统一归零。
            for node in self.nodes:
                left, top, right, bottom = self.bounds(node)
                left, top = max(0, left), max(0, top)
                right, bottom = min(self.width, right), min(self.height, bottom)
                if right <= left or bottom <= top:
                    left = top = right = bottom = 0
                node.set("bounds", f"[{left},{top}][{right},{bottom}]")
        else:
            self.width = max((self.bounds(n)[2] for n in self.nodes), default=1080)
            self.height = max((self.bounds(n)[3] for n in self.nodes), default=2400)

    @staticmethod
    def bounds(node):
        """解析 UIAutomator 矩形，缺失矩形不构造猜测坐标。"""
        values = tuple(map(int, re.findall(r"-?\d+", node.get("bounds", ""))))
        return values if len(values) == 4 else (0, 0, 0, 0)

    @staticmethod
    def rid(node):
        """去掉应用前缀，兼容相同资源名。"""
        return node.get("resource-id", "").rsplit("/", 1)[-1]

    def find(self, rid=None, text=None):
        """返回满足资源名及精确文字的所有当前节点。"""
        return [n for n in self.nodes if (rid is None or self.rid(n) == rid)
                and (text is None or n.get("text", "") == text)]

    def unique(self, rid=None, text=None):
        """控件有歧义就停止，不取首个重复控件。"""
        nodes = self.find(rid, text)
        if len(nodes) != 1:
            raise StopRun(f"控件不唯一或缺失：{rid or text}，数量 {len(nodes)}")
        return nodes[0]

    def text(self, rid):
        """读取唯一资源名的文字。"""
        nodes = self.find(rid)
        return nodes[0].get("text", "") if len(nodes) == 1 else ""

    def header_text(self, rid):
        """只取顶部栏唯一标题，排除聊天里的竞争分析等同名控件。"""
        nodes = [n for n in self.find(rid) if 0 < self.bounds(n)[3] < self.height * .2]
        return nodes[0].get("text", "") if len(nodes) == 1 else ""

    def description_end_visible(self):
        """正文底部贴住滚动容器边缘时先滚动，避免对屏幕外的展开入口做 OCR。"""
        node = self.unique(rid="tv_description")
        bottom = self.bounds(node)[3]
        while node in self.parents:
            node = self.parents[node]
            if node.get("scrollable") == "true":
                return bottom < self.bounds(node)[3] - 2
        return True

    def has_chat_draft(self):
        """区分已观察到的输入框提示与真实草稿，始终不改动输入框。"""
        text = self.text("editText_with_scrollbar").strip()
        return bool(text and text not in {"介绍自己回复率更高哦~", "介绍自己回复率更高哦～"})

    def state(self):
        """按真实资源组合识别页面，不根据单个标题猜沟通状态。"""
        if (self.find(text="你可能感兴趣以下工作") and self.find(text="添加多个求职期望，更容易找到工作")
                and self.find(text="立即添加")):
            return "preference_prompt"
        if self.find("tv_pop_text"):
            return "tooltip"
        if self.find("editText_with_scrollbar"):
            return "chat"
        if (self.find("tv_job_name") or self.find("tv_description")
                or self.find("iv_back") and self.find("tv_job_competitive_title")
                and (self.find("btn_chat") or self.find("btn_continue_chat"))):
            return "job"
        if self.find("btn_confirm") and self.find("tv_condition_title"):
            return "filter"
        if self.find("tv_search_hint") and self.find("tv_tab_label"):
            return "search_results"
        if self.find("et_search"):
            return "search_input"
        if self.find("tv_my_resume"):
            return "profile"
        if self.find("cl_tab_1"):
            return "home"
        return "unknown"

    def stability_key(self):
        """比较当前页面的业务字段、控件位置和状态；未知页面仍比较整棵树。"""
        state = self.state()
        if state in STABILITY_IDS:
            ids = STABILITY_IDS[state]
            nodes = [n for n in self.nodes if self.rid(n) in ids
                     or state == "search_results" and (EXPERIENCE_TAG.fullmatch(n.get("text", ""))
                                                       or n.get("text") in DEGREE_TAGS)]
        elif state == "filter":
            # 无资源名的筛选标题也保留；筛选面板动画或选项变化不能提前结束。
            nodes = [n for n in self.nodes if n.get("text") or n.get("clickable") == "true"
                     or n.get("scrollable") == "true"]
        else:
            return ET.tostring(self.root)
        attributes = ("text", "content-desc", "class", "bounds", "selected", "checked", "enabled", "focused")
        return (state, self.width, self.height, self.root.get("rotation"),
                tuple((self.rid(n), *(n.get(key, "") for key in attributes)) for n in nodes))

    def rows(self):
        """向上找单个岗位卡片，避免把相邻公司的字段拼成一个岗位。"""
        result = []
        for title in self.find("tv_position_name"):
            node = title
            while node in self.parents:
                node = self.parents[node]
                children = list(node.iter("node"))
                if sum(self.rid(n) == "tv_position_name" for n in children) != 1:
                    break
                fields = {self.rid(n): n.get("text", "") for n in children if self.rid(n)}
                if not fields.get("tv_company_name") or not fields.get("tv_employer"):
                    continue
                left, top, right, bottom = self.bounds(node)
                if top < 300 or bottom >= self.height - 5 or right <= left:
                    break
                tags = {n.get("text", "").strip() for n in children if not self.rid(n)}
                experiences = {text for text in tags if EXPERIENCE_TAG.fullmatch(text)}
                degrees = tags & DEGREE_TAGS
                result.append(dict(title=title.get("text", "").replace("&@", "").strip(),
                                   company=fields["tv_company_name"],
                                   hr=re.split(r"[·•]", fields["tv_employer"])[0].strip(),
                                   salary=fields.get("tv_salary_statue", ""),
                                   location=fields.get("tv_distance", ""),
                                   experience=next(iter(experiences)) if len(experiences) == 1 else "",
                                   degree=next(iter(degrees)) if len(degrees) == 1 else "",
                                   digest=fields.get("tv_digest", ""), node=title))
                break
        return result


@contextmanager
def device_lock(serial):
    """跨输出目录互斥本脚本的设备操作；崩溃遗留锁须本人核对后清理。"""
    name = hashlib.sha256(serial.encode()).hexdigest()[:16]
    path = Path(tempfile.gettempdir()) / f"boss-apply-{name}.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise StopRun(f"设备已有运行锁：{path}；请勿与其他采集程序同时操作") from exc
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


class Device:
    """单设备 ADB 适配，保留每次页面和输入操作依据。"""

    def __init__(self, serial, output, ocr_helper=DEFAULT_OCR):
        """绑定明确序列号，拒绝默认选择列表中的另一台设备。"""
        self.serial, self.output = serial, Path(output)
        self.ocr_helper = Path(ocr_helper) if ocr_helper else None
        self.output.mkdir(parents=True, exist_ok=True)
        self.counter = 0
        self.backend = "adb"
        self.metrics = dict(captures=0, capture_seconds=0.0, ocr_calls=0, ocr_seconds=0.0, adb_captures=0)

    def call(self, *args, timeout=30):
        """参数数组执行命令，所有设备动作明确带 -s。"""
        result = subprocess.run(["adb", "-s", self.serial, *args], capture_output=True, timeout=timeout)
        if result.returncode:
            raise StopRun(result.stderr.decode("utf-8", errors="replace")[-400:])
        return result.stdout

    def capture(self, label="page"):
        """仅在 dump 成功后读取 XML，旧快照不进入决策。"""
        start = time.perf_counter()
        dump = self.call("shell", "uiautomator", "dump", "/data/local/tmp/codex-boss-apply.xml")
        if b"dumped to:" not in dump:
            raise StopRun("UI 导出失败，未读取旧快照")
        raw = self.call("exec-out", "cat", "/data/local/tmp/codex-boss-apply.xml")
        snap = Snapshot(raw.decode("utf-8"))
        self.counter += 1
        path = self.output / "evidence" / f"{time.time_ns()}-{self.counter}-{label}.xml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        snap.source = str(path.resolve())
        self.metrics["captures"] += 1
        self.metrics["adb_captures"] += 1
        self.metrics["capture_seconds"] += time.perf_counter() - start
        return snap

    def close(self):
        """原 ADB 方式没有常驻资源，保留统一的退出入口。"""

    def __enter__(self):
        """把设备服务的释放纳入设备锁保护范围。"""
        return self

    def __exit__(self, *error):
        """正常退出或发生异常都关闭本次创建的服务。"""
        self.close()

    def after_action(self, label, predicate=None, stable=False):
        """原方式沿用单次读取；常驻方式覆盖为有上限的就绪等待。"""
        return self.capture(label)

    @staticmethod
    def tap_target(snap, node):
        """依据已确认控件等待目标页面，沟通按钮必须等待对应岗位的成功证据。"""
        rid, text = Snapshot.rid(node), node.get("text", "")
        if rid == "btn_chat":
            job = Device.detail_identity(snap)
            return lambda current: Device.check_contact(job, current)
        if rid == "tv_position_name" and snap.state() == "search_results":
            return lambda current: current.state() == "tooltip" or (
                current.state() == "job" and all(Device.detail_identity(current).values()))
        if rid == "tv_search_hint" or node.get("class") == "android.widget.RelativeLayout" and snap.state() == "home":
            return lambda current: current.state() == "search_input"
        if rid == "tv_search":
            query = normalized(snap.text("et_search"))
            return lambda current: current.state() == "search_results" and normalized(current.text("tv_search_hint")) == query
        if rid == "et_search":
            return lambda current: current.state() == "search_input" and current.unique(rid="et_search").get("focused") == "true"
        if rid == "tv_tab_label" and text.startswith("筛选"):
            return lambda current: current.state() == "filter"
        if rid == "keywords_view_text":
            return lambda current: current.state() == "filter" and any(n.get("selected") == "true" for n in current.find(rid,text))
        if rid == "btn_confirm":
            return lambda current: current.state() == "search_results"
        if rid == "cl_tab_1":
            return lambda current: current.state() == "home"
        return None

    def navigation_snapshot(self, snap, label):
        """返回、滚动复用两秒内快照，超过时限自动重读。"""
        if isinstance(snap, Snapshot) and time.monotonic() - snap.captured_at <= SNAPSHOT_MAX_AGE:
            return snap
        return self.capture(label)

    def tap(self, snap, node):
        """点击前重读控件；同文字、资源名和矩形必须仍然唯一。"""
        current = self.capture("before-tap")
        targets = [n for n in current.nodes if Snapshot.rid(n) == Snapshot.rid(node)
                   and n.get("text", "") == node.get("text", "")
                   and Snapshot.bounds(n) == Snapshot.bounds(node)]
        if current.state() != snap.state() or len(targets) != 1:
            raise StopRun("页面已变化，停止使用旧控件")
        if Snapshot.rid(node) == "btn_chat" and node.get("text") == "立即沟通":
            expected, actual = Device.detail_identity(snap), Device.detail_identity(current)
            if not all(actual.values()) or identity(expected) != identity(actual):
                raise StopRun("点击前岗位身份发生变化，未发起沟通")
        left, top, right, bottom = Snapshot.bounds(targets[0])
        if not (0 <= left < right <= current.width and 0 <= top < bottom <= current.height):
            raise StopRun("控件没有有效可见矩形")
        self.call("shell", "input", "tap", str((left + right) // 2), str((top + bottom) // 2))
        return self.after_action("after-tap", self.tap_target(snap, node))

    def back(self, snap=None):
        """只允许从已识别的只读页面返回，聊天草稿不自动退出。"""
        snap = self.navigation_snapshot(snap, "before-back")
        if snap.state() not in {"job", "filter", "search_results", "search_input", "tooltip", "preference_prompt"}:
            raise StopRun("未知页面或聊天中不自动返回")
        self.call("shell", "input", "keyevent", "4")
        return self.after_action("after-back", lambda current: current.state() != snap.state())

    def scroll(self, direction="down", snap=None):
        """只滚动结果或 JD 正文，手势避开发送按钮。"""
        snap = self.navigation_snapshot(snap, "before-scroll")
        if snap.state() not in {"search_results", "job"}:
            raise StopRun("当前不是结果列表或 JD，拒绝滚动")
        # JD 使用较短手势，避免越过折叠正文后被列表回收；结果页继续整屏翻动。
        start, end = ((.68, .48) if direction == "down" else (.48, .68)) if snap.state() == "job" else (
            (.78, .38) if direction == "down" else (.38, .78))
        self.call("shell", "input", "swipe", str(snap.width // 2), str(int(snap.height * start)),
                  str(snap.width // 2), str(int(snap.height * end)), "650")
        return self.after_action("after-scroll", lambda current: current.state() == snap.state(), stable=True)

    def fill_ascii(self, snap, node, text):
        """搜索词只允许 ASCII；点击聚焦、清空再填写并读回。"""
        if not re.fullmatch(r"[a-zA-Z0-9_ -]{1,80}", text):
            raise StopRun("搜索词当前仅支持 ASCII")
        focused = self.tap(snap, node)
        field = focused.unique(rid="et_search")
        if field.get("focused") != "true":
            raise StopRun("搜索框未聚焦")
        if field.get("text", "").casefold() == text.casefold():
            return focused
        self.call("shell", "input", "keyevent", "123")
        self.call("shell", "input", "keyevent", *(["67"] * (len(field.get("text", "")) + 4)))
        # 删除事件可能仍在输入法队列中；等待 UI 空闲后再输入，避免首字被迟到的删除吞掉。
        cleared = self.after_action("search-cleared", lambda current: current.state() == "search_input", stable=True)
        # 真机空框可能只显示提示词而未接受按键，再点一次实际编辑区域恢复输入。
        self.tap(cleared, cleared.unique(rid="et_search"))
        self.call("shell", "input", "text", text.replace(" ", "%s"))
        result = self.after_action("search-typed", lambda current: current.text("et_search").casefold() == text.casefold())
        if result.text("et_search").casefold() != text.casefold():
            raise StopRun("搜索词读回不符")
        return result

    def search(self, criteria):
        """进入搜索并确认城市；不改求职期望和个人资料。"""
        snap = self.capture("search-start")
        if snap.state() == "profile":
            snap = self.tap(snap, snap.unique(rid="cl_tab_1"))
        for _ in range(4):
            if snap.state() in {"home", "search_input", "search_results"}:
                break
            snap = self.back(snap)
        if snap.state() == "home":
            # 真机已观察：职位页右上角的空白 RelativeLayout 是放大镜；只认该结构。
            candidates = [n for n in snap.nodes if n.get("class") == "android.widget.RelativeLayout"
                          and n.get("clickable") == "true" and not n.get("text")
                          and Snapshot.bounds(n)[0] > snap.width * .85
                          and 0 < Snapshot.bounds(n)[1] < snap.height * .1]
            if len(candidates) != 1:
                raise StopRun("搜索入口结构变化，请手动打开搜索页")
            snap = self.tap(snap, candidates[0])
        elif snap.state() == "search_results":
            snap = self.tap(snap, snap.unique(rid="tv_search_hint"))
        if snap.state() != "search_input":
            raise StopRun("请手动进入 BOSS 职位搜索页")
        snap = self.fill_ascii(snap, snap.unique(rid="et_search"), criteria.keyword)
        snap = self.tap(snap, snap.unique(rid="tv_search", text="搜索"))
        if snap.state() != "search_results":
            raise StopRun("搜索后没有进入职位结果页")
        if normalized(snap.text("tv_search_hint")) != normalized(criteria.keyword):
            raise StopRun("结果页的实际搜索词与条件不符")
        # BOSS 会保留列表滚动位置；城市栏折叠时先恢复，不能把不可见误认为全国。
        for _ in range(4):
            if snap.find("tv_tab_label", criteria.city) or snap.find("tv_tab_label", "全国"):
                break
            snap = self.scroll("up", snap=snap)
        if not snap.find("tv_tab_label", criteria.city):
            snap = self.tap(snap, snap.unique(rid="tv_tab_label", text="全国"))
            snap = self.tap(snap, snap.unique(text=criteria.city))
        if not snap.find("tv_tab_label", criteria.city):
            raise StopRun("城市筛选未确认；请手动选择目标城市后重试")
        return snap

    def salary_filter(self, bucket):
        """真机薪资档位为 10–20K、20–50K，分两轮读取后按实际薪资细筛。"""
        snap = self.capture("salary-start")
        labels = [n for n in snap.find("tv_tab_label") if n.get("text", "").startswith("筛选")]
        # 结果列表向下滚动后，筛选栏会折叠；先恢复栏位，不猜测原坐标。
        for _ in range(4):
            if labels:
                break
            snap = self.scroll("up", snap=snap)
            labels = [n for n in snap.find("tv_tab_label") if n.get("text", "").startswith("筛选")]
        if len(labels) != 1:
            raise StopRun("筛选入口不唯一")
        snap = self.tap(snap, labels[0])
        if snap.state() != "filter":
            raise StopRun("筛选面板未打开")
        selection = snap.unique(rid="keywords_view_text", text=bucket)
        if selection.get("selected") != "true":
            snap = self.tap(snap, selection)
        if snap.unique(rid="keywords_view_text", text=bucket).get("selected") != "true":
            raise StopRun("薪资档位未选中")
        snap = self.tap(snap, snap.unique(rid="btn_confirm", text="确定"))
        if snap.state() != "search_results":
            raise StopRun("薪资筛选后未回结果页")
        return snap

    def expand_jd(self, snap):
        """复用既有本机 OCR 辅助程序，只点正文内精确的展开文字。"""
        if not snap.description_end_visible():
            return snap
        if not self.ocr_helper or not self.ocr_helper.is_file() or sys.platform != "win32":
            return snap
        description = snap.unique(rid="tv_description")
        image = self.output / "evidence" / f"{time.time_ns()}-expand.png"
        image.write_bytes(self.call("exec-out", "screencap", "-p"))
        start = time.perf_counter()
        self.metrics["ocr_calls"] += 1
        try:
            result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-File",
                                     str(self.ocr_helper), str(image.resolve())], capture_output=True,
                                    timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        finally:
            self.metrics["ocr_seconds"] += time.perf_counter() - start
        if result.returncode:
            return snap
        try:
            items = json.loads(result.stdout.decode("utf-8-sig"))
        except (ValueError, UnicodeError):
            return snap
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            return snap
        left, top, right, bottom = Snapshot.bounds(description)
        targets = [item for item in items if item.get("text") == "查看更多"
                   and isinstance(item.get("x"), (int, float)) and isinstance(item.get("y"), (int, float))
                   and left <= item["x"] <= right and top < item["y"] < bottom]
        if len(targets) == 1:
            fresh = self.capture("before-expand")
            if fresh.text("tv_description") != snap.text("tv_description"):
                raise StopRun("OCR 后正文发生变化")
            self.call("shell", "input", "tap", str(round(targets[0]["x"])), str(round(targets[0]["y"])))
            return self.after_action("expanded", lambda current: bool(current.text("tv_description"))
                                     and "查看更多" not in current.text("tv_description"))
        return snap

    def read_job(self, row, snap, cached=None):
        """读取完整 JD 和身份；标题或招聘方对不上时停止。"""
        snap = self.tap(snap, row["node"])
        if snap.state() == "tooltip":
            snap = self.back(snap)
        if snap.state() != "job":
            raise StopRun("打开岗位后页面无法识别")
        company = re.split(r"[·•]", snap.text("tv_boss_title"))[0].strip()
        value = dict(title=snap.text("tv_job_name").replace("&@", "").strip(), company=company,
                     hr=snap.text("tv_boss_name"), salary=snap.text("tv_job_salary"),
                     location=snap.text("tv_required_location"), experience=snap.text("tv_required_work_exp"),
                     degree=snap.text("tv_required_degree"), contacted=bool(snap.find("btn_continue_chat")),
                     closed="停止招聘" in snap.text("tv_job_salary"))
        if identity(value) != identity(row):
            raise JobIdentityMismatch(value, snap)
        preview = snap.text("tv_description")
        fields = ("salary", "location", "experience", "degree")
        # 身份、当前招聘条件和折叠正文都未变，才复用同批次的完整 JD。
        cache_hit = bool(cached and cached.get("jd_complete") and preview
                         and identity(value) == identity(cached)
                         and all(value[k] == cached.get(k) for k in fields)
                         and preview in {cached.get("jd_preview"), cached.get("jd")})
        if cache_hit:
            value.update(jd=cached["jd"], jd_complete=True, jd_preview=preview,
                         cache_hit=True, jd_source=cached.get("jd_source", cached.get("source", "")),
                         source=snap.source)
            return value, snap
        # 折叠标记可能在屏幕下方；滚到真正可见的展开入口后再做 OCR。
        for _ in range(5):
            if not snap.text("tv_description") and snap.find("tv_job_competitive_title"):
                snap = self.scroll("up", snap=snap)
                continue
            if "查看更多" not in snap.text("tv_description"):
                break
            expanded = self.expand_jd(snap)
            if expanded.text("tv_description") != snap.text("tv_description"):
                snap = expanded
                break
            snap = self.scroll(snap=snap)
        value.update(jd=snap.text("tv_description"), jd_complete=bool(snap.text("tv_description"))
                     and "查看更多" not in snap.text("tv_description"), jd_preview=preview,
                     cache_hit=False, source=snap.source, jd_source=snap.source)
        return value, snap

    def prepare_resume(self, report):
        """中断留在已核对会话时安全返回；陌生会话和草稿交给本人处理。"""
        snap = self.capture("resume-start")
        if snap.state() == "chat":
            matched = [j for j in report["records"] if Device.check_contact(j, snap)]
            if len(matched) != 1:
                raise StopRun("当前聊天无法与批次唯一对应，请本人返回职位列表")
            return self.return_to_results(matched[0], snap)
        return snap

    @staticmethod
    def detail_identity(snap):
        """从岗位详情读取身份，避免把其他岗位的继续沟通当成本次成功。"""
        return dict(title=snap.text("tv_job_name").replace("&@", "").strip(),
                    company=re.split(r"[·•]", snap.text("tv_boss_title"))[0].strip(),
                    hr=snap.text("tv_boss_name"))

    @staticmethod
    def check_contact(job, snap):
        """同时核对身份和沟通证据；仅进入空聊天页不算成功。"""
        if snap.state() == "job":
            return (identity(Device.detail_identity(snap)) == identity(job)
                    and bool(snap.find("btn_continue_chat")))
        if snap.state() != "chat" or normalized(snap.header_text("tv_title")) != normalized(job["hr"]):
            return False
        card = dict(title=snap.text("tv_position_name"), company=snap.text("tv_company_name"), hr=job["hr"])
        if identity(card) != identity(job):
            return False
        if snap.text("tv_contact_time"):
            return True
        # 默认招呼有送达/已读状态时，也可证明已建立沟通；对方消息不作为本人发送依据。
        for node in snap.find("tv_content_text"):
            if not node.get("text", "").strip():
                continue
            row = node
            while row in snap.parents:
                row = snap.parents[row]
                children = list(row.iter("node"))
                avatars = [n for n in children if Snapshot.rid(n) == "iv_avatar"]
                if len(avatars) == 1:
                    left, _, right, _ = Snapshot.bounds(avatars[0])
                    delivered = any(Snapshot.rid(n) == "mMsgTvStatus" and n.get("text") in {"已读", "未读", "送达"}
                                    for n in children)
                    if (left + right) / 2 > snap.width / 2 and delivered:
                        return True
                    break
                if len(avatars) > 1:
                    break
        return False

    def contact_job(self, job, journal):
        """只点击一次立即沟通，不填写消息；超时仅重读核对，不再次点击。"""
        # 1. JD 展开后标题可能离开屏幕，回到详情顶部并重新确认公司、岗位和招聘人。
        snap = self.capture("contact-start")
        for _ in range(6):
            if snap.state() != "job":
                raise StopRun("当前不是岗位详情，未点击立即沟通")
            current = Device.detail_identity(snap)
            if all(current.values()):
                break
            snap = self.scroll("up", snap=snap)
        if identity(Device.detail_identity(snap)) != identity(job):
            raise StopRun("沟通前的岗位身份与刚读取的 JD 不一致")
        if self.check_contact(job, snap):
            journal.record(job, "already_contacted", "当前岗位已显示继续沟通，未重复点击", snap.source)
            return snap
        button = snap.unique(rid="btn_chat", text="立即沟通")
        # 2. 点击本身可能发送平台默认招呼，必须先持久化意图，以免中断后重复触发。
        journal.record(job, "contacting", "即将点击立即沟通", snap.source)
        try:
            try:
                result = self.tap(snap, button)
            except (StopRun, subprocess.TimeoutExpired, OSError):
                result = self.capture("reconcile-contact")
            else:
                if not self.check_contact(job, result):
                    result = self.capture("verify-contact")
            # 3. 核对对应岗位的继续沟通按钮，或匹配会话的建立/送达证据。
            if not self.check_contact(job, result):
                raise StopRun("立即沟通结果无法确认，已停止且不会自动重试")
            journal.record(job, "contacted", "已观察到对应岗位的沟通状态；不代表附件已发或 HR 已回复", result.source)
            return result
        except BaseException as exc:
            journal.record(job, "unknown", "点击后结果待核：" + str(exc))
            raise

    def return_to_results(self, job, snap):
        """从刚核对的会话或岗位返回列表；保留已有草稿，不盲退未知页面。"""
        for _ in range(5):
            state = snap.state()
            if state == "search_results":
                return snap
            if state == "chat":
                if normalized(snap.header_text("tv_title")) != normalized(job["hr"]):
                    raise StopRun("返回前发现聊天对象变化")
                if snap.has_chat_draft():
                    raise StopRun("聊天中有已有草稿，请本人返回；脚本未修改草稿")
                self.call("shell", "input", "keyevent", "4")
                snap = self.after_action("leave-contact", lambda current: current.state() in {"job", "search_results"})
            elif state in {"job", "preference_prompt"}:
                snap = self.back(snap)
            else:
                raise StopRun("沟通后进入未知页面，停止后续岗位")
        raise StopRun("未能返回搜索结果页，停止后续岗位")


class UiautomatorDevice(Device):
    """复用常驻采集服务，裁剪到主屏可用区域；采集故障只读降级，不重放输入。"""

    def __init__(self, serial, output, ocr_helper=DEFAULT_OCR, client=None):
        """延迟启动服务，使参数检查和已完成批次无需启动手机辅助进程。"""
        super().__init__(serial, output, ocr_helper)
        self.backend, self._client, self._disabled = "uiautomator2", client, False
        self.page_timeout = PAGE_WAIT_SECONDS
        # 尺寸仅在一次等待循环内复用，任何独立采集（尤其点击前）都重新读取。
        self._polling, self._poll_viewport = False, None
        self.metrics.update(u2_captures=0, fallbacks=0, u2_start_seconds=0.0,
                            ready_polls=0, ready_wait_seconds=0.0, viewport_queries=0)

    def start(self):
        """只连接明确序列号和专用端口，不修改输入法或 BOSS 配置。"""
        if self._client is None:
            try:
                import uiautomator2 as u2
                from importlib.metadata import version
            except ImportError as exc:
                raise StopRun("当前 Python 未安装 uiautomator2；请使用已配置的独立环境，或 --backend adb") from exc
            start = time.perf_counter()
            self._client = u2.connect_usb(self.serial, port=U2_PORT)
            self.u2_version = version("uiautomator2")
            self.metrics["u2_start_seconds"] += time.perf_counter() - start
            if self._client._process is None:
                raise StopRun("专用端口已有其他服务，未接管其生命周期")

    def close(self):
        """只停止本设备实例创建的辅助服务，保留可复用依赖和 JAR。"""
        client, self._client = self._client, None
        if client is not None:
            client.stop_uiautomator()

    def fill_ascii(self, snap, node, text):
        """只对搜索编辑框整段设置 ASCII，避免输入法把快速逐键输入的光标重置。"""
        if self._disabled:
            return super().fill_ascii(snap, node, text)
        if (snap.state() != "search_input" or Snapshot.rid(node) != "et_search"
                or node.get("class") != "android.widget.EditText"
                or not re.fullmatch(r"[a-zA-Z0-9_ -]{1,80}", text)):
            raise StopRun("只允许向已确认的搜索编辑框填写 ASCII")
        # 1. 只聚焦确认过的搜索框，已是目标词时不再改写。
        current = self.tap(snap, node)
        if current.text("et_search").casefold() == text.casefold():
            return current
        if self._disabled:
            return super().fill_ascii(current, current.unique(rid="et_search"), text)
        self.start()
        # 2. 整段设置后只读核对，不使用聊天输入框或输入法扩展。
        self._client(resourceId=PACKAGE + ":id/et_search").set_text(text, timeout=1)
        return self.after_action("search-typed", lambda result: result.text("et_search").casefold() == text.casefold())

    def refresh_viewport(self):
        """动态取主屏可用尺寸；每次独立采集、轮询开始及旋转变化时刷新。"""
        self.metrics["viewport_queries"] += 1
        display = self.call("shell", "dumpsys", "display").decode("utf-8")
        self._poll_viewport = display_viewport(display)
        return self._poll_viewport

    def capture(self, label="page"):
        """轮询内复用主屏尺寸，旋转时刷新；保存实际参与判定的裁剪快照。"""
        if self._disabled:
            return super().capture(label)
        start = time.perf_counter()
        try:
            # 1. 动态取主屏应用尺寸，避免把底部系统栏计入点击区域。
            width, height, rotation = (self._poll_viewport if self._polling and self._poll_viewport
                                       else self.refresh_viewport())
            self.start()
            # 2. 一次读取并裁剪，未知应用和验证码仍按流程阻断。
            raw = self._client.dump_hierarchy(compressed=False, pretty=False, max_depth=50, root_in_active=True)
            raw_rotation = int(ET.fromstring(raw).get("rotation", rotation))
            if raw_rotation != rotation:
                width, height, rotation = self.refresh_viewport()
            snap = Snapshot(raw, viewport=(width, height))
            if int(snap.root.get("rotation", rotation)) != rotation:
                raise ViewportError("采集期间屏幕方向变化")
        except Exception as exc:
            # 锁屏、验证码和未知应用是流程阻断，不能当成采集故障忽略。
            if isinstance(exc, StopRun) and not isinstance(exc, ViewportError):
                raise
            self.close()
            self._disabled, self.backend = True, "adb-fallback"
            self.metrics["fallbacks"] += 1
            self.fallback_reason = str(exc)
            print(json.dumps(dict(capture_fallback="adb", reason=str(exc)), ensure_ascii=False), flush=True)
            return super().capture(label + "-fallback")
        # 3. 保存实际参与判定的规范化快照，供发送结果追溯。
        self.counter += 1
        path = self.output / "evidence" / f"{time.time_ns()}-{self.counter}-{label}.xml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(ET.tostring(snap.root, encoding="utf-8", xml_declaration=True))
        snap.source = str(path.resolve())
        self.metrics["captures"] += 1
        self.metrics["u2_captures"] += 1
        self.metrics["capture_seconds"] += time.perf_counter() - start
        return snap

    @staticmethod
    def page_ready(snap):
        """等待业务字段出现；详情滚动时不要求屏幕外的标题仍然存在。"""
        state = snap.state()
        if state == "unknown":
            return False
        if state == "job":
            return bool(snap.text("tv_description") or snap.find("tv_job_competitive_title")
                        and snap.find("iv_back") and (snap.find("btn_chat") or snap.find("btn_continue_chat")))
        if state == "chat":
            return all((snap.header_text("tv_title"), snap.text("tv_position_name"), snap.text("tv_company_name")))
        if state == "search_results":
            empty = any(re.search(r"暂无.*职位|没有.*职位|没有更多", n.get("text", "")) for n in snap.nodes)
            return bool(snap.text("tv_search_hint") and (snap.rows() or empty))
        return True

    def after_action(self, label, predicate=None, stable=False):
        """只轮询页面，不重放点击；动作后同时核对目标条件和连续两帧稳定。"""
        if self._disabled:
            return super().after_action(label, predicate, stable)
        # 字段出现时滑入动画可能仍未结束，所有点击及返回都须等布局稳定。
        stable = stable or label in {"after-tap", "after-back", "leave-contact", "expanded", "search-typed"}
        start = time.perf_counter()
        deadline, previous = time.monotonic() + self.page_timeout, None
        self._polling, self._poll_viewport = True, None
        try:
            while True:
                try:
                    snap = self.capture(label)
                    ready = self.page_ready(snap) and (predicate is None or predicate(snap))
                    fingerprint = snap.stability_key() if ready else None
                    if ready and (not stable or (previous == fingerprint and time.perf_counter() - start >= .2)):
                        return snap
                    previous = fingerprint
                except TransientPage:
                    previous = None
                self.metrics["ready_polls"] += 1
                if time.monotonic() >= deadline:
                    raise StopRun(f"页面未在 {self.page_timeout:g} 秒内就绪：{label}；未重复输入")
                time.sleep(.1)
        finally:
            self._polling, self._poll_viewport = False, None
            self.metrics["ready_wait_seconds"] += time.perf_counter() - start


def run_jobs(device, criteria, history, journal, limit, pages, account, output, seen_keys=(), new_batch=False):
    """列表预筛、完整 JD 匹配、单次沟通与核对；中断后按批次目标续跑。"""
    if not 1 <= limit <= MAX_BATCH:
        raise StopRun(f"limit 必须在 1～{MAX_BATCH} 之间")
    path = Path(output) / "results.json"
    report, resumed = open_batch(path, criteria, device.serial, account, limit, journal, new_batch)
    if report["complete"]:
        print("本批目标已完成；没有新增沟通。新批次请显式指定 --new-batch", flush=True)
        return path
    # 历史路径随批次保存，续跑无需重新输入长路径。
    if isinstance(history, History):
        paths = list(dict.fromkeys(report.get("history_paths", []) + history.paths))
        history = History(paths)
        report["history_paths"] = paths
    terminal = {"skipped", "review", "contacted", "already_contacted"}
    seen = set(seen_keys) | {job_key(j) for j in report["records"] if j.get("status") in terminal}
    records = {job_key(j): j for j in report["records"]}
    negative_cache = NegativeCache(Path(output) / "negative-cache.json", criteria, account)
    report.update(state="running", last_started_at=now(), deduplication="company_title",
                  agent_filter_policy="any_agent_keyword")
    if isinstance(device, Device):
        report["capture_backend"] = device.backend
    write_json(path, report)

    def save_record(value):
        """按岗位替换缓存，避免续跑时同一岗位累加多条结果。"""
        key = job_key(value)
        previous = records.get(key)
        if previous is None:
            report["records"].append(value)
        else:
            report["records"][report["records"].index(previous)] = value
        records[key] = value
        report["contacted"] = sum(j.get("status") == "contacted" for j in report["records"])
        report["complete"] = report["contacted"] >= report["target"]
        write_json(path, report)

    run_start = time.perf_counter()
    try:
        # 1. 直接使用 BOSS 城市筛选；恢复已核对的会话后重新进入搜索列表。
        if resumed:
            device.prepare_resume(report)
        with timed(report, "search_seconds"):
            device.search(criteria)
        for bucket in ("10-20K", "20-50K"):
            snap = device.salary_filter(bucket)
            for _ in range(pages):
                while True:
                    if snap.state() != "search_results":
                        raise StopRun("当前不是搜索结果页")
                    fresh = [r for r in snap.rows() if job_key(r) not in seen]
                    if not fresh:
                        break
                    row = fresh[0]
                    key = job_key(row)
                    seen.add(key)
                    # 2. 先用列表字段及历史淘汰明确不符项，避免无效展开 JD。
                    decision = prefilter_job(row, criteria)
                    if history.contains(row) or journal.contains(row):
                        decision = dict(status="skipped", reasons=["已沟通或本地已有尝试，未重复点击"])
                    negative = negative_cache.lookup(row) if decision["status"] == "candidate" else None
                    if negative:
                        decision = dict(status=negative["status"], reasons=negative["reasons"],
                                        negative_cache_hit=True, negative_cache_source=negative["source"],
                                        negative_cache_expires_at=negative["expires_at"])
                    if decision["status"] != "candidate":
                        value = {k: v for k, v in row.items() if k != "node"}
                        value.update(decision, stage="negative_cache" if negative else "list")
                        save_record(value)
                        continue
                    # 3. 完整 JD 缓存先落盘；即使下一步进程退出，重启也无需再做 OCR。
                    cached = records.get(key)
                    try:
                        with timed(report, "read_jd_seconds"):
                            if cached and cached.get("jd_complete"):
                                value, detail = device.read_job(row, snap, cached=cached)
                            else:
                                value, detail = device.read_job(row, snap)
                    except JobIdentityMismatch as exc:
                        # 已知详情页的身份不符只记待核；未知页面、发送结果不明仍停止。
                        value = {k: v for k, v in row.items() if k != "node"}
                        value.update(status="review", stage="identity_review", reasons=[str(exc)],
                                     detail_identity=exc.detail, source=exc.snapshot.source)
                        save_record(value)
                        snap = device.return_to_results(exc.detail, exc.snapshot)
                        continue
                    value.update(status="cached", stage="detail")
                    save_record(value)
                    decision = evaluate_job(value, criteria)
                    negative_cache.remember(value, row, decision)
                    value.update(decision, match_status=decision["status"])
                    if history.contains(value) or journal.contains(value):
                        value.update(status="skipped", reasons=["已沟通或本地已有尝试，未重复点击"])
                    save_record(value)
                    # 4. 点击前保存恢复标记；成功由持久化日志恢复，结果未知不重发。
                    if value["status"] == "ready":
                        value["attempted"] = True
                        save_record(value)
                        try:
                            with timed(report, "contact_verify_seconds"):
                                detail = device.contact_job(value, journal)
                            outcome = journal.latest(value)
                            if not outcome or outcome["status"] not in {"contacted", "already_contacted"}:
                                raise StopRun("未找到已核对的沟通日志")
                            value.update(status=outcome["status"], contact_source=outcome["source"])
                        except BaseException as exc:
                            value.update(status="unknown", error=str(exc))
                            raise
                        finally:
                            save_record(value)
                    progress = {k: value.get(k) for k in ("company", "title", "salary", "status", "reasons", "cache_hit")}
                    progress.update(contacted_total=report["contacted"], target=report["target"])
                    print(json.dumps(progress, ensure_ascii=False), flush=True)
                    # 5. 沿用返回结果页的快照，不再立即重复导出同一页面。
                    snap = device.return_to_results(value, detail)
                    if report["complete"]:
                        report["state"] = "complete"
                        return path
                before = {identity(r) for r in snap.rows()}
                after = device.scroll(snap=snap)
                if before == {identity(r) for r in after.rows()}:
                    break
                snap = after
        report["state"] = "exhausted"
        return path
    except BaseException as exc:
        report.update(state="stopped", stop_reason=str(exc))
        raise
    finally:
        report["finished_at"] = now()
        timings = report.setdefault("timings", {})
        timings["run_seconds"] = round(timings.get("run_seconds", 0) + time.perf_counter() - run_start, 3)
        # 统计独立于判定逻辑，模拟设备不要求实现计时属性。
        if isinstance(device, Device):
            report["capture_backend"] = device.backend
            report["capture_version"] = getattr(device, "u2_version", "")
            if hasattr(device, "fallback_reason"):
                report["capture_fallback_reason"] = device.fallback_reason
            metrics = report.setdefault("device_metrics", {})
            for key, value in device.metrics.items():
                metrics[key] = round(metrics.get(key, 0) + value, 3)
            device.metrics = dict.fromkeys(device.metrics, 0)
        write_json(path, report)


def main():
    """run 一次走完五步；inspect 只查看当前手机页面。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "run"))
    parser.add_argument("--serial", required=True)
    parser.add_argument("--backend", choices=("uiautomator2", "adb"), default="uiautomator2")
    parser.add_argument("--account", default="vivo-current")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--keyword", default="go")
    parser.add_argument("--city", default="深圳")
    parser.add_argument("--salary-min", type=int, default=15)
    parser.add_argument("--salary-max", type=int, default=25)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--new-batch", action="store_true", help="归档当前报告并创建新批次；默认续跑当前批次")
    parser.add_argument("--pages", type=int, default=8)
    parser.add_argument("--history", type=Path, nargs="*", default=[])
    parser.add_argument("--ocr-helper", type=Path, default=DEFAULT_OCR)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", args.account):
        parser.error("account 仅支持英文字母、数字、下划线及短横线")
    if not (10 <= args.salary_min <= args.salary_max <= 50 and 1 <= args.pages <= 30
            and 1 <= args.limit <= MAX_BATCH):
        parser.error("薪资、沟通数量或翻页上限无效")
    output = args.output / args.account
    try:
        device_class = UiautomatorDevice if args.backend == "uiautomator2" else Device
        with device_lock(args.serial), device_class(args.serial, output, args.ocr_helper) as device:
            if args.command == "inspect":
                snap = device.capture("inspect")
                print(json.dumps(dict(state=snap.state(), source=snap.source,
                                      texts=[dict(id=Snapshot.rid(n), text=n.get("text"), bounds=n.get("bounds"))
                                             for n in snap.nodes if n.get("text")]), ensure_ascii=False, indent=2))
            else:
                path = run_jobs(device, Criteria(args.keyword, args.city, args.salary_min, args.salary_max),
                                History(args.history), Journal(output), args.limit, args.pages, args.account, output,
                                new_batch=args.new_batch)
                report = json.loads(path.read_text(encoding="utf-8"))
                print(json.dumps(dict(contacted=report["contacted"], target=report["target"],
                                      state=report["state"],
                                      review=sum(j.get("status") == "review" for j in report["records"])),
                                 ensure_ascii=False))
                print(f"结果：{path.resolve()}")
        return 0
    except (StopRun, subprocess.TimeoutExpired, OSError, ValueError) as exc:
        print(f"已停止：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
