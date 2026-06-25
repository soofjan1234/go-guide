"""Generate Kubernetes Excalidraw diagrams for Guide/运维."""
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "Guide" / "content" / "其它" / "运维" / "pic"


def seed(element_id: str) -> int:
    return int(hashlib.sha1(element_id.encode("utf-8")).hexdigest()[:8], 16)


def _common(element_id, kind, x, y, w, h, stroke="#1e40af", fill="#a5d8ff"):
    return {
        "id": element_id,
        "type": kind,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "angle": 0,
        "strokeColor": stroke,
        "backgroundColor": fill,
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roughness": 1,
        "opacity": 100,
        "groupIds": [],
        "roundness": {"type": 3},
        "seed": seed(element_id),
        "version": 1,
        "isDeleted": False,
        "boundElements": None,
        "updated": 1,
        "link": None,
        "locked": False,
    }


def rect(element_id, x, y, w, h, fill="#a5d8ff", stroke="#1e40af", dashed=False, opacity=100):
    r = _common(element_id, "rectangle", x, y, w, h, stroke=stroke, fill=fill)
    r["opacity"] = opacity
    if dashed:
        r["strokeStyle"] = "dashed"
    return r


def text(element_id, x, y, content, size=18, stroke="#374151", w=None, h=None, align="center"):
    lines = content.split("\n")
    longest = max((len(line) for line in lines), default=1)
    tw = w if w else max(80, longest * size * 0.92)
    th = h if h else max(28, len(lines) * size * 1.35)
    base = _common(element_id, "text", x, y, tw, th, stroke=stroke, fill="transparent")
    base.update(
        {
            "backgroundColor": "transparent",
            "text": content,
            "fontSize": size,
            "fontFamily": 5,
            "textAlign": align,
            "verticalAlign": "middle",
            "containerId": None,
            "originalText": content,
            "autoResize": True,
            "lineHeight": 1.25,
        }
    )
    return base


def arrow(element_id, x, y, points, stroke="#3b82f6", dashed=False):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    base = _common(
        element_id,
        "arrow",
        x,
        y,
        max(1, max(xs) - min(xs)),
        max(1, max(ys) - min(ys)),
        stroke=stroke,
        fill="transparent",
    )
    base.update(
        {
            "points": points,
            "lastCommittedPoint": points[-1],
            "startBinding": None,
            "endBinding": None,
            "startArrowhead": None,
            "endArrowhead": "arrow",
            "backgroundColor": "transparent",
            "roundness": {"type": 2},
            "elbowed": False,
        }
    )
    if dashed:
        base["strokeStyle"] = "dashed"
    return base


def label_box(e, prefix, x, y, w, h, title, subtitle, fill, stroke, title_size=18):
    e.append(rect(prefix, x, y, w, h, fill, stroke))
    e.append(text(f"{prefix}_title", x + 10, y + 14, title, title_size, stroke, w=w - 20))
    if subtitle:
        e.append(text(f"{prefix}_sub", x + 10, y + 42, subtitle, 15, "#374151", w=w - 20))


def scene(elements):
    return {
        "type": "excalidraw",
        "version": 2,
        "source": "https://github.com/zsviczian/obsidian-excalidraw-plugin",
        "elements": elements,
        "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
        "files": {},
    }


def wrap_md(scene_json):
    return (
        """---
excalidraw-plugin: parsed
tags: [excalidraw]
---
==⚠  Switch to EXCALIDRAW VIEW in the MORE OPTIONS menu of this document. ⚠== You can decompress Drawing data with the command palette: 'Decompress current Excalidraw file'. For more info check in plugin settings under 'Saving'

# Excalidraw Data

## Text Elements
%%
## Drawing
```json
"""
        + json.dumps(scene_json, ensure_ascii=False, indent=2)
        + """
```
%%
"""
    )


