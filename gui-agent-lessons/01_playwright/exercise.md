# L01 练习

## 练习 1：iframe 嵌套页的处理（方法练习）

L01 的测试页都是顶层页面。真实网站常用 iframe 嵌入内容（如嵌入式文档、第三方组件），Playwright 默认不进 iframe 找元素。请：

1. 新增 `test_pages/iframe.html`，内含一个 `<iframe src="detail.html">`。
2. 用 BrowserSession 演示「先 `frame_locator` 进 iframe，再提取 #ver」。
3. 写下踩坑笔记：直接 `s.extract_text("#ver")` 会发生什么？为什么？

**验收**：能从 iframe 内提取到版本号，笔记说清「Playwright 的 frame 边界——元素选择器默认不跨 frame」。

<details>
<summary>提示：frame_locator 用法</summary>

```python
# 进 iframe 再找元素
frame = s.page.frame_locator("iframe")
ver = frame.locator("#ver").inner_text()
```
</details>

---

## 练习 2：量化对比 auto-wait vs sleep（设计实验类）

本课主张「auto-wait 优先，别手写 sleep」。用实验量化这个主张：

1. **假设**：`sleep(2)` 比 `wait_for_selector` 慢且脆——快机器白等、慢机器不够。
2. **实验设计**：
   - 改 `slow.html` 的延迟为可配置（URL 参数 `?delay=3000` 让 JS 延迟 3s）。
   - 在 `code.py` 写两个版本：A 用 `time.sleep(2)` 后 `inner_text`；B 用 `wait_for_selector`。
   - 跑 delay=1000/2000/3000 三档，记录：A 是否拿到（sleep<delay 会失败）、B 的实际等待时间。
3. **预期**：delay=3000 时 A 失败（sleep 2s 不够），B 总是成功且等待≈delay。

**验收**：输出三档对照表，A 在 delay>sleep 时失败，B 全绿。诚实标注这是本地实测数字。

---

## 练习 3：资源泄漏验证（理解类）

本课强调上下文管理器保证 `close()`。设计一个验证：

1. 在 `with BrowserSession()` 块内**故意抛异常**（如 `raise ValueError("test")`）。
2. 用 `tasklist`（Windows）或 `ps` 检查脚本退出后还有没有 `chrome`/`chromium` 进程残留。
3. 对比：把 `with` 换成手动 `s = BrowserSession(); s.__enter__()`（不调 `__exit__`），同样抛异常，看进程残留。

**验收**：能说出「with 块异常时 `__exit__` 仍被调用 → 无残留；手动管理 + 异常 → chromium 进程泄漏」。这解释了为什么上下文管理器不是语法糖而是可靠性必需。

---

## 练习 4：思考题——auto-wait 的边界（取舍类）

auto-wait 不是万能的。回答：

1. auto-wait 等的是「元素可交互」，但「元素可交互」≠「元素已加载完内容」。举一个 auto-wait 通过但内容还没好的场景（提示：异步填充数据的表格）。
2. 这种场景该用哪种等待？为什么 auto-wait 在这里失灵？
3. 这和 L00 讲的「确定性选择器 vs has-text 歧义」是不是同一类问题——都是「自动化对页面状态的假设」？

**验收**：能举出 auto-wait 失灵的具体场景并给出正确的显式等待写法（如 `wait_for_function` 检查表格行数 > 0），并点出这是「状态假设」问题的又一表现。
