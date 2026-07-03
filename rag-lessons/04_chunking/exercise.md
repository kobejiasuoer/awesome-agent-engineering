# Lesson 04 练习

> 改 `code.py` 里的代码，运行 `python lessons/04_chunking/code.py` 观察变化。
> 本课不调用 API，纯本地切分，随便试不花钱。

---

## 练习 1：故意切出"语义断裂"
把 `section_compare_chunk_sizes` 里的 separators 改成**只有空字符**：

```python
separators=["",]
```

这等于"纯按字符数硬切，不看任何语义边界"。用 chunk_size=100 跑。

**观察**：你会看到块从句子中间被劈断，比如 `"员工入职满 1 年可享"` 和 `"有 5 天带薪年假"` 分成两块。

**思考**：这种切法会让检索出现什么问题？（提示：检索到 `"员工入职满 1 年可享"` 这块时，模型拿不到"5 天"这个关键信息）

---

## 练习 2：找一份你自己的文档
把你自己的一个 Markdown 或 txt 文档放进 `data/sample_docs/`，改 `DOC_PATH` 指向它。

试着调整 `chunk_size` 和 `chunk_overlap`，**找到一份你觉得"切得最合理"的配置**。

判断标准：
- 每块是一个完整的语义单元（不是半句话）
- 每块不要混太多主题
- 关键信息没被切断

**思考**：不同类型的文档（规章制度 / 技术文档 / 小说），最佳 chunk_size 一样吗？为什么？

---

## 练习 3：观察 overlap 的作用
在 `section_recursive_with_overlap` 里，把 `chunk_overlap` 从 80 改成 **0**，再跑一次。

找一个跨块的关键信息（比如"年假天数"那句话），看它在 overlap=0 时有没有被切断，overlap=80 时是不是被两边都兜住了。

**思考**：overlap 越大越好吗？overlap=200 会有什么副作用？（提示：冗余、块数变多、存储检索开销增大）

---

## 练习 4：用切块结果做一次完整检索（综合练习）
把第 ④ 部分切出来的 chunks，用第 3 课学的 Chroma 检索一次。在 `main()` 末尾加：

```python
# 需要导入前面课程的工具，这里给个框架
import chromadb
from zhipuai import ZhipuAI
# ...（向量化 + 存 Chroma + 检索）
```

用问题 `"年假有几天？"` 检索，看切好的块能不能精准召回"年假"那段。

**思考**：对比"整篇文档向量化"和"切块后向量化"的检索效果——切块后检索是不是精准多了？这就是 chunking 的价值。

---

## ✅ 完成本课后，你应该能回答
1. 为什么不能把整篇文档直接向量化存进向量库？（三个原因）
2. chunk_size 太大和太小各有什么问题？经验值是多少？
3. chunk_overlap 解决什么问题？为什么不能设太大？
4. RecursiveCharacterTextSplitter 的 separators 优先级是怎么工作的？
5. 为什么说"一个 chunk = 一个语义单元"是检索精准的基础？
