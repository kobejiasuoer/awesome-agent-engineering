# Lesson 01 — Playwright 地基：确定性浏览器控制

> 本课目标：**在零 LLM 前提下把浏览器控制层写稳——封装一个 `BrowserSession`（goto/click/type/screenshot/extract_text/超时兜底/自动关闭），在慢加载页和弹窗页上全部跑通。agent 的手必须先稳，脑再聪明才有意义。**

学完你能回答：**「不靠 LLM，怎么把浏览器自动化写得不脆？」**——答案是 auto-wait + 显式等待 + 超时兜底 + 资源自动释放 + 确定性选择器。

---

## 0. 为什么先写「无脑的手」

L00 证明了浏览器能拿到搜索 API 拿不到的东西，但那段脚本是**写死的**——每一步的选择器、每一步的等待都硬编码。L01 要把它泛化成可复用的原语（`goto`/`click`/`type`/`extract`），但在泛化之前，得先回答一个更基础的问题：**浏览器自动化为什么脆？**

```
GUI 自动化的脆，根源是四类时序竞争：
  ① 动态渲染：关键内容 JS 延迟生成，DOM 里一开始没有（L01 的 slow.html）
  ② 弹窗劫持：遮罩盖住正文，不处理弹窗点不到下面的元素（L01 的 popup.html）
  ③ 导航时序：点击触发的整页跳转，旧 DOM 还在、新 DOM 没来
  ④ 元素选择歧义：a:has-text("2") 同时匹配分页器和结果文本（L00 踩过的坑）
```

> 🎯 **核心认知**：这些脆性**与 LLM 无关**——是浏览器自动化本身的问题。如果手不稳，agent 每次想点击都飘，那它的「脑」再聪明也白搭。所以本课严格零 LLM：先把控制层写到确定性可复现，再谈智能。

---

## 1. 流派对比：浏览器自动化框架

| 框架 | 取舍 |
|---|---|
| ① **Selenium** | 老、生态成熟；🚫 API 繁、auto-wait 弱、异步支持差、驱动版本管理烦 |
| ② **Playwright（本课选它）** | ✅ auto-wait 内置（点之前自动等元素可交互）、多浏览器、原生 async、CDP 直连快、trace viewer 调试强；🚫 生态比 Selenium 略小 |
| ③ **CDP 裸协议** | ✅ 最底层最灵活；🚫 太底层，光建连接就一堆样板，教学不划算 |
| ④ **browser-use 等现成 agent 框架** | ✅ 上层封装好直接出 agent；🚫 黑盒，失去对观察/行动/安全层的控制（任务书明确只作对比不作依赖） |

**选 Playwright 的理由**：auto-wait 是治「时序竞争」的解药——`click` 之前自动等元素 visible+enabled+stable，省掉一堆手写 `sleep`。原生 async 让 L09 落地 research-assistant（本身是 async 图）时无缝接。CDP 直连性能好（视觉路线 L05 截图频繁，省 ms 累积成钱）。

### 安装（任务书硬约束的国内镜像）

```bash
pip install playwright -i https://pypi.tuna.tsinghua.edu.cn/simple
# 浏览器二进制用国内镜像（只装 chromium，省空间）：
PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright \
  python -m playwright install chromium
```

---

## 2. auto-wait 与显式等待策略

Playwright 的等待分两层，理解它们的分工是写稳自动化的关键：

| 等待类型 | 触发方式 | 等什么 | 用在哪 |
|---|---|---|---|
| **auto-wait** | `click`/`fill` 等动作内置 | 元素 visible + enabled + stable + 可接收事件 | 大多数点击/输入，无需手写 |
| **显式等待** | `wait_for_selector`/`wait_for_url`/`wait_for_function` | 自定义条件 | 动态渲染（slow.html）/ 导航落定（L00 翻页）/ 弹窗关闭 |

**原则**：能用 auto-wait 就别手写 `sleep`（`sleep(2)` 是脆性的源头——机器快了浪费、机器慢了不够）。但动态渲染的内容 auto-wait 管不到（元素还没生成），这时用 `wait_for_selector("#ver")` 显式等。

```
慢加载页 slow.html 的关键内容延迟 1.5s 出现：
  ❌ time.sleep(2)            # 脆：快机器白等，慢机器不够
  ❌ page.inner_text("#ver")  # auto-wait 也救不了：元素压根没生成，直接抛
  ✅ page.wait_for_selector("#ver", timeout=5000)
     page.inner_text("#ver")  # 等 1.5s 后元素出现，再读
```

### 导航时序的坑

点击 `<a href>` 触发整页跳转时，点击返回时新页面可能还没加载完。两种稳法：

- `page.wait_for_url("**page=2**", wait_until="domcontentloaded")`——等 URL 落定
- `with page.expect_navigation(): page.click(...)`——点击与导航原子绑定

> 💡 `wait_until="domcontentloaded"` 比 `"load"` 更可靠——本地 `http.server` 不总触发 `load` 事件（缺 Content-Length 等），`domcontentloaded` 只要 DOM 解析完就放行，够用且不卡。

---

## 3. headless / headed 与可复现性

| 模式 | 用途 |
|---|---|
| `headless=True` | 测试/基准/CI——快、不弹窗、可并行；本课默认 |
| `headless=False` | 调试——肉眼看 agent 点哪了；本地排错用 |

