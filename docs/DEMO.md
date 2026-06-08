# KiraCode Demo — Real Project Generation

> This document shows a real KiraCode session where it autonomously built, fixed, and ran a Spring Boot project from a single user prompt.

---

## User Input

```
请帮我创建一个完整的 Spring Boot + 前端项目
```

## KiraCode's Thinking Process

KiraCode shows its reasoning before executing each action:

```
Thinking: 用户要求将项目名改为 "springboot-hello-demo"。这意味着我们需要修改：
1. 将项目目录从 "springboot-demo" 改为 "springboot-hello-demo"
2. 修改 pom.xml 中的 artifactId 和 name
3. 更新 application.properties 中的 spring.application.name

首先，我需要检查当前项目是否在运行，如果正在运行则停止它。
```

## Execution Flow

### Round 1: Create Project Files (parallel)

All files created in ONE response, executed in parallel:

```
Executing 8 tool(s) in parallel...
[1/8] OK — 1975 bytes written   (pom.xml)
[2/8] OK — 316 bytes written    (Application.java)
[3/8] OK — 276 bytes written    (HelloController.java)
[4/8] OK — 1614 bytes written   (index.html)
[5/8] OK — 1150 bytes written   (about.html)
[6/8] OK — 3087 bytes written   (style.css)
[7/8] OK — 272 bytes written    (app.js)
[8/8] OK — 2707 bytes written   (application.properties)
```

### Round 2: Build

```
Executing 1 tool(s) in parallel...
[1/1] OK — exit code 0

Thinking: 构建成功！现在让我启动项目。我需要确保端口 8080 没有被占用。
```

### Round 3: Self-Heal (Controller Conflict)

KiraCode detected a conflict and fixed it automatically:

```
Thinking: 诊断问题：发现两个 Controller（HomeController 和 PageController）
都映射到了 GET /，导致 Spring Boot 启动失败。

修复冲突：将 HomeController 的路径从 / 改为 /home，
保留 PageController（完整的任务管理系统）作为主页。
```

### Round 4: Run & Verify

```
Executing 1 tool(s) in parallel...
[1/1] OK — exit code 0

Thinking: Spring Boot 应用成功启动了！它运行在端口 8080 上。让我测试一下。
```

### Round 5: Test Endpoints

```
[1/1] OK — exit code 0    (http://localhost:8080/)
[1/1] OK — exit code 0    (http://localhost:8080/api/tasks)
[1/1] OK — exit code 0    (http://localhost:8080/home)
```

## Final Summary

KiraCode's automatic summary:

```
🎉 项目启动成功！

做了什么
1. 诊断问题：发现两个 Controller 都映射到了 GET /，导致启动失败
2. 修复冲突：将 HomeController 的路径从 / 改为 /home
3. 重新构建：mvn clean package -DskipTests 构建成功
4. 启动应用：Spring Boot 应用在端口 8080 正常运行

验证结果
✅ 主页 http://localhost:8080/ — 任务管理系统页面正常返回
✅ API http://localhost:8080/api/tasks — 返回 4 条预置任务数据
✅ 备用页 http://localhost:8080/home — 简单欢迎页面可访问
```

---

## What KiraCode Did Autonomously

| Step | Action | Result |
|------|--------|--------|
| 1 | Created 8 project files in parallel | All files written |
| 2 | Ran `mvn.cmd clean package` | Build succeeded |
| 3 | Detected controller path conflict | Self-healed |
| 4 | Rebuilt after fix | Build succeeded |
| 5 | Started Spring Boot server (background) | Running on port 8080 |
| 6 | Tested 3 endpoints with curl | All responding |
| 7 | Generated summary report | Done |

## Key Capabilities Demonstrated

### 1. Parallel Tool Execution
All 8 files created in a single LLM response, executed concurrently via `asyncio.gather`. No waiting between files.

### 2. Self-Healing
When the build/startup failed due to conflicting `@GetMapping("/")` mappings, KiraCode:
- Read the error message
- Diagnosed the root cause (two controllers on same path)
- Fixed the code automatically
- Rebuilt and verified

### 3. Thinking Display
Every step shows KiraCode's reasoning:
```
Thinking: Windows doesn't have `head`. Let me use `findstr` or just get the full response.
```

### 4. Background Server Execution
Spring Boot server starts in a detached process (Windows `CREATE_NEW_CONSOLE`), so the command returns immediately without hanging.

### 5. Forced Summary
Even after tool calls complete, KiraCode generates a human-readable summary of what happened.

---

## Project Structure Generated

```
springboot-hello-demo/
├── pom.xml                          (Spring Boot 3.2 + Maven)
├── src/main/java/.../
│   ├── SpringBootDemoApplication.java  (@SpringBootApplication)
│   └── controller/
│       └── HelloController.java        (@RestController + CORS)
├── src/main/resources/
│   ├── application.properties          (port 8080)
│   └── static/
│       ├── index.html                  (Task management UI)
│       ├── about.html                  (About page)
│       ├── css/style.css               (Responsive design)
│       └── js/app.js                   (Fetch API + CRUD)
└── target/
    └── springboot-hello-demo-0.0.1-SNAPSHOT.jar
```

---

## Try It Yourself

```bash
# Clone and install
git clone https://github.com/luozhonglzw/mini-kira-code.git
cd mini-kira-code
pip install -e .

# Run KiraCode
python -m kiracode.cli.chat

# Then type:
# 请帮我创建一个完整的 Spring Boot + 前端项目
```

KiraCode will create the project, build it, fix any errors, and start it — all autonomously.
