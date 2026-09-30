
### 示例：并发网络请求（使用 `aiohttp`）

```python
# async_http_demo.py
import asyncio
import aiohttp

async def fetch(session: aiohttp.ClientSession, url: str) -> str:
    """获取 URL 内容并返回长度"""
    async with session.get(url) as resp:
        text = await resp.text()
        return f"{url} -> {len(text)} bytes"

async def main():
    urls = [
        "https://www.python.org",
        "https://www.wikipedia.org",
        "https://www.github.com",
    ]

    async with aiohttp.ClientSession() as session:
        tasks = [asyncio.create_task(fetch(session, url)) for url in urls]
        results = await asyncio.gather(*tasks)

    for r in results:
        print(r)

if __name__ == "__main__":
    asyncio.run(main())
```

**运行结果（示例）**

```
https://www.python.org -> 12345 bytes
https://www.wikipedia.org -> 6789 bytes
https://www.github.com -> 101112 bytes
```

> 说明
> * `aiohttp.ClientSession` 负责连接池，复用 TCP 连接。
> * `asyncio.create_task()` 把 `fetch()` 协程包装成可调度的 Task。
> * `asyncio.gather()` 并发等待所有任务完成，并返回结果列表。
> * `async with` 确保资源（连接）正确释放。

---

## 调试与排查小贴士

| 工具 | 用途 |
|------|------|
| `asyncio.run()` | 简化入口，自动创建/关闭事件循环 |
| `asyncio.get_running_loop()` | 在协程内部获取当前事件循环 |
| `asyncio.Task.all_tasks()` | 查看当前所有未完成的 Task |
| `asyncio.run(debug=True)` | Python 3.11+ 可开启调试模式，打印协程状态 |
| `nest_asyncio.apply()` | 在 Jupyter Notebook 等已有循环环境中使用 `asyncio.run()` |

**常见错误**

| 错误 | 说明 |
|------|------|
| `RuntimeError: Event loop is closed` | 在已关闭的循环中调用 `asyncio.run()` 或 `loop.run_until_complete()` |
| `RuntimeError: Cannot run the event loop while another loop is running` | 在已有循环环境（如 Jupyter）中调用 `asyncio.run()`，可使用 `nest_asyncio.apply()` |
| `ConnectionError` | 网络请求失败，检查 URL、代理、SSL 等 |

---

## 小结

1. **异步编程**：通过 `async/await`、事件循环实现 I/O 并发。
2. **核心库**：`asyncio`（标准库） + `aiohttp`（网络 I/O）等。
3. **最佳实践**
   * 用 `asyncio.run()` 作为入口。
   * 用 `asyncio.create_task()` 或 `asyncio.gather()` 并发任务。
   * 资源使用 `async with` 或 `try/finally` 及时释放。
   * 避免在协程中执行阻塞 CPU 代码；如需 CPU 密集，可使用 `concurrent.futures.ThreadPoolExecutor` 或 `ProcessPoolExecutor`。

通过上述示例，你已经掌握了异步编程的基本语法与思路。接下来可以尝试：

* 并发下载多张图片并保存到磁盘。
* 用 `asyncio.Queue` 实现生产者-消费者模型。
* 将异步代码与数据库（如 `aiomysql`、`asyncpg`）结合。

祝你编码愉快 🚀！

修订次数：2
PS C:\ron\FlutterAI\day9>
