# L05 练习

> 改 `code.py` 里的代码，运行 `python agent-lessons/05_memory/code.py` 观察变化。

---

## 练习 1：体验多轮对话的记忆
把 `main()` 里的实验改成**交互式**，自己和 Agent 聊天：

```python
def interactive_mode(client):
    messages = [{"role": "system", "content": "你是友好的助手。"}]
    print("输入问题聊天，输 exit 退出。")
    while True:
        user = input("🙋 ").strip()
        if user.lower() in ("exit", "quit"): break
        messages.append({"role": "user", "content": user})
        reply = chat(client, messages)
        print(f"🤖 {reply}")
        messages.append({"role": "assistant", "content": reply})

# 在 main() 里调用
interactive_mode(client)
```

先告诉它"我叫XX，我喜欢XX"，聊几轮别的，再问它"我叫什么"。

**思考**：Agent 能记住是因为什么？（提示：每次调用 chat 都传了完整 messages）。如果把 `messages.append(...)` 那两行删掉，会发生什么？

---

## 练习 2：调截断窗口大小，观察"记忆边界"
在 `demo_forgetting` 里，把 `keep_last` 从 4 逐步调大到 6、8、10，每次问"我叫什么名字"。

**观察**：
- keep_last=4：可能失忆（"我叫李四"被截掉）
- keep_last=8：可能记起来了（保留了早期消息）

**思考**：这让你直观看到"截断窗口"的边界——keep_last 多大才够？这取决于对话里重要信息出现的位置。有没有"动态判断该保留哪些"的更好方法？（引出摘要的价值）

---

## 练习 3：改进摘要策略
当前的 `summarize_history` 每次压缩都会调一次模型（成本）。一个优化是：**不要每轮都压缩，而是当消息超过阈值时才压缩一次**。

试着实现"阈值触发压缩"：

```python
class MemoryManager:
    def __init__(self, threshold=10, keep_recent=4):
        self.threshold = threshold  # 超过这个数才压缩
        self.keep_recent = keep_recent

    def manage(self, client, messages):
        other = [m for m in messages if m["role"] != "system"]
        if len(other) > self.threshold:
            return compress_with_summary(client, messages, self.keep_recent)
        return messages  # 没超阈值，不压缩
```

**思考**：这种"按需压缩"比"每轮压缩"省成本。真实产品（如 ChatGPT）的长对话管理就是这种思路的复杂版。

---

## 练习 4：实现长期记忆（用 RAG 思路）
回顾 RAG 课程。试着把每次对话存进一个文件，新会话开始时检索相关历史：

```python
import chromadb

# 1. 每轮对话结束后存进 Chroma
collection.add(documents=[用户说的], ids=[...])

# 2. 新会话开始，用当前问题检索相关历史
results = collection.query(query_embeddings=[...], n_results=3)

# 3. 把检索到的历史作为上下文
messages = [{"role": "system", "content": f"用户之前提过：{results}"}]
```

**思考**：这就是长期记忆的本质——**对对话历史做 RAG**。你已经具备全部知识来实现它。这能不能直接用在你 RAG 课毕业作品（Lesson 09）的代码上？

---

## ✅ 完成本课后，你应该能回答
1. 大模型本身有记忆吗？所谓的"记住对话"是怎么实现的？
2. 上下文窗口限制是什么？为什么记忆不能无限长？
3. 三种窗口管理策略各有什么优缺点？
4. 截断策略为什么会"失忆"？摘要策略怎么缓解？
5. 长期记忆和短期记忆的区别？长期记忆本质是什么？（提示：RAG）
