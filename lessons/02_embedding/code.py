"""
Lesson 02 — 深入 Embedding：向量如何表示语义
==============================================
本脚本让你"看见" embedding：
    ① 把一句话变成向量，看看它长什么样
    ② 计算多个句子两两的余弦相似度，打印成矩阵（看相似/无关的差异）
    ③ 用 PCA 把高维向量降到 2D，画散点图（看相似句子聚成一团）

运行：python lessons/02_embedding/code.py
运行后会弹出一个图表窗口，关掉窗口程序才结束。
"""
from __future__ import annotations

import os

import matplotlib.pyplot as plt
import numpy as np
from dotenv import load_dotenv
from sklearn.decomposition import PCA
from zhipuai import ZhipuAI

# 让 matplotlib 支持中文（Windows 上常用字体）
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False  # 负号显示

EMBEDDING_MODEL = "embedding-3"

# ──────────────────────────────────────────────────────────────
# 实验句子：故意分成 3 组语义，方便你观察"同组相似度高、跨组相似度低"。
# 你可以自由增删改这些句子做实验。
# ──────────────────────────────────────────────────────────────
SENTENCES = [
    # 第 1 组：年假/休息（带薪假）
    "入职满一年有 5 天带薪年假。",
    "员工工作满三年可享有 10 天年假。",
    "公司每年提供带薪休假福利。",
    # 第 2 组：报销（钱）
    "差旅住宿一线城市每晚报销上限 500 元。",
    "餐饮发票每人每餐最多报销 80 元。",
    # 第 3 组：远程办公（地点）
    "每周最多可以申请两天居家办公。",
    "试用期员工不允许远程工作。",
    "经批准后可以在家办公。",
    # 第 4 组：无关/其他
    "今天天气晴朗，适合出门散步。",
    "远程办公非常自由，推荐大家多用。",   # 正面
    "远程办公效率低，应该全面禁止。",     # 反面
    "年假5天。",
]
# 给每个句子打一个组标签，方便在图上用颜色区分
GROUP_LABELS = ["年假", "年假", "年假", "报销", "报销", "远程", "远程", "远程", "天气", "远程", "远程", "年假"]
# 每组一个颜色
GROUP_COLORS = {"年假": "red", "报销": "blue", "远程": "green", "天气": "gray"}


def create_zhipu_client() -> ZhipuAI:
    """从 .env 读 Key，创建智谱客户端（和第 1 课一样）。"""
    load_dotenv()
    api_key = os.getenv("ZHIPUAI_API_KEY")
    if not api_key or api_key.startswith("xxxx"):
        raise RuntimeError(
            "还没配置 API Key！请把 .env.example 复制成 .env，填入真实 ZHIPUAI_API_KEY。"
        )
    return ZhipuAI(api_key=api_key)


def embed_texts(client: ZhipuAI, texts: list[str]) -> np.ndarray:
    """把文本变成向量，返回 numpy 数组（形状：[句子数, 维度]）。"""
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    sorted_data = sorted(response.data, key=lambda x: x.index)
    vectors = [item.embedding for item in sorted_data]
    return np.array(vectors)


def cosine_similarity_matrix(vectors: np.ndarray) -> np.ndarray:
    """计算所有向量两两之间的余弦相似度。

    公式：cos(a, b) = (a·b) / (|a| × |b|)
    向量化实现：先归一化（除以各自的长度），再算点积。
    """
    # 每个向量除以它自己的长度 → 变成单位向量（长度=1）
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)  # 每行的向量长度
    normalized = vectors / norms  # 归一化
    # 单位向量之间点积 = 余弦相似度
    return normalized @ normalized.T


def print_vector_preview(client: ZhipuAI):
    """第①部分：看看一句话的向量长什么样。"""
    print("\n" + "─" * 60)
    print("① 向量长什么样？")
    print("─" * 60)
    sample = "入职满一年有 5 天带薪年假。"
    vec = embed_texts(client, [sample])[0]
    print(f"句子：{sample}")
    print(f"向量维度：{len(vec)}")  # embedding-3 默认 2048
    print(f"前 8 个数：{np.round(vec[:8], 4).tolist()}")
    print(f"最大值：{vec.max():.4f}，最小值：{vec.min():.4f}")
    print("→ 你看到的就是：一句话被'压缩'成了 2048 个数字。")
    print("  单独看某个数没意义，但整体位置代表了这句话的语义。")