def k8s_architecture_scene():
    e = []
    e.append(text("title", 360, 24, "K8s 集群架构：控制平面 vs 工作节点", 24, "#1e40af"))

    e.append(rect("cp_zone", 60, 78, 1080, 250, "#dbe4ff", "#3b82f6", opacity=30))
    e.append(text("cp_label", 88, 92, "控制平面「做决策」", 20, "#1e40af", align="left"))

    label_box(
        e,
        "api",
        470,
        118,
        260,
        88,
        "API Server",
        "集群统一入口\nkubectl / 控制器都走它",
        "#a5d8ff",
        "#1e40af",
        20,
    )
    label_box(e, "etcd", 120, 168, 200, 88, "etcd", "保存集群状态\n与配置", "#c3fae8", "#0f766e")
    label_box(e, "sched", 820, 118, 200, 88, "Scheduler", "决定 Pod\n调度到哪台节点", "#fff3bf", "#b45309")
    label_box(
        e,
        "cm",
        820,
        218,
        200,
        88,
        "Controller Manager",
        "对比期望 vs 实际\n推动状态收敛",
        "#d0bfff",
        "#6d28d9",
    )

    e.append(rect("user", 60, 118, 120, 56, "#ffd8a8", "#c2410c"))
    e.append(text("user_t", 82, 132, "kubectl\n用户", 16, "#9a3412"))

    e.append(arrow("a_user_api", 180, 152, [[0, 0], [280, 0]], "#c2410c"))
    e.append(arrow("a_api_etcd", 470, 186, [[0, 0], [-150, 0]], "#0f766e"))
    e.append(arrow("a_api_sched", 730, 152, [[0, 0], [90, 0]], "#b45309"))
    e.append(arrow("a_api_cm", 700, 210, [[0, 0], [120, 8]], "#6d28d9", dashed=True))
    e.append(arrow("a_sched_node", 920, 206, [[0, 0], [0, 130]], "#b45309"))

    def worker_node(prefix, x, title_y=360):
        e.append(rect(f"{prefix}_zone", x, 350, 500, 250, "#d3f9d8", "#15803d", opacity=30))
        e.append(text(f"{prefix}_label", x + 18, title_y - 18, "工作节点「跑业务」", 18, "#15803d", align="left"))
        label_box(e, f"{prefix}_kubelet", x + 24, title_y + 18, 140, 72, "kubelet", "管理本机 Pod", "#b2f2bb", "#15803d")
        label_box(e, f"{prefix}_proxy", x + 180, title_y + 18, 140, 72, "kube-proxy", "Service\n网络转发", "#b2f2bb", "#15803d")
        label_box(
            e,
            f"{prefix}_runtime",
            x + 336,
            title_y + 18,
            140,
            72,
            "Container Runtime",
            "containerd\n真正跑容器",
            "#b2f2bb",
            "#15803d",
        )
        e.append(rect(f"{prefix}_pod1", x + 70, title_y + 118, 95, 58, "#ffffff", "#15803d"))
        e.append(text(f"{prefix}_pod1_t", x + 88, title_y + 132, "Pod", 16, "#15803d"))
        e.append(rect(f"{prefix}_pod2", x + 185, title_y + 118, 95, 58, "#ffffff", "#15803d"))
        e.append(text(f"{prefix}_pod2_t", x + 203, title_y + 132, "Pod", 16, "#15803d"))
        e.append(arrow(f"a_{prefix}_k_pod", x + 94, title_y + 90, [[0, 0], [0, 28]], "#15803d"))
        e.append(arrow(f"a_{prefix}_r_pod", x + 406, title_y + 90, [[0, 0], [-126, 28]], "#15803d", dashed=True))

    worker_node("n1", 60)
    worker_node("n2", 640)

    e.append(arrow("a_api_n1", 600, 206, [[0, 0], [-200, 190]], "#1e40af"))
    e.append(arrow("a_api_n2", 600, 206, [[0, 0], [180, 190]], "#1e40af"))
    e.append(text("flow_note", 60, 620, "调度链路：API Server → Scheduler 选节点 → kubelet 拉起 Pod → Runtime 运行容器", 16, "#374151", w=1080, align="left"))
    return scene(e)