**可复现性硬约束**（任务书 1.3）：viewport 固定尺寸（`1280×800`），保证截图和布局在每台机器一致——这直接影响 L05 视觉路线的 SoM 标注坐标稳定。headless 时 viewport 由 `new_page(viewport=...)` 控制；headed 时窗口大小不等于 viewport，会漂。

---

## 4. Windows 异步坑：ProactorEventLoop

任务书点名的「著名深坑」：Playwright async API 在 Windows 上需要 **ProactorEventLoop**。

```python
# Windows 上 asyncio 默认就是 ProactorEventLoop（Python 3.8+）
# ⚠️ 切勿手动改成 SelectorEventLoop！
#   错误写法：asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
#   后果：Playwright async 子进程通信挂死，某些 asyncio 库（如旧 aiodns）混用也炸。
# 正确：什么都不设，让默认 ProactorEventLoop 生效。
```

> 🎯 为什么单独拎出来：research-assistant 是 LangGraph async 图（L09 要把 browser 接进去），全链路 asyncio。如果在 Windows 上手贱设成 Selector，整个图会卡在 browser 调用上不动——这种 bug 不报错只挂死，极难查。本课 sync API 教学不受影响，但 README 必须写明，L09 落地时照此执行。

---

## 5. `BrowserSession` 设计

本课核心产出——一个把 Playwright sync API 封装成可复用原语的类：

| 原语 | 作用 | 关键设计 |
|---|---|---|
| `goto(url)` | 打开页面 | `wait_until="domcontentloaded"` |
| `click(selector)` | 点击 | auto-wait + 超时兜底 |
| `type(selector, text)` | 输入 | auto-wait |
| `screenshot(path)` | 截图 | L05 视觉路线用，降采样宽≤1280 |
| `extract_text(selector)` | 提取文本 | 显式 `wait_for_selector` 兜动态渲染 |
| `close()` | 关闭 | 上下文管理器 `__exit__` 自动调，防资源泄漏 |

**超时兜底**（可靠性主线预热）：每个动作有 `timeout`，超时不崩——返回结构化错误或抛可控异常，让上层（L04 agent 循环）能决定重试还是换策略。

**上下文管理器**（`with BrowserSession() as s:`）：保证即使中途异常，浏览器进程也一定被 `close()`——否则 chromium 进程泄漏，跑几次基准内存就爆。

> 🎯 这套原语就是 L00 写死脚本的泛化版。L02 在它之上加观察空间提取，L03 加动作 DSL 执行器，L04 装进 agent 循环——每一层都建立在「手稳」之上。

---

## 6. 落地清单

本课是地基课，**无 research-assistant 代码改动**（落地在 L09）。产出：

| 文件 | 说明 |
|---|---|
| `README.md`（本文件） | 框架对比 + 等待策略 + Windows 坑 + BrowserSession 设计 |
| `code.py` | `BrowserSession` 实现 + 在 slow/popup/L00 三个页上演示 |
| `test_pages/slow.html` | 慢加载页（动态渲染） |
| `test_pages/popup.html` | 弹窗劫持页 |
| `exercise.md` | 练习 |

### 起本地服务（同时服务 L00 和 L01 的测试页）

```bash
# L00 的 test_pages 起在 8765
cd gui-agent-lessons/00_overview/test_pages && python -m http.server 8765 &

# L01 的 test_pages 起在 8766
cd gui-agent-lessons/01_playwright/test_pages && python -m http.server 8766
```

### 验收

```bash
cd gui-agent-lessons/01_playwright

# 跑 BrowserSession 演示（需先起上述两个本地服务 + playwright/chromium）
python code.py

# 预期输出：
#  - slow.html：等 1.5s 后正确提取 v0.9.9 / 2024-09-20（动态渲染处理 ✅）
#  - popup.html：点「同意」关遮罩后提取 v0.7.7（弹窗处理 ✅）
#  - L00 search.html：goto→type→click→翻页→extract 全绿（确定性操作 ✅）
#  - 资源释放：脚本退出无残留 chromium 进程（上下文管理器 ✅）
```

> ⚠️ 若本地服务未起或 playwright 未装，`code.py` 会跳过对应演示并打印提示，不阻塞。

---

## 7. 本课在两条主线上的位置

- **评估主线**：本课不直接产指标，但为评估奠基——L08 mini-benchmark 和 L11 收益表的所有「成功率」都建立在 `BrowserSession` 的确定性之上。手不稳，成功率数字就是噪音。本课的验收（三个页面全绿）是评估主线可信度的前提。
- **观察-行动接口主线**：本课只搭**行动的物理底座**（goto/click/type 是行动的执行层），还没设计行动的**语义层**（DSL 在 L03）和观察空间（L02）。但「确定性选择器」「超时兜底」这些工程决策，直接约束了 L03 DSL 的设计——`click(3)` 能不能可靠执行，取决于这里的 `click(selector)` 稳不稳。

---

## 🎯 面试话术

> 「我做 GUI agent 先把无 LLM 的控制层写稳——封装 BrowserSession，auto-wait 加显式等待治时序竞争，超时兜底不崩，上下文管理器保证资源释放。慢加载页和弹窗页是我专门造的刁难场景，都能确定性通过。手不稳脑再聪明也白搭——这是我在 Windows ProactorEventLoop 坑上也踩过才认的死理。」