def print_similarity_matrix(sim_matrix: np.ndarray):
    """第②部分：打印相似度矩阵。"""
    print("\n" + "─" * 60)
    print("② 句子两两的余弦相似度矩阵")
    print("─" * 60)
    print("（对角线是自己和自己比 = 1.0；数值越大越相似）\n")

    # 打印表头（句子编号）
    header = "      " + "  ".join(f"[{i}]" for i in range(len(SENTENCES)))
    print(header)
    for i, row in enumerate(sim_matrix):
        cells = "  ".join(f"{v:.2f}" for v in row)
        print(f"[{i}] {SENTENCES[i][:14]:<16} {cells}")

    print("\n👉 观察重点：")
    print("  - [0][1][2] 都是'年假'，它们之间相似度应该偏高（>0.7）")
    print("  - '年假'和'报销'之间（如 [0]和[3]）相似度应该偏低（<0.6）")
    print("  - 这就是 embedding 能做检索的基础：语义近 → 数值近。")


def plot_visualization(vectors: np.ndarray):
    """第③部分：PCA 降维到 2D，画散点图 + 相似度热力图。"""
    print("\n" + "─" * 60)
    print("③ PCA 降维可视化（即将弹出图表窗口...）")
    print("─" * 60)

    # 把 2048 维降到 2 维（尽量保留原始空间里谁和谁近的关系）
    pca = PCA(n_components=2)
    coords_2d = pca.fit_transform(vectors)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # ---- 左图：2D 散点图 ----
    ax = axes[0]
    for i, (x, y) in enumerate(coords_2d):
        group = GROUP_LABELS[i]
        color = GROUP_COLORS[group]
        ax.scatter(x, y, c=color, s=120, zorder=3)
        # 标注句子编号
        ax.annotate(
            f"{i}: {SENTENCES[i][:8]}",
            (x, y),
            textcoords="offset points",
            xytext=(8, 6),
            fontsize=9,
        )
    ax.set_title("句子向量降维到 2D（相似句子应该聚成一团）")
    ax.set_xlabel("主成分 1")
    ax.set_ylabel("主成分 2")
    ax.grid(True, alpha=0.3)
    # 图例
    from matplotlib.patches import Patch

    legend = [Patch(color=c, label=g) for g, c in GROUP_COLORS.items()]
    ax.legend(handles=legend, title="语义组")

    # ---- 右图：相似度热力图 ----
    ax2 = axes[1]
    sim = cosine_similarity_matrix(vectors)
    im = ax2.imshow(sim, cmap="YlOrRd", vmin=0.3, vmax=1.0)
    ax2.set_title("余弦相似度热力图（越红越相似）")
    ax2.set_xticks(range(len(SENTENCES)))
    ax2.set_yticks(range(len(SENTENCES)))
    ax2.set_xticklabels(range(len(SENTENCES)))
    ax2.set_yticklabels(range(len(SENTENCES)))
    # 在格子里写数值
    for i in range(len(SENTENCES)):
        for j in range(len(SENTENCES)):
            ax2.text(
                j, i, f"{sim[i][j]:.2f}", ha="center", va="center", fontsize=8
            )
    fig.colorbar(im, ax=ax2, fraction=0.046)

    plt.tight_layout()
    print("📊 图表已生成。关掉图表窗口程序才会结束。")
    print("👉 左图：相似的句子（同色）应该挨得近；右图：对角线附近应该偏红。")
    plt.show()


def main():
    print("=" * 60)
    print("Lesson 02 — 深入 Embedding：向量如何表示语义")
    print("=" * 60)

    client = create_zhipu_client()

    # ① 看向量样例
    print_vector_preview(client)

    # 把所有句子向量化（供后面②③用）
    print("\n正在向量化所有句子...")
    vectors = embed_texts(client, SENTENCES)
    print(f"✅ {len(SENTENCES)} 个句子 → {vectors.shape[0]}×{vectors.shape[1]} 矩阵")

    # ② 相似度矩阵
    sim_matrix = cosine_similarity_matrix(vectors)
    print_similarity_matrix(sim_matrix)

    # ③ 可视化
    plot_visualization(vectors)

    print("\n" + "=" * 60)
    print("完成！如果散点图里同色点聚成一团，说明 embedding 成功捕捉了语义。")
    print("=" * 60)


if __name__ == "__main__":
    main()