def k8s_resources_scene():
    e = []
    e.append(text("title", 310, 22, "K8s 常见资源对象与关系", 24, "#1e40af"))

    e.append(rect("ext_zone", 60, 78, 1080, 110, "#dbe4ff", "#3b82f6", opacity=30))
    e.append(text("ext_label", 82, 92, "外部流量入口", 18, "#1e40af", align="left"))
    label_box(e, "ingress", 470, 108, 260, 68, "Ingress", "HTTP/HTTPS 外部入口", "#a5d8ff", "#1e40af")

    label_box(e, "svc", 470, 220, 260, 78, "Service", "稳定访问入口\nClusterIP / NodePort", "#d0bfff", "#6d28d9")
    label_box(e, "deploy", 120, 330, 220, 88, "Deployment", "管理无状态应用\n副本数 / 滚动更新 / 回滚", "#fff3bf", "#b45309")

    e.append(rect("pod_zone", 430, 340, 340, 150, "#b2f2bb", "#15803d", opacity=35))
    e.append(text("pod_zone_t", 540, 352, "Pod「最小调度单位」", 17, "#15803d"))
    e.append(rect("pod1", 455, 390, 130, 78, "#ffffff", "#15803d"))
    e.append(text("pod1_t", 472, 404, "Pod\n容器 A + B", 16, "#15803d"))
    e.append(rect("pod2", 615, 390, 130, 78, "#ffffff", "#15803d"))
    e.append(text("pod2_t", 640, 404, "Pod\n副本", 16, "#15803d"))

    label_box(e, "cm", 820, 330, 150, 72, "ConfigMap", "普通配置", "#c3fae8", "#0f766e")
    label_box(e, "secret", 990, 330, 150, 72, "Secret", "密码 / Token", "#ffc9c9", "#b91c1c")
    label_box(e, "pv", 820, 430, 150, 72, "PV / PVC", "持久化存储", "#c3fae8", "#0f766e")
    label_box(e, "runtime", 990, 430, 150, 72, "Runtime", "containerd", "#b2f2bb", "#15803d")

    e.append(arrow("a_ing_svc", 600, 176, [[0, 0], [0, 44]], "#1e40af"))
    e.append(arrow("a_svc_pod", 600, 298, [[0, 0], [0, 42]], "#6d28d9"))
    e.append(arrow("a_dep_pod1", 340, 374, [[0, 0], [115, 36]], "#b45309"))
    e.append(arrow("a_dep_pod2", 340, 374, [[0, 0], [275, 36]], "#b45309"))
    e.append(text("dep_note", 125, 430, "管理副本", 15, "#b45309", align="left"))

    e.append(arrow("a_cm_pod", 820, 366, [[0, 0], [-130, 50]], "#0f766e", dashed=True))
    e.append(arrow("a_sec_pod", 990, 366, [[0, 0], [-300, 50]], "#b91c1c", dashed=True))
    e.append(arrow("a_pv_pod", 895, 430, [[0, 0], [-220, 20]], "#0f766e", dashed=True))
    e.append(text("mount_note", 835, 510, "挂载进 Pod", 15, "#374151", align="left"))

    e.append(rect("legend", 60, 530, 1080, 120, "#f8fafc", "#64748b"))
    e.append(text("legend_h", 82, 544, "对象职责速记", 18, "#334155", align="left"))
    e.append(
        text(
            "legend_body",
            82,
            575,
            "Pod：最小调度单位，可含多个容器\n"
            "Deployment：声明期望副本数，负责创建/更新 Pod\n"
            "Service：给一组 Pod 固定虚拟 IP，做服务发现\n"
            "Ingress：七层路由，把外部域名流量转到 Service\n"
            "ConfigMap / Secret：配置与敏感信息，注入 Pod\n"
            "PV：集群级存储资源，PVC 申请后挂载给 Pod",
            16,
            "#374151",
            w=1020,
            align="left",
        )
    )
    return scene(e)


def write(name: str, scene_json):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(wrap_md(scene_json), encoding="utf-8")


def main():
    write("k8s架构.md", k8s_architecture_scene())
    write("k8s资源对象.md", k8s_resources_scene())
    print(f"Wrote diagrams to {OUT}")


if __name__ == "__main__":
    main()
